"""Rutas de zonas restringidas."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Zona
from ..schemas import ZonaCreate, ZonaOut
from ..utils import normalizar_poligono, poligono_a_json, poligono_valido

router = APIRouter(prefix="/api/zonas", tags=["zonas"])


@router.post("", response_model=dict)
@router.post("/", response_model=dict, include_in_schema=False)
def crear_zona(datos: ZonaCreate, db: Session = Depends(get_db)):
    if not datos.nombre.strip():
        raise HTTPException(400, "La zona necesita un nombre")
    if not poligono_valido(datos.poligono):
        raise HTTPException(400, "El polígono necesita al menos 3 puntos [x, y]")

    zona = Zona(
        nombre=datos.nombre.strip(),
        poligono=poligono_a_json(datos.poligono),
        camara_id=datos.camara_id or "cam0",
    )
    db.add(zona)
    db.commit()
    db.refresh(zona)
    return {"ok": True, "id": zona.id, "mensaje": f"Zona '{zona.nombre}' creada"}


@router.get("", response_model=list[ZonaOut])
@router.get("/", response_model=list[ZonaOut], include_in_schema=False)
def listar_zonas(db: Session = Depends(get_db)):
    zonas = db.scalars(select(Zona).order_by(Zona.id)).all()
    return [
        ZonaOut(id=z.id, nombre=z.nombre, poligono=normalizar_poligono(z.puntos()),
                camara_id=z.camara_id)
        for z in zonas
    ]


@router.put("/{zid}", response_model=dict)
def actualizar_zona(zid: int, datos: ZonaCreate, db: Session = Depends(get_db)):
    zona = db.get(Zona, zid)
    if not zona:
        raise HTTPException(404, "Zona no encontrada")
    if not poligono_valido(datos.poligono):
        raise HTTPException(400, "El polígono necesita al menos 3 puntos [x, y]")
    zona.nombre = datos.nombre.strip()
    zona.poligono = poligono_a_json(datos.poligono)
    zona.camara_id = datos.camara_id or "cam0"
    db.commit()
    return {"ok": True, "id": zid, "mensaje": "Zona actualizada"}


@router.delete("/{zid}", response_model=dict)
def eliminar_zona(zid: int, db: Session = Depends(get_db)):
    zona = db.get(Zona, zid)
    if not zona:
        raise HTTPException(404, "Zona no encontrada")
    db.delete(zona)
    db.commit()
    return {"ok": True, "id": zid, "mensaje": "Zona eliminada"}


@router.post("/validar", response_model=dict)
def validar(poligono: list):
    try:
        datos = json.loads(poligono) if isinstance(poligono, str) else poligono
    except json.JSONDecodeError as exc:
        raise HTTPException(400, f"JSON inválido: {exc}")
    if not poligono_valido(datos):
        raise HTTPException(400, "El polígono necesita al menos 3 puntos [x, y]")
    return {"ok": True, "puntos": len(datos)}
