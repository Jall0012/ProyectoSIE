import sqlite3
from contextlib import closing
from pathlib import Path

import geopandas as gpd
import numpy as np
from pyproj import Transformer
from shapely import from_wkb
from shapely.errors import GEOSException
from shapely.geometry import Point, Polygon

# ==========================================
# 1. CONFIGURACIÓN Y CARGA DE CAPAS BASE
# ==========================================
CRS_PROYECTADO = "EPSG:25830"
NOMBRE_CAPA_MALLA = "IrradiaciónMedia"
COLUMNA_VALOR_MALLA = "_mean"
TAMANOS_ENVOLVENTE_GPKG = (0, 32, 48, 48, 64)

DICCIONARIO_USOS = {
    "Sistemas agroforestales": 3, "Tejido urbano continuo": 3, "Tejido urbano discontinuo": 3,
    "Terrenos principalmente agrícolas, pero con importantes espacios de vegetación natural": 2,
    "Terrenos regados permanentemente": 2, "Tierras de labor en secano": 1, "Láminas de agua": 3,
    "Matorral boscoso de transición": 3, "Matorrales esclerófilos": 3, "Mosaico de cultivos": 2,
    "Olivares": 2, "Pastizales naturales": 2, "Prados y Praderas": 2,
    "Redes viarias, ferroviarias y terrenos asociados": 3, "Roquedo": 2, "Bosque mixto": 3,
    "Bosques de coníferas": 3, "Bosques de frondosas": 3,
    "Cultivos anuales asociados con cultivos permanentes": 2, "Cursos de agua": 3,
    "Escombreras y vertederos": 1, "Espacios con vegetación escasa": 1, "Frutales": 2,
    "Humedales y zonas pantanosas": 3, "Instalaciones deportivas y recreativas": 3
}

def cargar_capas_base(
    ruta_gpkg: str | Path, crs: str, *, incluir_malla: bool = True
) -> dict[str, gpd.GeoDataFrame]:
    """Carga y reproyecta una sola vez las capas de referencia."""
    print("Cargando capas base...")
    capas = {
        "electrica": gpd.read_file(ruta_gpkg, layer="redElectrica"),
        "carreteras": gpd.read_file(ruta_gpkg, layer="redcarreteras"),
        "curvas": gpd.read_file(ruta_gpkg, layer="CurvaNivel"),
        "usos": gpd.read_file(ruta_gpkg, layer="UsoSuelo"),
        "natura": gpd.read_file(ruta_gpkg, layer="RedNatura"),
    }
    if incluir_malla:
        capas["malla"] = gpd.read_file(ruta_gpkg, layer=NOMBRE_CAPA_MALLA)
    else:
        consultar_malla(ruta_gpkg, (0, 0, 0, 0))

    for nombre, gdf in capas.items():
        if gdf.crs != crs:
            capas[nombre] = gdf.to_crs(crs)

    # Reclasificar usos del suelo
    if 'uso_suelo' in capas["usos"].columns:
        capas["usos"]['uso_suelo'] = capas["usos"]['uso_suelo'].str.strip()
        capas["usos"]['valor_numerico'] = capas["usos"]['uso_suelo'].map(DICCIONARIO_USOS)
    else:
        raise KeyError("No se encontró la columna 'uso_suelo' en la capa UsoSuelo.")

    return capas


