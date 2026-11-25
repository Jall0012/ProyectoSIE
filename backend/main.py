import os
from base64 import b64encode
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.inferencia import analizar_recorte, cargar_modelo, leer_recorte
from backend.clasificador import CRS_PROYECTADO, cargar_capas_base, evaluar_circulo
from backend.recorte_satelital import ErrorProveedorImagen, generar_recorte_satelital

MAX_BYTES_TIFF = 16 * 1024 * 1024


class Zona(BaseModel):
    latitud: float = Field(ge=-90, le=90, strict=True, allow_inf_nan=False)
    longitud: float = Field(ge=-180, le=180, strict=True, allow_inf_nan=False)
    radio_m: float = Field(gt=0, strict=True, allow_inf_nan=False)


class ResultadoZona(BaseModel):
    categoria: str
    puntuacion: float | None


class ResultadoImagen(BaseModel):
    categoria: str
    probabilidades: dict[str, float]
    probabilidad_veto: float


class ResultadoZonaImagen(ResultadoImagen):
    recorte_tiff: str


def ruta_configurada(variable: str) -> Path:
    valor = os.environ.get(variable)
    if not valor or not Path(valor).is_file():
        raise RuntimeError(f"Configura {variable} con la ruta de un archivo existente.")
    return Path(valor).resolve()


@asynccontextmanager
async def cargar_recursos(aplicacion: FastAPI) -> AsyncIterator[None]:
    ruta_gpkg = ruta_configurada("PROYECTOSIE_GPKG")
    ruta_modelo = ruta_configurada("PROYECTOSIE_MODELO")
    aplicacion.state.ruta_gpkg = ruta_gpkg
    aplicacion.state.capas = cargar_capas_base(ruta_gpkg, CRS_PROYECTADO, incluir_malla=False)
    aplicacion.state.modelo = cargar_modelo(ruta_modelo)
    yield


app = FastAPI(title="ProyectoSIE", lifespan=cargar_recursos)


@app.exception_handler(RequestValidationError)
async def error_validacion(_solicitud: Request, error: RequestValidationError) -> JSONResponse:
    # Los valores rechazados, como NaN, no siempre se pueden serializar como JSON.
    detalle = [{"loc": fallo["loc"], "msg": fallo["msg"]} for fallo in error.errors()]
    return JSONResponse(status_code=422, content={"detail": detalle})


@app.get("/salud")
def salud() -> dict[str, str]:
    return {"estado": "ok"}


@app.post("/evaluar-zona")
def evaluar_zona(zona: Zona, solicitud: Request) -> ResultadoZona:
    estado = solicitud.app.state
    try:
        categoria, puntuacion = evaluar_circulo(
            zona.latitud, zona.longitud, zona.radio_m, estado.ruta_gpkg, estado.capas
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return ResultadoZona(categoria=categoria, puntuacion=puntuacion)


@app.post("/analizar-imagen")
def analizar_imagen(archivo: UploadFile, solicitud: Request) -> ResultadoImagen:
    contenido = archivo.file.read(MAX_BYTES_TIFF + 1)
    if len(contenido) > MAX_BYTES_TIFF:
        raise HTTPException(status_code=413, detail="El TIFF supera el límite de 16 MiB.")
    return analizar_tiff(contenido, solicitud)


@app.post("/analizar-zona-imagen")
def analizar_zona_imagen(zona: Zona, solicitud: Request) -> ResultadoZonaImagen:
    try:
        contenido = generar_recorte_satelital(zona.latitud, zona.longitud, zona.radio_m)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ErrorProveedorImagen as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    resultado = analizar_tiff(contenido, solicitud)
    return ResultadoZonaImagen(
        **resultado.model_dump(), recorte_tiff=b64encode(contenido).decode("ascii"),
    )


def analizar_tiff(contenido: bytes, solicitud: Request) -> ResultadoImagen:
    try:
        imagen = leer_recorte(contenido)
        categoria, probabilidades, veto = analizar_recorte(solicitud.app.state.modelo, imagen)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    return ResultadoImagen(
        categoria=categoria, probabilidades=probabilidades, probabilidad_veto=veto
    )
