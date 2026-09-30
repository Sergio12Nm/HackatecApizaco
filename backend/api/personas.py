"""Rutas de personas autorizadas y sus embeddings."""

from __future__ import annotations

import logging

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Embedding, LogRegistro, Persona
from ..schemas import PersonaOut
from ..utils import bytes_a_imagen, imagen_a_jpeg
from ..vision import face as face_mod

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/personas", tags=["personas"])


def _guardar_embeddings(
    db: Session, persona: Persona, imagenes: list[np.ndarray], origen: str
) -> int:
    """Genera y persiste los embeddings de un lote de imágenes."""
    guardados = 0
    vistos: set[bytes] = set()

    for img in imagenes:
        try:
            emb = face_mod.generar_embedding(img)
        except Exception as exc:
            log.error("No se pudo generar el embedding: %s", exc)
            continue
        if emb is None:
            continue

        # evita imágenes duplicadas byte a byte
        firma = emb.tobytes()
        if firma in vistos:
            continue
        vistos.add(firma)

        jpg = imagen_a_jpeg(img, 85)
        db.add(
            Embedding(
                persona_id=persona.id,
                vector=firma,
                foto=jpg,
                foto_mime="image/jpeg",
            )
        )
        guardados += 1

    db.add(
        LogRegistro(
            persona_id=persona.id,
            embeddings_creados=guardados,
            mensaje=origen[:255],
        )
    )
    db.commit()
    face_mod.invalidar_cache()
    return guardados


@router.post("", response_model=dict)
@router.post("/", response_model=dict, include_in_schema=False)
async def registrar_persona(
    nombre: str = Form(...),
    documento: str = Form(""),
    cargo: str = Form(""),
    email: str = Form(""),
    telefono: str = Form(""),
    fotos: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Registra una persona nueva a partir de 1-5 fotos con rostro visible."""
    nombre = nombre.strip()
    if len(nombre) < 2:
        raise HTTPException(400, "El nombre es demasiado corto")
    documento = documento.strip() or None

    if documento:
        existe = db.scalar(select(Persona).where(Persona.documento == documento))
        if existe:
            raise HTTPException(400, f"El documento {documento} ya está registrado")

    imagenes: list[np.ndarray] = []
    for f in fotos:
        raw = await f.read()
        img = bytes_a_imagen(raw)
        if img is None:
            continue
        imagenes.append(img)

    if not imagenes:
        raise HTTPException(400, "Ninguna de las imágenes pudo decodificarse")

    persona = Persona(
        nombre=nombre,
        documento=documento,
        cargo=cargo.strip() or None,
        email=email.strip() or None,
        telefono=telefono.strip() or None,
        activo=True,
    )
    db.add(persona)
    db.commit()
    db.refresh(persona)

    guardados = _guardar_embeddings(db, persona, imagenes, f"Registro vía API ({len(imagenes)} fotos)")

    if guardados == 0:
        db.delete(persona)
        db.commit()
        face_mod.invalidar_cache()
        raise HTTPException(
            400,
            "Ninguna foto contiene un rostro válido. Usa fotos frontales, "
            "con buena iluminación y sin accesorios que tapen el rostro.",
        )

    return {
        "ok": True,
        "persona_id": persona.id,
        "embeddings": guardados,
        "mensaje": f"{nombre} registrado con {guardados} embedding(s)",
    }


@router.post("/{pid}/embeddings", response_model=dict)
async def agregar_embeddings(
    pid: int,
    fotos: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Registro en caliente: más fotos para una persona ya existente."""
    persona = db.get(Persona, pid)
    if not persona:
        raise HTTPException(404, "Persona no encontrada")

    imagenes = []
    for f in fotos:
        img = bytes_a_imagen(await f.read())
        if img is not None:
            imagenes.append(img)
    if not imagenes:
        raise HTTPException(400, "Ninguna imagen válida")

    nuevos = _guardar_embeddings(db, persona, imagenes, f"Ampliación vía API ({len(imagenes)} fotos)")
    if nuevos == 0:
        raise HTTPException(400, "Ninguna foto contiene un rostro válido")

    return {"ok": True, "persona_id": pid, "embeddings": nuevos,
            "mensaje": f"Se agregaron {nuevos} embedding(s)"}


@router.get("", response_model=list[PersonaOut])
@router.get("/", response_model=list[PersonaOut], include_in_schema=False)
def listar_personas(solo_activas: bool = False, db: Session = Depends(get_db)):
    consulta = select(Persona).order_by(Persona.nombre)
    if solo_activas:
        consulta = consulta.where(Persona.activo.is_(True))
    personas = db.scalars(consulta).unique().all()
    return [
        PersonaOut(
            id=p.id,
            nombre=p.nombre,
            documento=p.documento,
            cargo=p.cargo,
            email=p.email,
            telefono=p.telefono,
            activo=bool(p.activo),
            num_embeddings=len(p.embeddings),
        )
        for p in personas
    ]


@router.patch("/{pid}/activo", response_model=dict)
def cambiar_activo(pid: int, activo: bool, db: Session = Depends(get_db)):
    persona = db.get(Persona, pid)
    if not persona:
        raise HTTPException(404, "Persona no encontrada")
    persona.activo = activo
    db.commit()
    face_mod.invalidar_cache()
    return {"ok": True, "id": pid, "activo": activo}


@router.delete("/{pid}", response_model=dict)
def eliminar_persona(pid: int, db: Session = Depends(get_db)):
    persona = db.get(Persona, pid)
    if not persona:
        raise HTTPException(404, "Persona no encontrada")
    db.delete(persona)
    db.commit()
    face_mod.invalidar_cache()
    return {"ok": True, "id": pid}


@router.get("/{pid}/foto")
def foto_persona(pid: int, indice: int = 0, db: Session = Depends(get_db)):
    """Devuelve una foto de registro de la persona (por defecto la primera)."""
    if not db.get(Persona, pid):
        raise HTTPException(404, "Persona no encontrada")
    emb = (
        db.query(Embedding)
        .filter(Embedding.persona_id == pid)
        .order_by(Embedding.id.asc())
        .offset(max(0, indice))
        .first()
    )
    if not emb or not emb.foto:
        raise HTTPException(404, "Sin foto registrada")
    return Response(content=emb.foto, media_type=emb.foto_mime or "image/jpeg")
