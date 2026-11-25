from contextlib import closing
from http.client import HTTPException as ErrorHTTP
from http.client import HTTPSConnection
from math import ceil, floor, isfinite, pi
from time import monotonic

import numpy as np
from pyproj import Transformer
from rasterio.errors import RasterioError
from rasterio.features import geometry_mask
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from shapely.geometry import Point

from backend.clasificador import CRS_PROYECTADO


DOMINIO_IGN = "tms-pnoa-ma.idee.es"
CRS_WEB = "EPSG:3857"
ZOOM = 14
TESELAS_POR_LADO = 2 ** ZOOM
ANCHO_TESELA = 256
EXTREMO_WEB = pi * 6378137
METROS_TESELA_WEB = 2 * EXTREMO_WEB / TESELAS_POR_LADO
METROS_PIXEL_WEB = METROS_TESELA_WEB / ANCHO_TESELA
METROS_PIXEL_RECORTE = 10
MAX_TESELAS = 16
MAX_BYTES_TESELA = 512 * 1024
TIEMPO_ESPERA_TESELA = 5
TIEMPO_ESPERA_TOTAL = 12
SIN_COBERTURA = "No hay imagen satelital utilizable para todo el círculo. Prueba otra zona o sube un TIFF."

PROYECTAR_CENTRO = Transformer.from_crs("EPSG:4326", CRS_PROYECTADO, always_xy=True)
PROYECTAR_MOSAICO = Transformer.from_crs(CRS_PROYECTADO, CRS_WEB, always_xy=True)


class ErrorProveedorImagen(RuntimeError):
    """El servicio de imágenes no devolvió una tesela válida a tiempo."""


