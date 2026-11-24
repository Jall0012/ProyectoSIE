import geopandas as gpd
import numpy as np

# ==========================================
# 1. CONFIGURACIÓN Y CARGA DE CAPAS BASE
# ==========================================
RUTA_GPKG_BASE = "/home/Jose/ProyectoToniSolar.gpkg"
CRS_PROYECTADO = "EPSG:25830"
COLUMNA_VALOR_MALLA = "_mean"

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

def cargar_capas_base(ruta_gpkg, crs):
    """Carga y reproyecta una sola vez las capas de referencia."""
    print("Cargando capas base...")
    capas = {
        "electrica": gpd.read_file(ruta_gpkg, layer="redElectrica"),
        "carreteras": gpd.read_file(ruta_gpkg, layer="redcarreteras"),
        "curvas": gpd.read_file(ruta_gpkg, layer="CurvaNivel"),
        "malla": gpd.read_file(ruta_gpkg, layer="IrradiaciónMedia"),
        "usos": gpd.read_file(ruta_gpkg, layer="UsoSuelo"),
        "natura": gpd.read_file(ruta_gpkg, layer="RedNatura"),
    }

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


# ==========================================
# 2. FUNCIÓN PRINCIPAL DE CÁLCULO Y TOPSIS
# ==========================================
def clasificar_area(gdf_area, capas_base, crs=CRS_PROYECTADO):
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
        a_malla = gpd.sjoin(area[['geometry']], capas_base["malla"][['geometry', COLUMNA_VALOR_MALLA]], how="left", predicate="intersects")
        area['irradiacion_media'] = a_malla.groupby(a_malla.index)[COLUMNA_VALOR_MALLA].mean()
    else:
        raise KeyError(f"No se encontró la columna '{COLUMNA_VALOR_MALLA}' en IrradiaciónMedia.")

    # 5. Intersección con Red Natura
    a_natura = gpd.sjoin(area[['geometry']], capas_base["natura"][['geometry']], how="inner", predicate="intersects")
    area['en_red_natura'] = area.index.isin(a_natura.index.unique())

    # 6. Mayor valor de uso de suelo superpuesto
    a_usos = gpd.sjoin(area[['geometry']], capas_base["usos"][['geometry', 'valor_numerico']], how="left", predicate="intersects")
    area['valorSuelo'] = a_usos.groupby(a_usos.index)['valor_numerico'].max()

    # --- B. MODELO TOPSIS ---
    columnas_criterios = [
        'dist_carreteras_m',
        'dist_red_electrica_m',
        'num_curvas_cruzadas',
        'irradiacion_media'
    ]
    Aclasificar = area[columnas_criterios].fillna(0).to_numpy(dtype=float)
    num_alternativas = Aclasificar.shape[0]
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

    # --- C. CLASIFICACIÓN Y REGLA DE VETO ---
    grupos, puntuaciones = [], []
    for i in range(num_alternativas):
        puntuacion = dist_rel[i + 4]

        if puntuacion < limite_1:
            grupo = nombregrupo[0]
        elif puntuacion < limite_2:
            grupo = nombregrupo[1]
        else:
            grupo = nombregrupo[2]

        es_red_natura = area.iloc[i]['en_red_natura']
        uso_suelo = area.iloc[i]['valorSuelo']

        if es_red_natura and uso_suelo in (2, 3):
            grupo = "Lugar prohibido"
            puntuacion = 0.0

        grupos.append(grupo)
        puntuaciones.append(puntuacion)

    area['Aptitud_Solar'] = grupos
    area['Puntuacion_TOPSIS'] = puntuaciones

    return area
