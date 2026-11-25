from pathlib import Path

import numpy as np
import tensorflow as tf
from rasterio.errors import RasterioError
from rasterio.io import MemoryFile

CLASES_APTITUD = ("Buenos", "Normales", "Malos")
FIRMAS_TIFF = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")
MAX_PIXELES_TIFF = 16_000_000


def cargar_modelo(ruta_modelo: Path) -> tf.keras.Model:
    with tf.device("/CPU:0"):
        modelo = tf.keras.models.load_model(ruta_modelo, compile=False)
    if modelo.input_shape[1:] != (128, 128, 3) or set(modelo.output_names) != {
        "salida_aptitud", "salida_prohibido",
    }:
        raise ValueError("El modelo Keras no tiene las entradas y salidas esperadas.")
    return modelo


def leer_recorte(contenido: bytes) -> np.ndarray:
    if not contenido.startswith(FIRMAS_TIFF):
        raise ValueError("El archivo debe ser un TIFF.")

    try:
        with MemoryFile(contenido) as memoria, memoria.open(driver="GTiff") as recorte:
            if recorte.count == 2 or recorte.count == 0:
                raise ValueError("El TIFF debe tener una banda o al menos tres.")
            if recorte.width * recorte.height > MAX_PIXELES_TIFF:
                raise ValueError("El TIFF supera el límite de 16 millones de píxeles.")
            bandas = (1, 1, 1) if recorte.count == 1 else (1, 2, 3)
            imagen = recorte.read(bandas, out_dtype="float32").transpose(1, 2, 0)
    except RasterioError as error:
        raise ValueError("No se pudo leer el TIFF.") from error

    if not np.isfinite(imagen).all():
        raise ValueError("El TIFF contiene valores de píxel no finitos.")
    return imagen


def analizar_recorte(
    modelo: tf.keras.Model, imagen: np.ndarray
) -> tuple[str, dict[str, float], float]:
    with tf.device("/CPU:0"):
        imagen_redimensionada = tf.image.resize(imagen, (128, 128))
        maximo = float(tf.reduce_max(imagen_redimensionada))
        if maximo > 0:
            imagen_redimensionada = imagen_redimensionada / maximo
        if not bool(tf.reduce_all(tf.math.is_finite(imagen_redimensionada))):
            raise ValueError("El intervalo de valores del TIFF impide normalizarlo.")
        salidas = modelo(imagen_redimensionada[None, ...], training=False)

    por_nombre = dict(zip(modelo.output_names, salidas, strict=True))
    probabilidades = {
        clase: float(probabilidad)
        for clase, probabilidad in zip(
            CLASES_APTITUD, por_nombre["salida_aptitud"][0], strict=True
        )
    }
    veto = float(por_nombre["salida_prohibido"][0, 0])
    if not np.isfinite([*probabilidades.values(), veto]).all():
        raise ValueError("No se pudo obtener una predicción válida para el TIFF.")
    categoria = max(CLASES_APTITUD, key=probabilidades.__getitem__)
    return categoria, probabilidades, veto
