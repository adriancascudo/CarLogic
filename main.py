import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel

app = FastAPI(title="API Coche Compartido")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")

PUNTUACIONES = {
    1: (24, -24),
    2: (30, -15),
    3: (33, -11),
    4: (36, -9),
}


class ConsultaConductorRequest(BaseModel):
    participantes_ids: List[str]


class RegistroViajeRequest(BaseModel):
    fecha: str
    conductor_id: str
    pasajeros_sistema_ids: List[str]


def obtener_conexion():
    if not DATABASE_URL:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL no está configurada en las variables de entorno.",
        )
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def calcular_puntos_viaje(num_pasajeros: int) -> tuple[int, int]:
    """Retorna (puntos_conductor, puntos_pasajero) según la tabla del PDF."""
    if num_pasajeros in PUNTUACIONES:
        return PUNTUACIONES[num_pasajeros]
    if num_pasajeros > 4:
        puntos_conductor = 36 + (num_pasajeros - 4) * 3
        puntos_pasajero = -(puntos_conductor // num_pasajeros)
        return puntos_conductor, puntos_pasajero
    raise ValueError("El viaje debe incluir al menos a 1 pasajero del sistema.")

class UsuarioCreateRequest(BaseModel):
    nombre: str
    conduce_habitualmente: bool = True


@app.get("/api/v1/usuarios")
def listar_usuarios():
    conn = obtener_conexion()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nombre, conduce_habitualmente FROM usuarios ORDER BY nombre ASC;"
            )
            return cur.fetchall()
    finally:
        conn.close()


@app.post("/api/v1/usuarios")
def crear_usuario(payload: UsuarioCreateRequest):
    conn = obtener_conexion()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO usuarios (nombre, conduce_habitualmente) VALUES (%s, %s) RETURNING id;",
                (payload.nombre, payload.conduce_habitualmente),
            )
            conn.commit()
            return {"status": "success", "id": cur.fetchone()["id"]}
    finally:
        conn.close()


@app.delete("/api/v1/usuarios/{usuario_id}")
def eliminar_usuario(usuario_id: str):
    conn = obtener_conexion()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM usuarios WHERE id = %s;", (usuario_id,))
            conn.commit()
            return {"status": "success"}
    finally:
        conn.close()


@app.get("/api/v1/viajes-historial")
def listar_historial():
    conn = obtener_conexion()
    try:
        with conn.cursor() as cur:
            query = """
                SELECT 
                    v.id,
                    v.fecha,
                    u.nombre AS conductor_nombre,
                    ARRAY_REMOVE(ARRAY_AGG(up.nombre), NULL) AS pasajeros
                FROM viajes v
                JOIN usuarios u ON v.conductor_id = u.id
                LEFT JOIN viaje_pasajeros vp ON vp.viaje_id = v.id
                LEFT JOIN usuarios up ON vp.usuario_id = up.id
                GROUP BY v.id, v.fecha, u.nombre
                ORDER BY v.fecha DESC, v.creado_en DESC;
            """
            cur.execute(query)
            viajes = cur.fetchall()
            for v in viajes:
                num_p = len(v["pasajeros"])
                p_cond, p_pas = (
                    calcular_puntos_viaje(num_p) if num_p > 0 else (0, 0)
                )
                v["puntos_conductor"] = p_cond
                v["puntos_pasajero"] = p_pas
            return viajes
    finally:
        conn.close()


@app.get("/")
def estado_api():
    return {"status": "ok", "mensaje": "API Coche Compartido activa"}


