# Portafolio de datos / Data Portfolio

**ES** — Proyectos de analítica sobre futbol (Premier League y La Liga), NFL, cine y moda deportiva, construidos sobre un warehouse en SQL que se actualiza cada semana de forma automática.
**EN** — Analytics projects on football (Premier League and La Liga), the NFL, film and sportswear, built on a SQL warehouse that refreshes automatically every week.

## Estado / Status

| Fase / Phase | Contenido / Scope | Estado / Status |
|---|---|---|
| 0 | Base: warehouse DuckDB, ingesta, actualización semanal, sitio ES/EN | Completa |
| 1 | Futbol: modelo de predicción + tablero Liverpool / Barcelona | Modelo y backtest listos, falta registro semanal de predicciones y el tablero |
| 2 | Fantasy NFL (nflverse + Sleeper) | Pendiente |
| 3 | Moda deportiva y cine | Pendiente |

## Cómo correrlo / How to run

```bash
pip install -r requirements.txt
python scripts/check_sources.py                 # ¿se alcanzan las fuentes de datos?
python -m pipelines.ingest_football --seasons 2425 2526 2627   # descarga (primera vez: historial)
python -m pipelines.build_warehouse             # construye el warehouse y exporta los marts
python -m pipelines.run_backtest                # evalúa el modelo de predicción vs el mercado
```

Todos los pasos tardan segundos. El warehouse (`warehouse/portafolio.duckdb`) se reconstruye completo en cada corrida; los resultados listos para usar quedan en `data/marts/` (Parquet y CSV).

## Estructura / Structure

```
pipelines/   código Python: ingesta (descarga) y construcción del warehouse
sql/         transformaciones en SQL: staging/ (limpieza) y marts/ (tablas finales)
data/raw/    datos crudos tal como se descargan
data/marts/  tablas finales para modelos y tableros
site/        sitio del portafolio (Quarto, español e inglés)
docs/        documentación de arquitectura y decisiones
.github/     actualización semanal automática (GitHub Actions)
```

Más detalle en [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md).

## Transparencia / Transparency

**ES** — Las preguntas, decisiones de diseño y arquitectura son mías. La implementación se desarrolló con ayuda de un asistente de IA (Claude), y cada decisión está documentada en `docs/`.
**EN** — The questions, design decisions and architecture are mine. The implementation was developed with the help of an AI assistant (Claude), and each decision is documented in `docs/`.

## Fuentes de datos / Data sources

- [football-data.co.uk](https://www.football-data.co.uk/) — resultados y cuotas históricas / historical results and odds.
