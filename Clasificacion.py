import numpy as np
import geopandas as gpd

# ==========================================
# 1. CARGAR LA CAPA DE RESULTADOS
# ==========================================
ruta_gpkg =
nombre_capa = "Areas_Analizadas"
gdf = gpd.read_file(ruta_gpkg, layer=nombre_capa)

# ==========================================
# 2. DEFINIR LOS CRITERIOS PARA SOLAR
# ==========================================
columnas_criterios = [
    'dist_carreteras_m',
    'dist_red_electrica_m',
    'num_curvas_cruzadas',
    'irradiacion_media_vector'
]

Aclasificar = gdf[columnas_criterios].fillna(0).to_numpy(dtype=float)
num_alternativas = Aclasificar.shape[0]
criterios = 4

# ==========================================
# 3. PARÁMETROS DE TOPSIS PARA RENOVABLES
# ==========================================
nombregrupo = ["Malos", "Normales", "Buenos"]
pesos = np.array([0.08139958032186938, 0.04221141616780158, 0.21933385831425337, 0.6570551451960757])

# C = Coste (Minimizar), B = Beneficio (Maximizar)
benef = np.array(["C", "C", "C", "B"])

# ==========================================
# 4. CONSTRUIR MATRIZ CON PERFILES CENTRALES (TOPSIS-Sort-C)
# ==========================================
maximos_reales = np.max(Aclasificar, axis=0)
minimos_reales = np.min(Aclasificar, axis=0)

perfil_ideal_teorico = np.empty(criterios)
perfil_peor_teorico = np.empty(criterios)

for j in range(criterios):
    if benef[j] == "B":
        perfil_ideal_teorico[j] = maximos_reales[j] * 1.2
        perfil_peor_teorico[j] = minimos_reales[j] * 0.8
    else:
        perfil_ideal_teorico[j] = minimos_reales[j] * 0.8
        perfil_peor_teorico[j] = maximos_reales[j] * 1.2

# AQUÍ DEFINIMOS LOS PERFILES TÍPICOS DE CADA CLASE
# [Dist. Carretera, Dist. Red, Curvas, Irradiación]
perfil_tipico_malo = [1000, 1500, 5, 1500]
perfil_tipico_normal = [500, 700, 3, 1600]
perfil_tipico_bueno = [200, 300, 1, 1650]

perfiles = np.array([
    perfil_peor_teorico,
    perfil_ideal_teorico,
    perfil_tipico_malo,
    perfil_tipico_normal,
    perfil_tipico_bueno
], dtype=float)

matr = np.vstack((perfiles, Aclasificar))

# ==========================================
# 5. NORMALIZACIÓN
# ==========================================
total_filas = matr.shape[0]
normalizado = np.empty((total_filas, criterios))

for j in range(criterios):
    columna = matr[:, j]
    mini = np.min(columna)
    maxi = np.max(columna)

    rango = maxi - mini
    if rango == 0:
        normalizado[:, j] = 0
    else:
        if benef[j] == "B":
            normalizado[:, j] = (columna - mini) / rango
        else:
            normalizado[:, j] = (maxi - columna) / rango

# ==========================================
# 6. MATRIZ PONDERADA E IDEALES
# ==========================================
matrizponderada = normalizado * pesos

idealactionIdeal = np.max(matrizponderada, axis=0)
antidealactionIdeal = np.min(matrizponderada, axis=0)

# ==========================================
# 7. CÁLCULO DE DISTANCIAS
# ==========================================
distanciasposideal = np.sqrt(np.sum((matrizponderada - idealactionIdeal) ** 2, axis=1))
distanciasnegideal = np.sqrt(np.sum((matrizponderada - antidealactionIdeal) ** 2, axis=1))

distanciasrelativasideal = distanciasnegideal / (distanciasposideal + distanciasnegideal)

# ==========================================
# 8. CLASIFICACIÓN (PUNTOS MEDIOS) Y REGLA DE VETO
# ==========================================
puntuacion_malo = distanciasrelativasideal[2]
puntuacion_normal = distanciasrelativasideal[3]
puntuacion_bueno = distanciasrelativasideal[4]

limite_malo_normal = (puntuacion_malo + puntuacion_normal) / 2
limite_normal_bueno = (puntuacion_normal + puntuacion_bueno) / 2

print("--- PUNTUACIONES DE PERFILES CENTRALES ---")
print(f"Modelo Malo:   {puntuacion_malo:.4f}")
print(f"Modelo Normal: {puntuacion_normal:.4f}")
print(f"Modelo Bueno:  {puntuacion_bueno:.4f}")
print("--- LÍMITES CALCULADOS ---")
print(f"Límite Malo -> Normal:  {limite_malo_normal:.4f}")
print(f"Límite Normal -> Bueno: {limite_normal_bueno:.4f}")

grupos_asignados = []
puntuaciones_finales = []
estado_prohibido = []

for i in range(num_alternativas):
    idx_matriz = i + 5
    puntuacion = distanciasrelativasideal[idx_matriz]

    if puntuacion < limite_malo_normal:
        grupo = nombregrupo[0]
    elif puntuacion < limite_normal_bueno:
        grupo = nombregrupo[1]
    else:
        grupo = nombregrupo[2]

    es_red_natura = gdf.iloc[i]['en_red_natura']
    uso_suelo = gdf.iloc[i]['valorSuelo']

    if es_red_natura == True and (uso_suelo == 2 or uso_suelo == 3):
        prohibido = "Sí"
    else:
        prohibido = "No"

    grupos_asignados.append(grupo)
    puntuaciones_finales.append(puntuacion)
    estado_prohibido.append(prohibido)

# ==========================================
# 9. GUARDAR RESULTADOS
# ==========================================
gdf['Aptitud_Solar'] = grupos_asignados
gdf['Puntuacion_TOPSIS'] = puntuaciones_finales
gdf['Lugar_Prohibido'] = estado_prohibido

nombre_nueva_capa = f"{nombre_capa}_Aptitud_SortC"
gdf.to_file(ruta_gpkg, layer=nombre_nueva_capa, driver="GPKG")

print(f"\n¡Clasificación por perfiles centrales finalizada! Revisa la capa '{nombre_nueva_capa}'")
print("\nResumen de parcelas según aptitud pura:")
print(gdf['Aptitud_Solar'].value_counts())
print("\nResumen de parcelas según prohibición:")
print(gdf['Lugar_Prohibido'].value_counts())