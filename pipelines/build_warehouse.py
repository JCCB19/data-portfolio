"""Paso 2: construye el warehouse en DuckDB (raw -> staging -> marts) y exporta los marts.

Se reconstruye completo en cada corrida (son unos miles de filas, tarda segundos),
así que no hay estado que se pueda corromper.

Uso:
    python -m pipelines.build_warehouse
"""
import time

import duckdb

from pipelines.config import DB_PATH, MARTS_DIR, RAW_FOOTBALL, SQL_DIR
from pipelines.normalize import read_football_csvs


def run_sql_dir(con, folder) -> None:
    """Ejecuta los .sql de una carpeta en orden alfabético (una sentencia por ';')."""
    for path in sorted(folder.glob("*.sql")):
        # Se quitan los comentarios "--" antes de separar por ';' para que un ';' dentro de un comentario no rompa nada.
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.strip().startswith("--")]
        for stmt in "\n".join(lines).split(";"):
            if stmt.strip():
                con.execute(stmt)
        print(f"  ejecutado {path.relative_to(SQL_DIR.parent)}")


def main() -> None:
    t0 = time.time()
    matches = read_football_csvs(RAW_FOOTBALL)
    print(f"Leídos {len(matches)} partidos de {matches['season_code'].nunique()} temporada(s)")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    MARTS_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    for schema in ("raw", "staging", "marts"):
        con.execute(f"create schema if not exists {schema}")

    con.register("matches_df", matches)
    con.execute("create or replace table raw.football_matches as select * from matches_df")

    run_sql_dir(con, SQL_DIR / "staging")
    run_sql_dir(con, SQL_DIR / "marts")

    tables = [r[0] for r in con.execute(
        "select table_name from information_schema.tables where table_schema = 'marts'"
    ).fetchall()]
    for name in tables:
        con.execute(f"copy (select * from marts.{name}) to '{MARTS_DIR / name}.parquet' (format parquet)")
        con.execute(f"copy (select * from marts.{name}) to '{MARTS_DIR / name}.csv' (header, delimiter ',')")
        rows = con.execute(f"select count(*) from marts.{name}").fetchone()[0]
        print(f"  exportado marts.{name}: {rows} filas (parquet + csv)")
    con.close()
    print(f"Listo en {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
