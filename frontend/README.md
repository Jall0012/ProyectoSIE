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

El mapa local usa curvas de nivel, carreteras y suelo urbano simplificados
de `CapasUsadas.gpkg` de la [release de datos](https://github.com/Jall0012/ProyectoSIE/releases/tag/datos).
Las tres capas corresponden a los temas de relieve, usos del suelo y red de
carreteras de [DERA](https://www.juntadeandalucia.es/institutodeestadisticaycartografia/dega/datos-espaciales-de-referencia-de-andalucia-dera/descarga-de-informacion),
publicados por el Instituto de Estadística y Cartografía de Andalucía bajo
[CC BY 4.0](https://www.juntadeandalucia.es/datosabiertos/portal/dataset/datos-espaciales-de-referencia-andalucia-dera).
El IGN es la fuente de origen de las capas de usos del suelo y carretera.
La cartografía local es orientativa. La evaluación usa las capas completas
del backend. El mapa general opcional solicita teselas de CARTO y
OpenStreetMap y muestra sus créditos en el mapa.

El navegador carga versiones fijas de Leaflet y GeoTIFF.js desde jsDelivr.
La vista previa se calcula en el dispositivo. El TIFF original solo se envía
a FastAPI al pulsar «Analizar imagen».
