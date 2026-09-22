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

## Preguntas probables de entrevista (Fase 0)

- *¿Por qué DuckDB y no Postgres o BigQuery?* Volumen pequeño, costo cero, sin servidor; el diseño en capas se traslada tal cual a otro motor si crece.
- *¿Cómo evitas que el pipeline se rompa?* Falla con un mensaje claro si no hay datos, tolera que una temporada nueva aún no exista y no guarda nada si la descarga falla por completo.
- *¿Qué harías distinto con más datos?* Cargas incrementales en lugar de reconstruir todo, dbt con pruebas de calidad y un motor en la nube.

---

# Fase 1: modelo de predicción de partidos

## El flujo en una línea

**Historial de partidos → dos modelos que solo ven el pasado → probabilidades de 1X2 y matriz de marcadores → comparación contra el mercado, semana a semana.**

## Los dos modelos

**Elo** (`pipelines/predict_football.py`, clase `EloRatings`). Es la línea base. Cada equipo tiene un puntaje que sube si gana y baja si pierde, más de lo esperado cuanto más grande sea la sorpresa. Solo usa el resultado (gana, empata, pierde), no los goles. Sirve para comprobar que el modelo principal realmente aporta algo sobre algo muy simple.

**Poisson** (misma función, `fit_poisson`). Es el modelo principal. La idea: los goles de un equipo siguen una distribución de Poisson cuya media depende de la fuerza de ataque del equipo, la fuerza de defensa del rival, y si juega en casa. Se ajustan por máxima verosimilitud una fuerza de ataque y una de defensa por equipo. Con esas dos fuerzas se calculan los goles esperados de cada equipo en un partido, y con dos Poisson independientes se arma la matriz completa de marcadores (por ejemplo, la probabilidad de que el partido termine 2-1). Sumando esa matriz por triángulos se obtienen las probabilidades de que gane el local, empate o gane la visita.

Es una versión simplificada del modelo de Dixon y Coles (1997), uno de los más citados en predicción de futbol. Se dejó fuera, a propósito, el ajuste que ese paper añade para corregir resultados bajos (0-0, 1-0, 0-1, 1-1): es una mejora medible pero secundaria, y agregarla ahora habría complicado el código sin cambiar la historia que cuenta el proyecto. Queda anotada como mejora futura.

## Cómo se evalúa (backtest)

`pipelines/run_backtest.py` hace lo siguiente para la última temporada completa:

1. Toma cada semana de esa temporada, en orden.
2. Para predecirla, entrena el modelo Poisson solo con los partidos anteriores a esa semana (de cualquier temporada disponible). Nunca ve resultados futuros.
3. El Elo se actualiza partido a partido en todo el historial; la predicción de cada partido se guarda antes de actualizar con su resultado.
4. Compara las probabilidades de Poisson, Elo y el mercado (las cuotas, ya convertidas a probabilidad en `staging.stg_matches`) contra lo que pasó, con dos métricas: **Brier score** y **RPS** (Ranked Probability Score). Más bajo es mejor en ambas. El RPS es el estándar en la literatura de predicción de futbol porque, a diferencia del Brier, penaliza menos un error "cercano" (predecir empate cuando ganó el local) que uno "lejano" (predecir visita cuando ganó el local).

El resultado se guarda en `data/marts/mart_backtest_results.csv`, con una fila por partido y las probabilidades y métricas de los tres métodos, para poder graficar la evolución semana a semana en el tablero.

## Decisiones y por qué

1. **No se intenta ganarle al mercado.** Las casas de apuestas tienen más información y la ganan profesionalmente; el objetivo es que las probabilidades del modelo estén bien calibradas y se acerquen al mercado, no superarlo. Si el backtest muestra que Poisson se acerca al mercado y le gana claramente a Elo, el modelo está haciendo su trabajo.
2. **Reentrenar cada semana en lugar de una vez por temporada.** El ajuste tarda una fracción de segundo incluso con miles de partidos, así que no hay razón para no hacerlo. Además refleja mejor lo que se sabía en el momento de cada predicción.
3. **Ridge (regularización) en vez de una restricción de identificabilidad.** El modelo Poisson, sin ninguna restricción, tiene un problema técnico: se puede subir el ataque de todos los equipos y bajar la defensa de todos por igual sin que cambien las predicciones. La forma clásica de resolverlo es fijar un equipo de referencia en cero. Aquí se usa, en cambio, una penalización pequeña que empuja todos los parámetros hacia cero; el resultado es equivalente, pero el código es más simple y además ayuda con equipos recién ascendidos, que tienen pocos partidos.
4. **Elo con margen de empate aproximado.** La fórmula clásica de Elo no incluye empates (viene del ajedrez). Se usa una aproximación común en Elo para deportes con empate, en vez de un modelo de empates derivado matemáticamente. Es una limitación conocida y aceptable para una línea base.

## Limitaciones conocidas

- Sin datos de xG (goles esperados) todavía; Understat queda pendiente de integrar (ver Fase 0). El modelo actual usa solo goles reales.
- No hay ajuste por lesiones, suspensiones ni calendario de competiciones (Champions League entre semana, por ejemplo).
- El backtest usa la última temporada *completa*; la temporada en curso aún no tiene suficiente historial dentro de sí misma para evaluarse igual de bien, aunque sí se beneficia del historial de temporadas anteriores para las predicciones en vivo.
- Falta la fuente de próximos partidos (fixtures). Los CSV de football-data.co.uk solo traen partidos ya jugados; para publicar predicciones antes de cada jornada hace falta otra fuente, que se define en la Fase 1b.

## Preguntas probables de entrevista (Fase 1)

- *¿Por qué Poisson y no un modelo de machine learning más "moderno" (XGBoost, red neuronal)?* Con la cantidad de partidos disponibles por temporada, un modelo más complejo tiende a sobreajustar sin mejorar la calibración. Poisson es interpretable (se puede explicar por qué el modelo cree que un equipo es favorito) y es el punto de partida estándar en la literatura antes de complicar el modelo.
- *¿Cómo sabes que el modelo no hace trampa viendo el futuro?* El backtest solo entrena con partidos estrictamente anteriores a la fecha de la semana que predice; se verificó explícitamente con datos sintéticos antes de usarlo con datos reales.
- *¿Qué mejorarías primero?* El ajuste de Dixon-Coles para marcadores bajos, incorporar xG de Understat como variable adicional, y ponderar los partidos más recientes con más peso (decaimiento temporal) en vez de tratar toda la historia por igual.
