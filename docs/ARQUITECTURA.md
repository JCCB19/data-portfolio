# Arquitectura y decisiones (Fase 0)

Este documento explica cómo funciona el proyecto en lenguaje llano, para poder defenderlo en una entrevista.

## El flujo en una línea

**Fuente pública → descarga (ingesta) → datos crudos → limpieza en SQL → tablas finales (marts) → modelo y tableros.**

## Las piezas

**Ingesta** (`pipelines/ingest_football.py`). Descarga los CSV de football-data.co.uk (resultados y cuotas de Premier League y La Liga) y los guarda sin modificar en `data/raw/`. Separar la descarga de la limpieza permite volver a procesar sin volver a descargar.

**Normalización** (`pipelines/normalize.py`). Estandariza nombres de columnas, tipos y fechas. Se hace en Python porque la fuente mezcla dos formatos de fecha. Es la única lógica que no está en SQL.

**Warehouse en tres capas** (DuckDB, `sql/`). Es una convención muy usada en la industria:

- `raw`: datos tal como llegan, ya con tipos correctos.
- `staging`: partidos jugados y probabilidades implícitas del mercado (las cuotas convertidas en probabilidades que suman 100 %).
- `marts`: tablas listas para consumir. `mart_team_form` tiene una fila por equipo y partido, con puntos acumulados y forma de los últimos 5 partidos. `mart_standings` es la tabla de posiciones.

**Actualización semanal** (`.github/workflows/weekly_update.yml`). GitHub ejecuta los dos pasos cada lunes y guarda los datos nuevos en el repositorio. No es un agente de IA: es una tarea programada.

## Decisiones y por qué

1. **DuckDB en lugar de un servidor de base de datos.** Corre en el mismo proceso, no hay nada que mantener ni pagar, y es muy rápido con este volumen (miles de filas). Es un warehouse analítico a escala pequeña; no se presenta como big data.
2. **Reconstrucción completa en cada corrida.** A este tamaño tarda segundos y elimina errores de estado (nada queda a medias).
3. **SQL con archivos numerados (`01_`, `02_`).** Los archivos se ejecutan en orden alfabético y `mart_standings` depende de `mart_team_form`, así que el número fija el orden. Cuando haya más modelos y dependencias, se migrará a dbt, que resuelve el orden solo.
4. **Datos crudos guardados en el repositorio.** Pesan poco y hacen que el proyecto sea reproducible sin depender de que la fuente siga en línea.
5. **La forma reciente incluye el partido actual.** `points_last5` en una fila describe la forma *después* de ese partido. Para el modelo predictivo habrá que usar la fila anterior, para no filtrar información del futuro. Se aplicará en la Fase 1.

## Limitaciones conocidas

- La fuente (football-data.co.uk) es un sitio de un tercero sin garantías de disponibilidad.
- Las cuotas son de Bet365; no todas las temporadas y ligas las traen completas.
- Understat (estadísticas avanzadas como xG) aún no está integrado. Se decide en la Fase 1 después de verificar el acceso.

## Preguntas probables de entrevista

- *¿Por qué DuckDB y no Postgres o BigQuery?* Volumen pequeño, costo cero, sin servidor; el diseño en capas se traslada tal cual a otro motor si crece.
- *¿Cómo evitas que el pipeline se rompa?* Falla con un mensaje claro si no hay datos, tolera que una temporada nueva aún no exista y no guarda nada si la descarga falla por completo.
- *¿Qué harías distinto con más datos?* Cargas incrementales en lugar de reconstruir todo, dbt con pruebas de calidad y un motor en la nube.