@app.post("/api/v1/sugerir-conductor")
def sugerir_conductor(payload: ConsultaConductorRequest):
    """
    Regla 1: Menor saldo acumulado.
    Regla 2: Menor número de viajes realizados como conductor.
    Regla 3: Desempate por ID (orden de llegada).
    Excluye automáticamente a los participantes registrados sin vehículo.
    """
    if not payload.participantes_ids:
        raise HTTPException(
            status_code=400, detail="Debe indicar al menos un participante."
        )

    conn = obtener_conexion()
    try:
        with conn.cursor() as cur:
            # Obtener datos de saldo y total de conducciones para los elegibles
            query = """
                SELECT 
                    u.id,
                    u.nombre,
                    u.conduce_habitualmente,
                    COALESCE(SUM(
                        CASE 
                            WHEN v.conductor_id = u.id THEN (
                                SELECT CASE 
                                    WHEN COUNT(vp.usuario_id) = 1 THEN 24
                                    WHEN COUNT(vp.usuario_id) = 2 THEN 30
                                    WHEN COUNT(vp.usuario_id) = 3 THEN 33
                                    WHEN COUNT(vp.usuario_id) = 4 THEN 36
                                    ELSE 36 + (COUNT(vp.usuario_id) - 4) * 3
                                END
                                FROM viaje_pasajeros vp WHERE vp.viaje_id = v.id
                            )
                            ELSE 0
                        END
                    ), 0) + COALESCE(SUM(
                        CASE 
                            WHEN vp_sub.usuario_id = u.id THEN (
                                SELECT CASE 
                                    WHEN count_pas.total = 1 THEN -24
                                    WHEN count_pas.total = 2 THEN -15
                                    WHEN count_pas.total = 3 THEN -11
                                    WHEN count_pas.total = 4 THEN -9
                                    ELSE -((36 + (count_pas.total - 4) * 3) / count_pas.total)
                                END
                                FROM (
                                    SELECT COUNT(*) as total 
                                    FROM viaje_pasajeros 
                                    WHERE viaje_id = vp_sub.viaje_id
                                ) count_pas
                            )
                            ELSE 0
                        END
                    ), 0) AS saldo,
                    (SELECT COUNT(*) FROM viajes v_cond WHERE v_cond.conductor_id = u.id) AS total_conducciones
                FROM usuarios u
                LEFT JOIN viajes v ON v.conductor_id = u.id
                LEFT JOIN viaje_pasajeros vp_sub ON vp_sub.usuario_id = u.id
                WHERE u.id = ANY(%s::uuid[]) AND u.conduce_habitualmente = TRUE
                GROUP BY u.id, u.nombre, u.conduce_habitualmente;
            """
            cur.execute(query, (payload.participantes_ids,))
            candidatos = cur.fetchall()

            if not candidatos:
                raise HTTPException(
                    status_code=404,
                    detail="Ninguno de los participantes indicados está habilitado para conducir.",
                )

            # Ordenar aplicando las reglas 1, 2 y 3 del documento
            candidatos_ordenados = sorted(
                candidatos,
                key=lambda x: (x["saldo"], x["total_conducciones"], x["id"]),
            )

            conductor_elegido = candidatos_ordenados[0]

            return {
                "conductor_sugerido": conductor_elegido,
                "ranking_candidatos": candidatos_ordenados,
            }
    finally:
        conn.close()


@app.post("/api/v1/viajes")
def registrar_viaje(payload: RegistroViajeRequest):
    num_pasajeros = len(payload.pasajeros_sistema_ids)

    if payload.conductor_id in payload.pasajeros_sistema_ids:
        raise HTTPException(
            status_code=400,
            detail="El conductor no puede figurar en la lista de pasajeros del sistema.",
        )

    try:
        p_cond, p_pas = calcular_puntos_viaje(num_pasajeros)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))

    conn = obtener_conexion()
    try:
        with conn.cursor() as cur:
            # Insertar viaje
            cur.execute(
                "INSERT INTO viajes (fecha, conductor_id) VALUES (%s, %s) RETURNING id;",
                (payload.fecha, payload.conductor_id),
            )
            viaje_id = cur.fetchone()["id"]

            # Insertar pasajeros asociados al sistema
            for p_id in payload.pasajeros_sistema_ids:
                cur.execute(
                    "INSERT INTO viaje_pasajeros (viaje_id, usuario_id) VALUES (%s, %s);",
                    (viaje_id, p_id),
                )

            conn.commit()

            return {
                "status": "success",
                "viaje_id": viaje_id,
                "puntos_conductor": p_cond,
                "puntos_por_pasajero": p_pas,
                "balance_suma_cero": p_cond + (p_pas * num_pasajeros),
            }
    except Exception as err:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(err))
    finally:
        conn.close()