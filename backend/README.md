# Backend de ProyectoSIE

Desde la raíz del repositorio, con Python 3.12 y los archivos de las releases
guardados fuera del repositorio:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-backend.txt
export PROYECTOSIE_GPKG=/workspace/ProyectoSIE-datos/CapasUsadas.gpkg
export PROYECTOSIE_MODELO=/workspace/ProyectoSIE-datos/modelo_multitarea_solar.keras
.venv/bin/python -m uvicorn backend.main:app
```

La documentación interactiva está en `http://127.0.0.1:8000/docs`.

| Método y ruta | Entrada | Resultado |
| --- | --- | --- |
| `GET /salud` | | Estado del servicio |
| `POST /evaluar-zona` | JSON con `latitud`, `longitud` y `radio_m` | Categoría y puntuación TOPSIS entre 0 y 1, o «Sin datos» con puntuación nula |
| `POST /analizar-imagen` | Campo multipart `archivo` con un TIFF | Categoría más probable, probabilidades de aptitud y probabilidad de veto |

El centro se indica en WGS84 y el radio en metros. El TIFF admite una banda o
al menos tres, hasta 16 MiB y 16 millones de píxeles.
