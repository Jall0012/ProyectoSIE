import argparse
import json
from operator import itemgetter
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


def consultar_irradiacion(
    ruta_geopackage: Path, latitud: float, longitud: float
) -> list[Coincidencia]:
    if not (-90 <= latitud <= 90 and -180 <= longitud <= 180):
        raise ValueError("La latitud debe estar entre -90 y 90 y la longitud entre -180 y 180.")

    coincidencias: list[Coincidencia] = []
    with gdal.ExceptionMgr(), ogr.ExceptionMgr(), osr.ExceptionMgr():
        destino = crear_referencia(25830)
        transformacion = osr.CoordinateTransformation(crear_referencia(4326), destino)
        # OGR recibe longitud antes que latitud.
        este, norte, _ = transformacion.TransformPoint(longitud, latitud)
        punto = ogr.Geometry(ogr.wkbPoint)
        punto.AddPoint_2D(este, norte)

        with gdal.OpenEx(
            str(ruta_geopackage), gdal.OF_VECTOR | gdal.OF_READONLY, allowed_drivers=["GPKG"]
        ) as datos:
            capa = datos.GetLayerByName(CAPA_IRRADIACION)
            if capa is None:
                raise ValueError(f"No se encontró la capa «{CAPA_IRRADIACION}».")
            referencia = capa.GetSpatialRef()
            if referencia is None or not referencia.IsSame(destino):
                raise ValueError(f"La capa «{CAPA_IRRADIACION}» debe estar en EPSG:25830.")
            if capa.GetLayerDefn().GetFieldIndex(CAMPO_IRRADIACION) < 0:
                raise ValueError(f"No se encontró el campo {CAMPO_IRRADIACION}.")

            # El índice acota la búsqueda y la intersección incluye los bordes.
            capa.SetSpatialFilter(punto)
            for entidad in capa:
                geometria = entidad.GetGeometryRef()
                if geometria is not None and geometria.Intersects(punto):
                    coincidencias.append({
                        "fid": entidad.GetFID(),
                        "_mean": entidad.GetField(CAMPO_IRRADIACION),
                    })

    return sorted(coincidencias, key=itemgetter("fid"))


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
