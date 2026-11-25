# GeoSolar

Evaluación de la aptitud fotovoltaica en Jaén mediante capas geográficas e imágenes Sentinel-2.

## Arranque rápido en Ubuntu

1. Clona el repositorio y entra en la carpeta. Necesitas Python 3.12 con soporte para entornos virtuales.

   ```sh
   git clone --branch master https://github.com/Jall0012/ProyectoSIE.git
   cd ProyectoSIE
   python3.12 -m venv .venv
   .venv/bin/python -m pip install -r backend/requirements-backend.txt
   ```

2. Crea una carpeta `GeoSolar-datos` junto al repositorio y guarda allí `CapasUsadas.gpkg` y `modelo_multitarea_solar.keras`. Para el recorte automático, descarga también el TIFF Sentinel-2 cuyo nombre termina en `_sur_COG.tif` y guárdalo como `sentinel2-sur.tif`. [Release de datos](https://github.com/Jall0012/ProyectoSIE/releases/tag/datos) · [Release del modelo](https://github.com/Jall0012/ProyectoSIE/releases/tag/Modelos)

3. Desde la raíz del repositorio, configura las rutas y arranca el visor y la API en el mismo puerto.

   ```sh
   export PROYECTOSIE_GPKG="$PWD/../GeoSolar-datos/CapasUsadas.gpkg"
   export PROYECTOSIE_MODELO="$PWD/../GeoSolar-datos/modelo_multitarea_solar.keras"
   export PROYECTOSIE_SENTINEL="$PWD/../GeoSolar-datos/sentinel2-sur.tif"

   .venv/bin/python - <<'PY'
   import uvicorn
   from starlette.applications import Starlette
   from starlette.routing import Mount
   from starlette.staticfiles import StaticFiles

   from backend.main import app as api

   def main() -> None:
       app = Starlette(
           lifespan=lambda _: api.router.lifespan_context(api),
           routes=[
               Mount("/api", app=api),
               Mount("/", app=StaticFiles(directory="frontend", html=True)),
           ],
       )
       uvicorn.run(app, host="127.0.0.1", port=3000)

   if __name__ == "__main__":
       main()
   PY
   ```

Abre [GeoSolar](http://127.0.0.1:3000/) y prueba **Sobre GeoSolar → Ver un ejemplo**. Puedes comprobar la [salud de la API](http://127.0.0.1:3000/api/salud) y parar el servidor con **Ctrl+C**.

Más detalles en las [instrucciones del backend](backend/README.md) y la [guía de despliegue con Nginx](frontend/README.md#preparación-para-ubuntu).