def consultar_malla(
    ruta_gpkg: str | Path, extension: tuple[float, float, float, float]
) -> gpd.GeoDataFrame:
    """Lee las celdas candidatas directamente con el índice RTree del GeoPackage."""
    uri = Path(ruta_gpkg).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as conexion:
        metadatos = conexion.execute(
            "SELECT column_name, srs_id FROM gpkg_geometry_columns WHERE table_name = ?",
            (NOMBRE_CAPA_MALLA,),
        ).fetchone()
        if metadatos is None or metadatos[1] != 25830:
            raise ValueError(f"La capa {NOMBRE_CAPA_MALLA} debe estar en {CRS_PROYECTADO}.")
        nombre_geometria = metadatos[0].replace('"', '""')
        nombre_indice = f"rtree_{NOMBRE_CAPA_MALLA}_{nombre_geometria}"
        min_x, min_y, max_x, max_y = extension
        filas = conexion.execute(
            f'''
            SELECT m."{COLUMNA_VALOR_MALLA}", m."{nombre_geometria}"
            FROM "{nombre_indice}" AS r
            CROSS JOIN "{NOMBRE_CAPA_MALLA}" AS m ON m.rowid = r.id
            WHERE r.minx <= ? AND r.maxx >= ? AND r.miny <= ? AND r.maxy >= ?
            ''',
            (max_x, min_x, max_y, min_y),
        ).fetchall()

    valores = np.array([valor for valor, _ in filas], dtype=float)
    geometrias = []
    for _, geometria in filas:
        # En GeoPackage, el WKB sigue a la cabecera y su envolvente opcional.
        codigo_envolvente = (geometria[3] >> 1) & 7
        inicio_wkb = 8 + TAMANOS_ENVOLVENTE_GPKG[codigo_envolvente]
        geometrias.append(geometria[inicio_wkb:])

    return gpd.GeoDataFrame(
        {COLUMNA_VALOR_MALLA: valores},
        geometry=from_wkb(geometrias),
        crs=CRS_PROYECTADO,
    )


def construir_circulo(latitud: float, longitud: float, radio_m: float) -> tuple[Point, Polygon] | None:
    """Proyecta un centro WGS84 y construye su círculo en metros."""
    if not (-90 <= latitud <= 90 and -180 <= longitud <= 180):
        raise ValueError("El centro debe tener coordenadas WGS84 válidas.")
    if not np.isfinite(radio_m) or radio_m <= 0:
        raise ValueError("El radio debe ser positivo y finito.")

    transformar = Transformer.from_crs("EPSG:4326", CRS_PROYECTADO, always_xy=True)
    este, norte = transformar.transform(longitud, latitud)
    if not np.isfinite((este, norte)).all():
        return None

    centro = Point(este, norte)
    try:
        circulo = centro.buffer(radio_m)
    except GEOSException as error:
        raise ValueError("El radio no permite construir un círculo en este centro.") from error
    if circulo.is_empty or not np.isfinite(circulo.area) or circulo.area <= 0:
        raise ValueError("El radio no permite construir un círculo en este centro.")
    return centro, circulo


def evaluar_circulo(
    latitud: float,
    longitud: float,
    radio_m: float,
    ruta_gpkg: str | Path,
    capas_base: dict[str, gpd.GeoDataFrame],
) -> tuple[str, float | None]:
    """Evalúa un círculo en metros a partir de un centro WGS84."""
    zona_proyectada = construir_circulo(latitud, longitud, radio_m)
    if zona_proyectada is None:
        return "Sin datos", None
    _, circulo = zona_proyectada

    malla = consultar_malla(ruta_gpkg, circulo.bounds)
    zona = gpd.GeoDataFrame(geometry=[circulo], crs=CRS_PROYECTADO)
    resultado = clasificar_area(zona, {**capas_base, "malla": malla}).iloc[0]
    puntuacion = resultado["Puntuacion_TOPSIS"]
    return str(resultado["Aptitud_Solar"]), float(puntuacion) if np.isfinite(puntuacion) else None


