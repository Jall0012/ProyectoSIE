import argparse
import json
from pathlib import Path
from typing import TypedDict

from osgeo import gdal, ogr, osr


RUTA_GEOPACKAGE = Path("/workspace/shared/proyectosie-data/datosjaenv1.gpkg")
CAPA_IRRADIACION = "IrradiaciónMedia"
CAMPO_IRRADIACION = "_mean"


class Coincidencia(TypedDict):
    fid: int
    _mean: float | None


def crear_referencia(epsg: int) -> osr.SpatialReference:
    referencia = osr.SpatialReference()
    referencia.ImportFromEPSG(epsg)
    referencia.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return referencia


def proyectar_punto(latitud: float, longitud: float) -> ogr.Geometry:
    if not (-90 <= latitud <= 90 and -180 <= longitud <= 180):
        raise ValueError("La latitud debe estar entre -90 y 90 y la longitud entre -180 y 180.")

    # La CLI recibe latitud y longitud. OGR usa X = longitud e Y = latitud.
    origen = crear_referencia(4326)
    destino = crear_referencia(25830)
    transformacion = osr.CoordinateTransformation(origen, destino)
    este, norte, _ = transformacion.TransformPoint(longitud, latitud)

    punto = ogr.Geometry(ogr.wkbPoint)
    punto.AddPoint_2D(este, norte)
    return punto


def buscar_coincidencias(capa: ogr.Layer, punto: ogr.Geometry) -> list[Coincidencia]:
    # El filtro espacial limita los candidatos. Intersects comprueba la geometría
    # exacta e incluye un punto situado en el borde de uno o más polígonos.
    coincidencias: list[Coincidencia] = []
    capa.SetSpatialFilter(punto)
    try:
        for entidad in capa:
            geometria = entidad.GetGeometryRef()
            if geometria is not None and geometria.Intersects(punto):
                coincidencias.append({
                    "fid": entidad.GetFID(),
                    "_mean": entidad.GetField(CAMPO_IRRADIACION),
                })
    finally:
        capa.SetSpatialFilter(None)

    return sorted(coincidencias, key=lambda coincidencia: coincidencia["fid"])


def consultar_irradiacion(
    ruta_geopackage: Path, latitud: float, longitud: float
) -> list[Coincidencia]:
    with gdal.ExceptionMgr(), ogr.ExceptionMgr(), osr.ExceptionMgr():
        punto = proyectar_punto(latitud, longitud)

        # Abrir el GeoPackage sin permiso de escritura.
        with gdal.OpenEx(
            str(ruta_geopackage), gdal.OF_VECTOR | gdal.OF_READONLY, allowed_drivers=["GPKG"]
        ) as datos:
            capa = datos.GetLayerByName(CAPA_IRRADIACION)
            if capa is None:
                raise ValueError(f"No se encontró la capa «{CAPA_IRRADIACION}».")
            referencia = capa.GetSpatialRef()
            if referencia is None or not referencia.IsSame(crear_referencia(25830)):
                raise ValueError(f"La capa «{CAPA_IRRADIACION}» debe estar en EPSG:25830.")
            if capa.GetLayerDefn().GetFieldIndex(CAMPO_IRRADIACION) < 0:
                raise ValueError(f"No se encontró el campo {CAMPO_IRRADIACION}.")

            return buscar_coincidencias(capa, punto)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Consulta la irradiación media de un punto WGS84."
    )
    parser.add_argument("latitud", type=float, help="Latitud en grados decimales")
    parser.add_argument("longitud", type=float, help="Longitud en grados decimales")
    parser.add_argument("--gpkg", type=Path, default=RUTA_GEOPACKAGE, help="Ruta al GeoPackage")
    argumentos = parser.parse_args()

    try:
        coincidencias = consultar_irradiacion(
            argumentos.gpkg, argumentos.latitud, argumentos.longitud
        )
    except (RuntimeError, ValueError) as error:
        parser.exit(1, f"Error: {error}\n")

    print(json.dumps(coincidencias, indent=2))


if __name__ == "__main__":
    main()
