# ProyectoSIE

Proyecto académico para evaluar si una zona es adecuada para instalar placas fotovoltaicas. El análisis empieza en Jaén y tiene dos modos.

1. **Evaluación con capas geográficas.** El usuario introduce la latitud y la longitud del centro en WGS84 y un radio en metros. El sistema proyecta el centro a `EPSG:25830` y construye una zona circular. El sistema consulta las capas que ya tiene para esa zona y calcula su idoneidad con TOPSIS. Si faltan datos para evaluarla, informa de la falta de cobertura.
2. **Estimación con una imagen satelital.** Si el usuario solo dispone de una imagen del terreno y el sistema carece de capas para esa zona, puede subir el recorte. Una red neuronal convolucional (CNN) usa la imagen para estimar la idoneidad fotovoltaica.

**Cómo se entrena la CNN.** Se ejecuta el primer modo en un bucle que recorre todas las zonas disponibles. Para cada zona con evaluación e imagen satelital, se empareja el recorte de la misma zona circular con el resultado de TOPSIS. Esos pares de imagen y etiqueta forman el conjunto de entrenamiento del segundo modo.

## Karpathy · Cómo programar

1. **Piensa antes de editar.** Revisa la rama, el estado de Git y el código afectado. Expón los supuestos que cambien el resultado. Si hay varias interpretaciones relevantes, explica la diferencia y pregunta cuando impida avanzar.
2. **Elige la solución más simple.** Reutiliza lo que existe. Añade una función, clase o dependencia solo si resuelve una necesidad actual. Prefiere código breve que se pueda leer y comprobar.
3. **Cambia lo justo.** Limita el diff a la tarea y conserva el trabajo de los demás. Limpia los imports y el código que tu propio cambio deje sin usar.
4. **Define cómo sabrás que funciona.** Convierte la petición en comprobaciones concretas. Si corriges un error, reprodúcelo primero cuando sea posible. Ejecuta las comprobaciones y comunica su resultado real.

## Caveman · Cómo comunicar

- Responde en español, con el resultado primero. Usa frases cortas, términos técnicos precisos y listas solo si ayudan.
- Para tareas planificadas, usa una tarjeta breve con ID, objetivo, rama, entrada, salida y criterios de aceptación.
- Al cerrar, di qué cambió, qué comprobaste y qué queda pendiente. Amplía si una decisión o un resultado necesita contexto.

## Reglas del proyecto

- Python al estilo de las prácticas de SIE. Usa nombres descriptivos en español, pasos claros y comentarios breves donde aporten contexto. Anota el tipo de cada parámetro y retorno. En scripts ejecutables, usa `main() -> None` y `if __name__ == "__main__":`.
- Mantén separados el análisis geográfico, el entrenamiento y la interfaz. En `master`, empieza por `clasificador.py` para la evaluación territorial o `EntrenamientoIA.py` para la CNN. En `develop`, la consulta puntual está en `backend/main.py`.
- Usa WGS84 (`EPSG:4326`) para la entrada GPS y `EPSG:25830` para las medidas en Jaén. Valida capas, campos y unidades. Consulta la malla de irradiación con el índice espacial. Abre los datos de origen en solo lectura y recibe sus rutas por configuración. Los archivos grandes se distribuyen por Releases (`datos` y `Modelos`).
- Distingue la falta de cobertura de un valor cero. Compara puntuaciones TOPSIS con una referencia común. Separa entrenamiento y evaluación de la CNN por bloques geográficos. Distingue la estimación visual de la evaluación territorial.
- Para cambios espaciales, contrasta casos con QGIS u `ogrinfo`. Incluye un punto interior, uno sin cobertura y un borde si cambia la intersección. En Codex Cloud, usa `/usr/bin/python3` si necesitas los módulos de GDAL del sistema.
- Si el usuario pide subagentes, separa implementación y verificación. Haz commits, push y despliegues cuando el usuario los pida. Atribuye cada commit de agente a quien hizo el cambio.
