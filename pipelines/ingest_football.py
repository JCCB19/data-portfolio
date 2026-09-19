"""Paso 1 (ingesta): descarga resultados y cuotas de football-data.co.uk.

Guarda cada CSV tal cual (convertido a UTF-8) en data/raw/football_data/.
No transforma nada: la limpieza vive en normalize.py y en los archivos SQL.

Uso:
    python -m pipelines.ingest_football                       # temporada actual
    python -m pipelines.ingest_football --seasons 2324 2425 2526 2627
"""
import argparse
import sys
import urllib.error
import urllib.request

from pipelines.config import BASE_URL, LEAGUES, RAW_FOOTBALL, current_season_code


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "portafolio-datos/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def to_utf8(raw: bytes) -> str:
    """Los CSV de esta fuente a veces vienen en latin-1; se normalizan a UTF-8."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", nargs="+", default=[current_season_code()])
    args = parser.parse_args()

    RAW_FOOTBALL.mkdir(parents=True, exist_ok=True)
    ok, failed = 0, []
    for season in args.seasons:
        for div, name in LEAGUES.items():
            url = BASE_URL.format(season=season, div=div)
            try:
                text = to_utf8(fetch(url))
            except (urllib.error.URLError, TimeoutError) as exc:
                failed.append(f"{season}/{div}: {exc}")
                continue
            (RAW_FOOTBALL / f"{season}_{div}.csv").write_text(text, encoding="utf-8")
            print(f"OK   {name} {season}: {len(text.splitlines()) - 1} filas")
            ok += 1

    for msg in failed:
        print(f"FALLÓ {msg}", file=sys.stderr)
    # Falla solo si no se pudo descargar nada; una temporada nueva puede no existir aún.
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
