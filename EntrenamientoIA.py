import tensorflow as tf
from tensorflow.keras import layers, models
import geopandas as gpd
import numpy as np
import rasterio

# ==========================================
# 1. PREPARACIÓN DE DATOS DESDE TU GEOPACKAGE
# ==========================================
ruta_gpkg = "/home/Jose/PycharmProjects/ProyectoSIE/ProyectoToniSolar_Resultados.gpkg"
nombre_capa = "Areas_Analizadas_Aptitud_SortC"

gdf = gpd.read_file(ruta_gpkg, layer=nombre_capa)

mapa_aptitud = {"Buenos": 0, "Normales": 1, "Malos": 2}
gdf['etiqueta_aptitud'] = gdf['Aptitud_Solar'].map(mapa_aptitud)

mapa_prohibido = {"No": 0, "Sí": 1}
gdf['etiqueta_prohibido'] = gdf['Lugar_Prohibido'].map(mapa_prohibido)

rutas_imagenes = gdf['ruta_imagen_asociada'].values
etiquetas_aptitud = gdf['etiqueta_aptitud'].values
etiquetas_prohibido = gdf['etiqueta_prohibido'].values

alto_img, ancho_img = 128, 128


def leer_tif_python(ruta_tensor):
    ruta = ruta_tensor.decode('utf-8')
    with rasterio.open(ruta) as src:
        img = src.read()  # Formato (bandas, alto, ancho)

        if img.shape[0] == 1:
            img = np.repeat(img, 3, axis=0)
        else:
            img = img[:3, :, :]

        img = np.transpose(img, (1, 2, 0)).astype(np.float32)

        img_resized = tf.image.resize(img, [alto_img, ancho_img]).numpy()
        return img_resized


def procesar_imagen_y_etiquetas(ruta, aptitud, prohibido):
    imagen = tf.numpy_function(leer_tif_python, [ruta], tf.float32)

    imagen.set_shape([alto_img, ancho_img, 3])

    max_val = tf.reduce_max(imagen)
    imagen = tf.cond(max_val > 0, lambda: imagen / max_val, lambda: imagen)

    return imagen, {'salida_prohibido': prohibido, 'salida_aptitud': aptitud}

dataset = tf.data.Dataset.from_tensor_slices((rutas_imagenes, etiquetas_aptitud, etiquetas_prohibido))
dataset = dataset.map(procesar_imagen_y_etiquetas, num_parallel_calls=tf.data.AUTOTUNE)


total_datos = len(gdf)
tamano_entrenamiento = int(0.8 * total_datos)

train_dataset = dataset.take(tamano_entrenamiento).shuffle(1000).batch(32).prefetch(tf.data.AUTOTUNE)
val_dataset = dataset.skip(tamano_entrenamiento).batch(32).prefetch(tf.data.AUTOTUNE)

dataset = dataset.shuffle(1000)
# ==========================================f
# 2. ARQUITECTURA DEL MODELO (API FUNCIONAL)
# ==========================================
# Entrada
entrada = layers.Input(shape=(alto_img, ancho_img, 3), name='entrada_imagen')

x = layers.Conv2D(32, (3, 3), padding='same', activation='relu')(entrada)
x = layers.MaxPooling2D()(x)
x = layers.Conv2D(64, (3, 3), padding='same', activation='relu')(x)
x = layers.MaxPooling2D()(x)
x = layers.Conv2D(128, (3, 3), padding='same', activation='relu')(x)
x = layers.MaxPooling2D()(x)

tronco_aplanado = layers.Flatten()(x)
tronco_aplanado = layers.Dropout(0.5)(tronco_aplanado)

# --- RAMA 1 ---
rama_prohibido = layers.Dense(64, activation='relu')(tronco_aplanado)
rama_prohibido = layers.Dropout(0.3)(rama_prohibido)
salida_prohibido = layers.Dense(1, activation='sigmoid', name='salida_prohibido')(rama_prohibido)

# --- RAMA 2 ---
rama_aptitud = layers.Dense(64, activation='relu')(tronco_aplanado)
rama_aptitud = layers.Dropout(0.3)(rama_aptitud)
salida_aptitud = layers.Dense(3, activation='softmax', name='salida_aptitud')(rama_aptitud)

modelo = models.Model(inputs=entrada, outputs=[salida_prohibido, salida_aptitud])

# ==========================================
# 3. COMPILACIÓN DEL MODELO
# ==========================================
modelo.compile(
    optimizer='adam',
    loss={
        'salida_prohibido': 'binary_crossentropy',
        'salida_aptitud': 'sparse_categorical_crossentropy'
    },
    metrics={
        'salida_prohibido': ['accuracy'],
        'salida_aptitud': ['accuracy']
    }
)

modelo.summary()

# ==========================================
# 4. ENTRENAMIENTO
# ==========================================
parada_temprana = tf.keras.callbacks.EarlyStopping(
    monitor='val_loss',
    patience=3, # Si en 3 épocas seguidas no mejora la validación, se detiene
    restore_best_weights=True # Se queda con la mejor versión, no con la última
)

historial = modelo.fit(
    train_dataset,
    validation_data=val_dataset,
    epochs=20,
    callbacks=[parada_temprana]
)

modelo.save("/home/Jose/modelo_multitarea_solar.keras")
print("\nModelo guardado correctamente en /home/Jose/modelo_multitarea_solar2.keras")