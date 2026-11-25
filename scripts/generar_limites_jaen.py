import argparse
import json
from pathlib import Path
from urllib.request import urlopen

import geopandas as gpd
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from scripts.generar_mapa_jaen import elemento_geojson


URL_PROVINCIA = "https://api-features.ign.es/collections/administrativeunit/items?nationalcode=34012300000"


def limite_provincial() -> BaseGeometry:
    with urlopen(URL_PROVINCIA, timeout=30) as respuesta:
        elementos = json.load(respuesta)["features"]
    if len(elementos) != 1 or elementos[0]["properties"]["nationallevelname"] != "Provincia":
        raise ValueError("El servicio del IGN debe devolver un único recinto provincial de Jaén.")
    recinto = gpd.GeoSeries([shape(elementos[0]["geometry"])], crs=4326).to_crs(25830).iloc[0]
    return recinto.simplify(25, preserve_topology=True)


def main() -> None:
    argumentos = argparse.ArgumentParser(description="Genera el límite provincial de Jaén.")
    argumentos.add_argument("destino", type=Path, help="Ruta del GeoJSON que genera el script.")
    opciones = argumentos.parse_args()
    provincia = elemento_geojson("provincia", limite_provincial())
    provincia["properties"] = {
        "capa": "provincia",
        "fuente": URL_PROVINCIA,
        "atribucion": "Obra derivada de BDLJE CC-BY 4.0 ign.es",
        "descripcion": "Recinto provincial de Jaén simplificado con tolerancia de 25 m.",
    }
    with opciones.destino.open("w", encoding="utf-8") as salida:
        json.dump({"type": "FeatureCollection", "features": [provincia]}, salida, separators=(",", ":"))
        salida.write("\n")


if __name__ == "__main__":
    main()
