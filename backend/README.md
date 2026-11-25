# Backend de ProyectoSIE

Desde la raíz del repositorio, con Python 3.12 y los archivos de las releases
guardados fuera del repositorio:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-backend.txt
export PROYECTOSIE_GPKG=/workspace/ProyectoSIE-datos/CapasUsadas.gpkg
export PROYECTOSIE_MODELO=/workspace/ProyectoSIE-datos/modelo_multitarea_solar.keras
export PROYECTOSIE_SENTINEL=/ruta/al/mosaico_sur_COG.tif
.venv/bin/python -m uvicorn backend.main:app
```

La documentación interactiva está en `http://127.0.0.1:8000/docs`.

| Método y ruta | Entrada | Resultado |
| --- | --- | --- |
| `GET /salud` | | Estado del servicio |
| `POST /evaluar-zona` | JSON con `latitud`, `longitud` y `radio_m` | Categoría y puntuación TOPSIS entre 0 y 1, o «Sin datos» con puntuación nula |
| `POST /analizar-imagen` | Campo multipart `archivo` con un TIFF | Categoría más probable, probabilidades de aptitud y probabilidad de veto |
| `POST /analizar-zona-imagen` | JSON con `latitud`, `longitud` y `radio_m` entre 50 y 2000 | Resultado de IA y `recorte_tiff` con el TIFF utilizado, en base64 |

El centro se indica en WGS84 y el radio en metros. El TIFF admite una banda o
al menos tres, hasta 16 MiB y 16 millones de píxeles.

El análisis automático necesita el [mosaico Sentinel-2 sur de la release de datos](https://github.com/Jall0012/ProyectoSIE/releases/tag/datos).
Configura `PROYECTOSIE_SENTINEL` con la ruta local al TIFF. El servidor lee solo
la ventana del círculo en la cuadrícula original (EPSG:25830, RGB de 8 bits,
10 m por píxel). El TIFF se genera en memoria y pasa por la misma inferencia
que la subida manual.

El modo automático devuelve `422` si el radio está fuera del intervalo
admitido o si el círculo tiene cobertura incompleta. Devuelve `503` si el
mosaico falta, es ilegible o tiene otro formato. Con cualquiera de estos
errores, la subida manual y la evaluación TOPSIS siguen disponibles.
