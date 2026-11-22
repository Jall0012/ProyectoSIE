import geopandas as gpd
import numpy as np
import rasterio
from rasterio.mask import mask
import os

# ==========================================
# 1. CONFIGURACIÓN INICIAL Y RUTAS
# ==========================================
ruta_gpkg =
ruta_salida =
crs_proyectado = "EPSG:25830"

ruta_tif =
carpeta_recortes_tif =
os.makedirs(carpeta_recortes_tif, exist_ok=True)

# ==========================================
# 2. CARGA DE TODAS LAS CAPAS
# ==========================================
print("Cargando capas...")
gdf_areas = gpd.read_file(ruta_gpkg, layer="AreasEjemplo")
gdf_electrica = gpd.read_file(ruta_gpkg, layer="redElectrica")
gdf_carreteras = gpd.read_file(ruta_gpkg, layer="redcarreteras")
gdf_curvas = gpd.read_file(ruta_gpkg, layer="CurvaNivel")
gdf_malla = gpd.read_file(ruta_gpkg, layer="IrradiaciónMedia")
gdf_usos = gpd.read_file(ruta_gpkg, layer="UsoSuelo")
gdf_natura = gpd.read_file(ruta_gpkg, layer="RedNatura")

# ==========================================
# 3. REPROYECCIÓN (CRS MÉTRICO)
# ==========================================
print("Comprobando y ajustando CRS...")
capas = [gdf_areas, gdf_electrica, gdf_carreteras, gdf_curvas, gdf_malla, gdf_usos, gdf_natura]
for i in range(len(capas)):
    if capas[i].crs != crs_proyectado:
        capas[i] = capas[i].to_crs(crs_proyectado)

gdf_areas, gdf_electrica, gdf_carreteras, gdf_curvas, gdf_malla, gdf_usos, gdf_natura = capas

# ==========================================
# 4. ANÁLISIS 1 y 2: DISTANCIAS A REDES
# ==========================================
print("Calculando distancias a Red Eléctrica y Carreteras...")
temp_electrica = gpd.sjoin_nearest(gdf_areas, gdf_electrica[['geometry']], how="left",
                                   distance_col="dist_red_electrica_m")
temp_electrica = temp_electrica[~temp_electrica.index.duplicated(keep='first')]
gdf_areas['dist_red_electrica_m'] = temp_electrica['dist_red_electrica_m']

temp_carreteras = gpd.sjoin_nearest(gdf_areas, gdf_carreteras[['geometry']], how="left",
                                    distance_col="dist_carreteras_m")
temp_carreteras = temp_carreteras[~temp_carreteras.index.duplicated(keep='first')]
gdf_areas['dist_carreteras_m'] = temp_carreteras['dist_carreteras_m']

# ==========================================
# 5. ANÁLISIS 3: CONTEO DE CURVAS DE NIVEL
# ==========================================
print("Calculando conteo de curvas de nivel...")
areas_y_curvas = gpd.sjoin(gdf_areas[['geometry']], gdf_curvas[['geometry']], how="left", predicate="intersects")
gdf_areas['num_curvas_cruzadas'] = areas_y_curvas.groupby(areas_y_curvas.index)['index_right'].count()

# ==========================================
# 6. ANÁLISIS 4: MEDIA DE IRRADIACIÓN (MALLA VECTORIAL)
# ==========================================
print("Calculando irradiación media de la malla vectorial...")
columna_valor_malla = "_mean"  # Recuerda cambiar esto por el nombre real
if columna_valor_malla in gdf_malla.columns:
    areas_y_malla = gpd.sjoin(gdf_areas[['geometry']], gdf_malla[['geometry', columna_valor_malla]], how="left",
                              predicate="intersects")
    gdf_areas['irradiacion_media_vector'] = areas_y_malla.groupby(areas_y_malla.index)[columna_valor_malla].mean()

# ==========================================
# 7. ANÁLISIS 5: BOOLEANO RED NATURA
# ==========================================
print("Calculando intersección con Red Natura...")
intersecciones_natura = gpd.sjoin(gdf_areas[['geometry']], gdf_natura[['geometry']], how="inner",
                                  predicate="intersects")
gdf_areas['en_red_natura'] = gdf_areas.index.isin(intersecciones_natura.index.unique())

# ==========================================
# 8. ANÁLISIS 6: RECLASIFICACIÓN DE USOS DE SUELO
# ==========================================
print("Reclasificando capa de Usos del Suelo...")
diccionario_valores = {
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

if 'uso_suelo' in gdf_usos.columns:
    gdf_usos['uso_suelo'] = gdf_usos['uso_suelo'].str.strip()
    gdf_usos['valor_numerico'] = gdf_usos['uso_suelo'].map(diccionario_valores)
else:
    print("Aviso: No se encontró la columna 'uso_suelo' en la capa UsoSuelo.")

# ==========================================
# 9. ANÁLISIS 7: MAYOR VALOR DE SUELO SUPERPUESTO
# ==========================================
print("Calculando el mayor valor de uso de suelo superpuesto...")
if 'valor_numerico' in gdf_usos.columns:
    areas_y_usos = gpd.sjoin(gdf_areas[['geometry']], gdf_usos[['geometry', 'valor_numerico']], how="left",
                             predicate="intersects")
    gdf_areas['valorSuelo'] = areas_y_usos.groupby(areas_y_usos.index)['valor_numerico'].max()

# ==========================================
# 10. ANÁLISIS 8: ASOCIAR IMAGEN TIF A CADA POLÍGONO (NUEVO)
# ==========================================
print("Procesando la imagen .tif superpuesta...")

valores_medios_tif = []
rutas_archivos_recortados = []

with rasterio.open(ruta_tif) as src:

    gdf_areas_tif = gdf_areas.to_crs(src.crs)

    for index, fila in gdf_areas_tif.iterrows():
        geometria = fila.geometry

        try:
            out_image, out_transform = mask(src, [geometria], crop=True)

            nodata_val = src.nodata
            if nodata_val is not None:
                pixeles_validos = out_image[out_image != nodata_val]
            else:
                pixeles_validos = out_image[out_image > 0]  # Omitimos el fondo negro (0)

            valor_medio = np.mean(pixeles_validos) if pixeles_validos.size > 0 else 0
            valores_medios_tif.append(valor_medio)

            # --- 2. GUARDAR LA IMAGEN RECORTADA EN DISCO ---
            out_meta = src.meta.copy()
            out_meta.update({
                "driver": "GTiff",
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform
            })

            nombre_salida = f"recorte_parcela_{index}.tif"
            ruta_recorte_final = os.path.join(carpeta_recortes_tif, nombre_salida)

            with rasterio.open(ruta_recorte_final, "w", **out_meta) as dest:
                dest.write(out_image)

            rutas_archivos_recortados.append(ruta_recorte_final)

        except ValueError:

            valores_medios_tif.append(0)
            rutas_archivos_recortados.append("Sin solape")

gdf_areas['valor_tif_superpuesto'] = valores_medios_tif
gdf_areas['ruta_imagen_asociada'] = rutas_archivos_recortados

# ==========================================
# 11. GUARDAR RESULTADOS
# ==========================================
print("Guardando resultados en un nuevo GeoPackage...")
gdf_areas.to_file(ruta_salida, layer="Areas_Analizadas", driver="GPKG")
gdf_usos.to_file(ruta_salida, layer="UsoSuelo_Valorado", driver="GPKG")

print(f"\n¡Proceso completado con éxito! Archivos guardados.")
print(f"- Base de datos vectorial: {ruta_salida}")
print(f"- Imágenes individuales: {carpeta_recortes_tif}")