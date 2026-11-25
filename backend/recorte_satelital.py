from math import isfinite
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.enums import ColorInterp, MaskFlags
from rasterio.errors import RasterioError
from rasterio.features import geometry_mask, geometry_window
from rasterio.io import MemoryFile
from shapely.geometry import Point

from backend.clasificador import CRS_PROYECTADO

PROYECTAR_CENTRO = Transformer.from_crs("EPSG:4326", CRS_PROYECTADO, always_xy=True)
SIN_COBERTURA = "Sentinel-2 no cubre todo el círculo. Prueba otra zona o sube un TIFF."
SIN_FUENTE = "El mosaico Sentinel-2 no está disponible. Puedes subir un TIFF manualmente."


class ErrorFuenteSentinel(RuntimeError):
    """El mosaico configurado no se puede usar para el recorte automático."""


def generar_recorte_satelital(
    latitud: float, longitud: float, radio_m: float, ruta_sentinel: Path | None,
) -> bytes:
    if not 50 <= radio_m <= 2000:
        raise ValueError("El radio para analizar con IA debe estar entre 50 y 2000 m.")
    este, norte = PROYECTAR_CENTRO.transform(longitud, latitud)
    if not isfinite(este) or not isfinite(norte):
        raise ValueError(SIN_COBERTURA)
    # Los recortes de entrenamiento usan 20 lados para aproximar el círculo.
    circulo = Point(este, norte).buffer(radio_m, quad_segs=5)

    try:
        if ruta_sentinel is None or not ruta_sentinel.is_file():
            raise ErrorFuenteSentinel(SIN_FUENTE)
        with rasterio.open(ruta_sentinel, mode="r", driver="GTiff") as fuente:
            if (
                fuente.crs != CRS_PROYECTADO
                or fuente.dtypes != ("uint8",) * 3
                or fuente.colorinterp != (ColorInterp.red, ColorInterp.green, ColorInterp.blue)
                or (fuente.transform.a, fuente.transform.b, fuente.transform.d, fuente.transform.e)
                != (10, 0, 0, -10)
            ):
                raise ErrorFuenteSentinel(SIN_FUENTE)

            ventana = geometry_window(fuente, [circulo], boundless=True)
            if (
                ventana.col_off < 0 or ventana.row_off < 0
                or ventana.col_off + ventana.width > fuente.width
                or ventana.row_off + ventana.height > fuente.height
            ):
                raise ValueError(SIN_COBERTURA)

            rgb = fuente.read(window=ventana)
            transformacion = fuente.window_transform(ventana)
            mascara = geometry_mask(
                [circulo], rgb.shape[1:], transformacion, invert=True,
            )
            if all(MaskFlags.all_valid in banderas for banderas in fuente.mask_flag_enums):
                # El COG publicado no declara nodata. Usa RGB negro para el relleno.
                cobertura = np.any(rgb != 0, axis=0)
            else:
                cobertura = fuente.dataset_mask(window=ventana) != 0
            if not cobertura[mascara].all():
                raise ValueError(SIN_COBERTURA)
    except (OSError, RasterioError) as error:
        raise ErrorFuenteSentinel(SIN_FUENTE) from error

    rgb[:, ~mascara] = 0
    with MemoryFile() as memoria:
        with memoria.open(
            driver="GTiff", width=rgb.shape[2], height=rgb.shape[1], count=3, dtype="uint8",
            crs=CRS_PROYECTADO, transform=transformacion, photometric="RGB", compress="deflate",
        ) as tiff:
            tiff.write(rgb)
        return memoria.read()
