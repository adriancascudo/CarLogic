import os
from typing import List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="API Coche Compartido")

# Permitir peticiones desde cualquier origen (móviles / web PWA)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Matriz de puntuación propuesta en el documento
PUNTUACIONES = {
    1: (24, -24),
    2: (30, -15),
    3: (33, -11),
    4: (36, -9),
}


class RegistroViajeRequest(BaseModel):
    fecha: str
    conductor_id: str
    pasajeros_ids: List[str]


def obtener_puntuacion(num_pasajeros: int) -> tuple[int, int]:
    if num_pasajeros in PUNTUACIONES:
        return PUNTUACIONES[num_pasajeros]
    if num_pasajeros > 4:
        p_cond = 36 + (num_pasajeros - 4) * 3
        p_pas = -(p_cond // num_pasajeros)
        return p_cond, p_pas
    raise ValueError("El viaje requiere al menos 1 pasajero del sistema.")


@app.get("/")
def estado_api():
    return {"status": "ok", "mensaje": "API Coche Compartido activa"}


@app.post("/api/v1/viajes")
def registrar_viaje(payload: RegistroViajeRequest):
    num_pasajeros = len(payload.pasajeros_ids)

    if payload.conductor_id in payload.pasajeros_ids:
        raise HTTPException(
            status_code=400,
            detail="El conductor no puede ser también pasajero.",
        )

    try:
        p_cond, p_pas = obtener_puntuacion(num_pasajeros)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))

    movimientos = [
        {"usuario_id": payload.conductor_id, "puntos": p_cond, "rol": "C"}
    ]
    for p_id in payload.pasajeros_ids:
        movimientos.append({"usuario_id": p_id, "puntos": p_pas, "rol": "P"})

    return {
        "status": "success",
        "fecha": payload.fecha,
        "balance_total": sum(m["puntos"] for m in movimientos),
        "movimientos": movimientos,
    }