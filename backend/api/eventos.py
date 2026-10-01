"""Rutas de eventos, stream de video y estado del motor de visión."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db, ping, estadisticas
from ..models import Evento, Persona, Zona
from ..schemas import EventoOut, EstadoMonitor
from ..vision.pipeline import monitor, stream_frames

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["vision"])


@router.get("/stream")
def stream():
    """Stream MJPEG con el fotograma anotado (o un aviso si no hay cámara)."""
    return StreamingResponse(
        stream_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
            # evita que proxies o navegadores acumulen los fotogramas
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/frame")
def frame():
    """Último fotograma anotado (JPEG) — lo consume el frontend Streamlit."""
    jpeg = monitor.fotograma()
    if not jpeg:
        estado = monitor.estado()
        if not estado["activo"]:
            detalle = "El motor de visión está detenido. POST /api/monitor/start para encenderlo."
        else:
            detalle = f"Sin fotogramas: {estado['estado']}"
        raise HTTPException(503, detalle)
    return Response(content=jpeg, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


@router.get("/estado", response_model=EstadoMonitor)
def estado():
    return EstadoMonitor(**monitor.estado())


@router.get("/alarma")
def alarma():
    return {"activa": monitor.alarma()}


@router.post("/monitor/{accion}")
def monitor_accion(accion: str):
    """acciones: start | stop | reiniciar-cache"""
    accion = accion.lower()
    if accion in {"start", "iniciar", "start"}:
        monitor.iniciar()
        return {"ok": True, "accion": "iniciado"}
    if accion in {"stop", "detener"}:
        monitor.detener()
        return {"ok": True, "accion": "detenido"}
    if accion in {"reiniciar-cache", "reload-cache"}:
        from ..vision import face as face_mod

        face_mod.invalidar_cache()
        return {"ok": True, "accion": "recargando embeddings"}
    raise HTTPException(400, f"Acción desconocida: {accion}")


@router.get("/eventos", response_model=list[EventoOut])
def listar_eventos(
    limit: int = Query(50, ge=1, le=500),
    tipo: str | None = None,
    persona_id: int | None = None,
    zona_id: int | None = None,
    db: Session = Depends(get_db),
):
    consulta = (
        select(Evento, Persona.nombre, Zona.nombre)
        .outerjoin(Persona, Evento.persona_id == Persona.id)
        .outerjoin(Zona, Evento.zona_id == Zona.id)
        .order_by(Evento.timestamp.desc(), Evento.id.desc())
        .limit(limit)
    )
    if tipo in {"autorizado", "no_autorizado"}:
        consulta = consulta.where(Evento.tipo == tipo)
    if persona_id:
        consulta = consulta.where(Evento.persona_id == persona_id)
    if zona_id:
        consulta = consulta.where(Evento.zona_id == zona_id)

    filas = db.execute(consulta).all()
    return [
        EventoOut(
            id=e.id,
            ts=e.timestamp,
            persona_id=e.persona_id,
            nombre=nombre,
            tipo=e.tipo,
            zona_id=e.zona_id,
            zona_nombre=zona_nombre,
            similitud=e.similitud,
            nota=e.nota,
            tiene_snapshot=e.snapshot is not None,
        )
        for e, nombre, zona_nombre in filas
    ]


@router.get("/eventos/{eid}/snapshot")
def snapshot_evento(eid: int, db: Session = Depends(get_db)):
    evento = db.get(Evento, eid)
    if not evento or not evento.snapshot:
        raise HTTPException(404, "El evento no tiene snapshot")
    return Response(content=evento.snapshot, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


@router.delete("/eventos/{eid}", response_model=dict)
def borrar_evento(eid: int, db: Session = Depends(get_db)):
    evento = db.get(Evento, eid)
    if not evento:
        raise HTTPException(404, "Evento no encontrado")
    db.delete(evento)
    db.commit()
    return {"ok": True, "id": eid}


@router.post("/eventos/purgar", response_model=dict)
def purgar(dias: int = Query(90, ge=1, le=3650), db: Session = Depends(get_db)):
    """Elimina eventos con snapshot anterior a N días (los autorizados no guardan foto)."""
    import sqlalchemy as sa
    from datetime import datetime, timedelta

    limite = datetime.now() - timedelta(days=dias)
    borrados = db.execute(
        sa.delete(Evento).where(Evento.timestamp < limite)
    ).rowcount
    db.commit()
    return {"ok": True, "borrados": borrados, "dias": dias}


@router.get("/db/estado")
def db_estado():
    ok, mensaje = ping()
    datos = estadisticas() if ok else {}
    return {"ok": ok, "mensaje": mensaje, "estadisticas": datos}