def buscar_zonas_cercanas(
    latitud: float,
    longitud: float,
    radio_m: float,
    alcance_km: int,
    ruta_gpkg: str | Path,
    capas_base: dict[str, gpd.GeoDataFrame],
) -> gpd.GeoDataFrame:
    """Ordena hasta tres zonas viables con una referencia TOPSIS común."""
    if alcance_km not in (1, 3, 5):
        raise ValueError("El alcance debe ser de 1, 3 o 5 km.")
    zona_proyectada = construir_circulo(latitud, longitud, radio_m)
    if zona_proyectada is None:
        return gpd.GeoDataFrame()
    centro, circulo = zona_proyectada
    alcance_m = alcance_km * 1000
    x, y = centro.x, centro.y
    zonas = gpd.read_file(
        ruta_gpkg, layer="AreasEjemplo", engine="pyogrio", columns=[], fid_as_index=True,
        bbox=(x - alcance_m, y - alcance_m, x + alcance_m, y + alcance_m),
    )
    if zonas.crs != CRS_PROYECTADO:
        raise ValueError(f"La capa AreasEjemplo debe estar en {CRS_PROYECTADO}.")

    zonas["id_zona"] = zonas.index
    zonas["distancia_m"] = zonas.geometry.centroid.distance(centro)
    cercanas = zonas.loc[zonas["distancia_m"] <= alcance_m]
    candidatas = cercanas.loc[cercanas.geometry.intersection(circulo).area == 0]
    if candidatas.empty:
        return candidatas

    min_x, min_y, max_x, max_y = candidatas.total_bounds
    malla = consultar_malla(ruta_gpkg, (min_x, min_y, max_x, max_y))
    resultados = clasificar_area(
        candidatas, {**capas_base, "malla": malla}, excluir_vetos_de_referencia=True,
    )
    recomendables = resultados.loc[resultados["Aptitud_Solar"].isin(("Buenos", "Normales"))]
    seleccionadas = recomendables.sort_values(
        ["Puntuacion_TOPSIS", "distancia_m", "id_zona"], ascending=[False, True, True],
    ).head(3).copy()
    centros = seleccionadas.geometry.centroid.to_crs("EPSG:4326")
    limites = seleccionadas.geometry.bounds
    seleccionadas["latitud"] = centros.y
    seleccionadas["longitud"] = centros.x
    # Las zonas circulares de AreasEjemplo tienen un radio entero en metros.
    seleccionadas["radio_m"] = ((limites["maxx"] - limites["minx"]) / 2).round()
    return seleccionadas.to_crs("EPSG:4326")


def solapes_con_superficie(
    area: gpd.GeoDataFrame, capa: gpd.GeoDataFrame, campo: str
) -> gpd.GeoDataFrame:
    capa = capa[[campo, "geometry"]].reset_index(drop=True)
    cruces = gpd.sjoin(area[["geometry"]], capa, how="inner", predicate="intersects")
    geometrias_capa = capa.geometry.iloc[cruces["index_right"].to_numpy()]
    superficie = cruces.geometry.intersection(geometrias_capa, align=False).area
    return cruces[(superficie > 0) & np.isfinite(cruces[campo])]


