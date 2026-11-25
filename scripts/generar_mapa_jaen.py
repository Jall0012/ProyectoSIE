import argparse
import json
from pathlib import Path

import geopandas as gpd
from shapely import get_parts, line_merge, orient_polygons, set_precision, to_geojson, union_all
from shapely.geometry import MultiLineString, MultiPolygon
from shapely.geometry.base import BaseGeometry


def lineas_simplificadas(capa: gpd.GeoDataFrame, tolerancia_m: float) -> MultiLineString:
    partes = get_parts(capa.geometry.array)
    lineas = line_merge(MultiLineString(partes.tolist()))
    return MultiLineString(get_parts(lineas.simplify(tolerancia_m)).tolist())


def redondear_coordenadas(coordenadas: list | float) -> list | float:
    if isinstance(coordenadas, list):
        return [redondear_coordenadas(valor) for valor in coordenadas]
    return round(coordenadas, 5)


def elemento_geojson(categoria: str, geometria: BaseGeometry) -> dict[str, object]:
    geometria_wgs84 = gpd.GeoSeries([geometria], crs=25830).to_crs(4326).iloc[0]
    geometria_wgs84 = orient_polygons(set_precision(geometria_wgs84, 0.00001))
    datos = json.loads(to_geojson(geometria_wgs84))
    datos["coordinates"] = redondear_coordenadas(datos["coordinates"])
    return {"type": "Feature", "properties": {"capa": categoria}, "geometry": datos}


def generar_mapa(ruta_gpkg: Path, destino: Path) -> None:
    curvas = gpd.read_file(ruta_gpkg, layer="CurvaNivel", columns=["altura"]).to_crs(25830)
    carreteras = gpd.read_file(ruta_gpkg, layer="redcarreteras", columns=["jerarquia"]).to_crs(25830)
    suelo = gpd.read_file(ruta_gpkg, layer="UsoSuelo", columns=["uso_suelo"]).to_crs(25830)

    curvas_principales = curvas[curvas["altura"] % 200 == 0]
    vias_principales = carreteras["jerarquia"].isin(["Principal", "Primer orden"])
    tejido_urbano = suelo[suelo["uso_suelo"].str.strip().str.startswith("Tejido urbano", na=False)]
    urbano = union_all(tejido_urbano.geometry.array).simplify(12)
    urbano = MultiPolygon(get_parts(urbano).tolist())

    elementos = [
        elemento_geojson("curvas", lineas_simplificadas(curvas_principales, 85)),
        elemento_geojson("urbano", urbano),
        elemento_geojson("vias", lineas_simplificadas(carreteras[~vias_principales], 17)),
        elemento_geojson("principal", lineas_simplificadas(carreteras[vias_principales], 17)),
    ]
    with destino.open("w", encoding="utf-8") as salida:
        json.dump({"type": "FeatureCollection", "features": elementos}, salida, separators=(",", ":"))
        salida.write("\n")


def main() -> None:
    argumentos = argparse.ArgumentParser(description="Genera la cartografía web simplificada de Jaén.")
    argumentos.add_argument("gpkg", type=Path, help="Ruta a CapasUsadas.gpkg.")
    argumentos.add_argument("destino", type=Path, help="Ruta del GeoJSON que genera el script.")
    opciones = argumentos.parse_args()
    generar_mapa(opciones.gpkg, opciones.destino)


if __name__ == "__main__":
    main()