def teselas_del_recorte(limites: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    oeste, sur, este, norte = PROYECTAR_MOSAICO.transform_bounds(*limites)
    if not all(isfinite(valor) and abs(valor) <= EXTREMO_WEB for valor in (oeste, sur, este, norte)):
        raise ValueError(SIN_COBERTURA)
    if oeste > este:
        raise ValueError(SIN_COBERTURA)

    # Un píxel de margen conserva el contexto para la interpolación bilineal.
    margen = METROS_PIXEL_WEB
    columna_ini = max(0, floor((oeste - margen + EXTREMO_WEB) / METROS_TESELA_WEB))
    columna_fin = min(TESELAS_POR_LADO - 1, floor((este + margen + EXTREMO_WEB) / METROS_TESELA_WEB))
    fila_ini = max(0, floor((EXTREMO_WEB - norte - margen) / METROS_TESELA_WEB))
    fila_fin = min(TESELAS_POR_LADO - 1, floor((EXTREMO_WEB - sur + margen) / METROS_TESELA_WEB))
    if (columna_fin - columna_ini + 1) * (fila_fin - fila_ini + 1) > MAX_TESELAS:
        raise ValueError("No se puede recortar ese círculo. Reduce el radio o prueba otra zona.")
    return columna_ini, fila_ini, columna_fin, fila_fin


def descargar_tesela(
    conexion: HTTPSConnection, columna: int, fila: int, plazo: float,
) -> tuple[str, bytes] | None:
    restante = plazo - monotonic()
    if restante <= 0:
        raise ErrorProveedorImagen("Se agotó el tiempo de espera del proveedor de imágenes.")
    conexion.timeout = min(TIEMPO_ESPERA_TESELA, restante)
    if conexion.sock is not None:
        conexion.sock.settimeout(conexion.timeout)

    fila_tms = TESELAS_POR_LADO - 1 - fila
    conexion.request("GET", f"/1.0.0/pnoa-ma/{ZOOM}/{columna}/{fila_tms}.jpeg")
    with conexion.getresponse() as respuesta:
        if respuesta.status in (204, 404):
            conexion.close()
            return None
        if respuesta.status != 200:
            raise ErrorProveedorImagen("El proveedor de imágenes no está disponible. Inténtalo de nuevo.")

        tipo = respuesta.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
        contenido = bytearray()
        while monotonic() < plazo:
            parte = respuesta.read1(min(64 * 1024, MAX_BYTES_TESELA + 1 - len(contenido)))
            if not parte:
                return tipo, bytes(contenido)
            contenido.extend(parte)
            if len(contenido) > MAX_BYTES_TESELA:
                raise ErrorProveedorImagen("El proveedor devolvió una tesela demasiado grande.")
    raise ErrorProveedorImagen("Se agotó el tiempo de espera del proveedor de imágenes.")


def leer_tesela(tipo: str, contenido: bytes) -> np.ndarray | None:
    if tipo == "image/png" and contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        formato = "PNG"
    elif tipo == "image/jpeg" and contenido.startswith(b"\xff\xd8") and contenido.endswith(b"\xff\xd9"):
        formato = "JPEG"
    else:
        raise ErrorProveedorImagen("El proveedor devolvió un formato de imagen inesperado.")

    try:
        with MemoryFile(contenido) as memoria, memoria.open() as tesela:
            if tesela.driver != formato or tesela.shape != (ANCHO_TESELA, ANCHO_TESELA):
                raise ErrorProveedorImagen("El proveedor devolvió una tesela con dimensiones inválidas.")
            # El IGN devuelve PNG transparentes o JPEG uniformes en zonas sin imagen.
            if formato == "PNG" and not tesela.dataset_mask().any():
                return None
            if formato != "JPEG" or tesela.count != 3 or tesela.dtypes != ("uint8",) * 3:
                raise ErrorProveedorImagen("El proveedor devolvió una tesela con formato inesperado.")
            rgb = tesela.read()
    except RasterioError as error:
        raise ErrorProveedorImagen("No se pudo leer una tesela del proveedor de imágenes.") from error

    return rgb if np.any(rgb != rgb[:, :1, :1]) else None


def cargar_mosaico(columnas_y_filas: tuple[int, int, int, int]) -> np.ndarray:
    columna_ini, fila_ini, columna_fin, fila_fin = columnas_y_filas
    ancho = (columna_fin - columna_ini + 1) * ANCHO_TESELA
    alto = (fila_fin - fila_ini + 1) * ANCHO_TESELA
    mosaico = np.zeros((4, alto, ancho), dtype=np.uint8)
    plazo = monotonic() + TIEMPO_ESPERA_TOTAL

    try:
        with closing(HTTPSConnection(DOMINIO_IGN)) as conexion:
            for fila in range(fila_ini, fila_fin + 1):
                for columna in range(columna_ini, columna_fin + 1):
                    respuesta = descargar_tesela(conexion, columna, fila, plazo)
                    rgb = leer_tesela(*respuesta) if respuesta is not None else None
                    if rgb is not None:
                        primero_y = (fila - fila_ini) * ANCHO_TESELA
                        primero_x = (columna - columna_ini) * ANCHO_TESELA
                        ventana = mosaico[:, primero_y:primero_y + ANCHO_TESELA, primero_x:primero_x + ANCHO_TESELA]
                        ventana[:3] = rgb
                        ventana[3] = 255
    except (OSError, ErrorHTTP) as error:
        raise ErrorProveedorImagen("No se pudo obtener la imagen del proveedor. Inténtalo de nuevo.") from error
    return mosaico


def generar_recorte_satelital(latitud: float, longitud: float, radio_m: float) -> bytes:
    if not 50 <= radio_m <= 2000:
        raise ValueError("El radio para analizar con IA debe estar entre 50 y 2000 m.")
    este, norte = PROYECTAR_CENTRO.transform(longitud, latitud)
    if not isfinite(este) or not isfinite(norte):
        raise ValueError(SIN_COBERTURA)
    circulo = Point(este, norte).buffer(radio_m)
    limites_teselas = teselas_del_recorte(circulo.bounds)
    mosaico = cargar_mosaico(limites_teselas)
    columna, fila = limites_teselas[:2]
    origen_mosaico = from_origin(
        -EXTREMO_WEB + columna * METROS_TESELA_WEB,
        EXTREMO_WEB - fila * METROS_TESELA_WEB,
        METROS_PIXEL_WEB, METROS_PIXEL_WEB,
    )
    lado = ceil(2 * radio_m / METROS_PIXEL_RECORTE)
    medio_lado = lado * METROS_PIXEL_RECORTE / 2
    origen_recorte = from_origin(este - medio_lado, norte + medio_lado, METROS_PIXEL_RECORTE, METROS_PIXEL_RECORTE)
    recorte = np.zeros((4, lado, lado), dtype=np.uint8)
    reproject(
        mosaico, recorte, src_transform=origen_mosaico, src_crs=CRS_WEB,
        dst_transform=origen_recorte, dst_crs=CRS_PROYECTADO, src_alpha=4, dst_alpha=4,
        resampling=Resampling.bilinear,
    )
    mascara = geometry_mask([circulo], out_shape=(lado, lado), transform=origen_recorte, invert=True)
    rgb = recorte[:3]
    pixeles = rgb[:, mascara]
    if not recorte[3, mascara].all() or not np.any(pixeles != pixeles[:, :1]):
        raise ValueError(SIN_COBERTURA)
    rgb[:, ~mascara] = 0

    with MemoryFile() as memoria:
        with memoria.open(
            driver="GTiff", width=lado, height=lado, count=3, dtype="uint8",
            crs=CRS_PROYECTADO, transform=origen_recorte, photometric="RGB", compress="deflate",
        ) as tiff:
            tiff.write(rgb)
        return memoria.read()