# ==========================================
# 2. FUNCIÓN PRINCIPAL DE CÁLCULO Y TOPSIS
# ==========================================
def clasificar_area(
    gdf_area: gpd.GeoDataFrame,
    capas_base: dict[str, gpd.GeoDataFrame],
    crs: str = CRS_PROYECTADO,
    *,
    excluir_vetos_de_referencia: bool = False,
) -> gpd.GeoDataFrame:
    """
    Recibe un GeoDataFrame con 1 (o varias) áreas, calcula las variables espaciales
    y devuelve su clasificación TOPSIS + regla de veto.
    """
    area = gdf_area.copy().reset_index(drop=True)
    if area.crs != crs:
        area = area.to_crs(crs)

    # --- A. CÁLCULO DE VARIABLES ESPACIALES ---
    # 1. Distancia a Red Eléctrica
    t_elec = gpd.sjoin_nearest(area, capas_base["electrica"][['geometry']], how="left", distance_col="dist_red_electrica_m")
    area['dist_red_electrica_m'] = t_elec[~t_elec.index.duplicated(keep='first')]['dist_red_electrica_m']

    # 2. Distancia a Carreteras
    t_carr = gpd.sjoin_nearest(area, capas_base["carreteras"][['geometry']], how="left", distance_col="dist_carreteras_m")
    area['dist_carreteras_m'] = t_carr[~t_carr.index.duplicated(keep='first')]['dist_carreteras_m']

    # 3. Conteo de curvas de nivel
    a_curvas = gpd.sjoin(area[['geometry']], capas_base["curvas"][['geometry']], how="left", predicate="intersects")
    area['num_curvas_cruzadas'] = a_curvas.groupby(a_curvas.index)['index_right'].count()

    # 4. Irradiación media (malla vectorial)
    if COLUMNA_VALOR_MALLA in capas_base["malla"].columns:
        a_malla = solapes_con_superficie(area, capas_base["malla"], COLUMNA_VALOR_MALLA)
        area['irradiacion_media'] = a_malla.groupby(a_malla.index)[COLUMNA_VALOR_MALLA].mean()
    else:
        raise KeyError(f"No se encontró la columna '{COLUMNA_VALOR_MALLA}' en IrradiaciónMedia.")

    # 5. Intersección con Red Natura
    a_natura = gpd.sjoin(area[['geometry']], capas_base["natura"][['geometry']], how="inner", predicate="intersects")
    area['en_red_natura'] = area.index.isin(a_natura.index.unique())

    # 6. Mayor valor de uso de suelo superpuesto
    a_usos = solapes_con_superficie(area, capas_base["usos"], "valor_numerico")
    area['valorSuelo'] = a_usos.groupby(a_usos.index)['valor_numerico'].max()

    # --- B. MODELO TOPSIS ---
    columnas_criterios = [
        'dist_carreteras_m',
        'dist_red_electrica_m',
        'num_curvas_cruzadas',
        'irradiacion_media'
    ]
    evaluables = np.isfinite(area[columnas_criterios + ["valorSuelo"]]).all(axis=1)
    vetadas = evaluables & area["en_red_natura"] & area["valorSuelo"].isin((2, 3))
    area["Aptitud_Solar"] = "Sin datos"
    area["Puntuacion_TOPSIS"] = np.nan
    area.loc[vetadas, "Aptitud_Solar"] = "Lugar prohibido"
    area.loc[vetadas, "Puntuacion_TOPSIS"] = 0.0
    referencia = evaluables & ~vetadas if excluir_vetos_de_referencia else evaluables
    if not referencia.any():
        return area
    alternativas = area.loc[referencia]
    Aclasificar = alternativas[columnas_criterios].to_numpy(dtype=float)
    criterios = 4

    nombregrupo = ["Malos", "Normales", "Buenos"]
    pesos = np.array([0.20, 0.35, 0.15, 0.30])
    benef = np.array(["C", "C", "C", "B"])

    # Perfiles límite fijos: [Carretera, Red, Curvas, Irradiacion]
    limites = np.array([
        [2000, 3000, 15, 1500],  # Límite Malos -> Normales
        [500, 1000, 5, 2000],    # Límite Normales -> Buenos
    ], dtype=float)

    # Ideal y anti-ideal calculados sobre (límites + área) para que no colapse con 1 sola parcela
    referencia_total = np.vstack((limites, Aclasificar))
    maximos = np.max(referencia_total, axis=0)
    minimos = np.min(referencia_total, axis=0)

    perfil_ideal = np.where(benef == "B", maximos * 1.2, minimos * 0.8)
    perfil_peor = np.where(benef == "B", minimos * 0.8, maximos * 1.2)

    perfiles = np.vstack((perfil_peor, perfil_ideal, limites))
    matr = np.vstack((perfiles, Aclasificar))

    # Normalización
    normalizado = np.empty_like(matr)
    for j in range(criterios):
        col = matr[:, j]
        mini, maxi = np.min(col), np.max(col)
        rango = maxi - mini
        if rango == 0:
            normalizado[:, j] = 0
        elif benef[j] == "B":
            normalizado[:, j] = (col - mini) / rango
        else:
            normalizado[:, j] = (maxi - col) / rango

    # Ponderación y distancias
    matrizponderada = normalizado * pesos
    ideal = np.max(matrizponderada, axis=0)
    antideal = np.min(matrizponderada, axis=0)

    dist_pos = np.sqrt(np.sum((matrizponderada - ideal) ** 2, axis=1))
    dist_neg = np.sqrt(np.sum((matrizponderada - antideal) ** 2, axis=1))
    dist_rel = dist_neg / (dist_pos + dist_neg)

    limite_1, limite_2 = dist_rel[2], dist_rel[3]

    # --- C. CLASIFICACIÓN DE LAS ZONAS SIN VETO ---
    puntuaciones = dist_rel[4:]
    grupos = np.select(
        [puntuaciones < limite_1, puntuaciones < limite_2], nombregrupo[:2], default=nombregrupo[2],
    )
    sin_veto = ~vetadas.loc[referencia].to_numpy()
    area.loc[referencia & ~vetadas, "Aptitud_Solar"] = grupos[sin_veto]
    area.loc[referencia & ~vetadas, "Puntuacion_TOPSIS"] = puntuaciones[sin_veto]

    return area
