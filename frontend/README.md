# Frontend de ProyectoSIE

Interfaz estática en español. Sirve esta carpeta como raíz del sitio. El
frontend envía las peticiones a `/api/` en el mismo origen. Sigue las
[instrucciones del backend](../backend/README.md) para arrancar FastAPI en
`127.0.0.1:8000` con el GeoPackage y el modelo Keras.

## Preparación para Ubuntu

Adapta el dominio y la ruta de archivos en el bloque de Nginx. En el servidor,
systemd puede arrancar Uvicorn con el entorno de Python y las variables
`PROYECTOSIE_GPKG` y `PROYECTOSIE_MODELO` apuntando a los datos externos.

```nginx
server {
    listen 80;
    server_name proyectosie.ejemplo.es;
    root /var/www/proyectosie/frontend;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }

    location /api/ {
        client_max_body_size 17m;
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

La barra final de `proxy_pass` elimina el prefijo `/api/`. Los 17 MiB dejan
margen para el cuerpo multipart. FastAPI aplica el límite de 16 MiB al TIFF.
Antes de activar la configuración en Ubuntu, valida el archivo con `nginx -t`
y configura HTTPS para el dominio definitivo.

## Mapa y vista previa

El mapa local abre con una vista provincial. Usa curvas de nivel cada 200 m,
carreteras y suelo urbano simplificados
de `CapasUsadas.gpkg` de la [release de datos](https://github.com/Jall0012/ProyectoSIE/releases/tag/datos).
Las tres capas corresponden a los temas de relieve, usos del suelo y red de
carreteras de [DERA](https://www.juntadeandalucia.es/institutodeestadisticaycartografia/dega/datos-espaciales-de-referencia-de-andalucia-dera/descarga-de-informacion),
publicados por el Instituto de Estadística y Cartografía de Andalucía bajo
[CC BY 4.0](https://www.juntadeandalucia.es/datosabiertos/portal/dataset/datos-espaciales-de-referencia-andalucia-dera).
El IGN es la fuente de origen de las capas de usos del suelo y carretera.
La cartografía local es orientativa. La evaluación usa las capas completas
del backend. El mapa general solicita teselas del
[Mapa Base de España del IGN](https://www.ign.es/web/ide-area-nodo-ide-ign)
sin clave de API y muestra su atribución en el mapa.

Para regenerar la cartografía local, ejecuta desde la raíz del repositorio
con el entorno del backend activo:

```sh
python scripts/generar_mapa_jaen.py /ruta/a/CapasUsadas.gpkg frontend/mapa-jaen.geojson
```

### Límite provincial

El recinto provincial de Jaén se obtiene de la colección de unidades
administrativas de la [API del IGN](https://api-features.ign.es/collections/administrativeunit/items?nationalcode=34012300000).
Se simplifica con una tolerancia de 25 m. Obra derivada de BDLJE CC-BY 4.0 ign.es.

Para regenerar el límite, ejecuta desde la raíz con el entorno del backend
activo y acceso a la API del IGN:

```sh
python -m scripts.generar_limites_jaen frontend/limites-jaen.geojson
```

### Vista previa del recorte

El navegador carga versiones fijas de Leaflet y GeoTIFF.js desde jsDelivr.
La vista previa se calcula en el dispositivo. El TIFF original solo se envía
a FastAPI al pulsar «Analizar imagen».
