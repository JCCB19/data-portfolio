"""Descarga la próxima jornada sin jugar de Premier League y La Liga desde football-data.org.

Requiere una API key gratuita (10 peticiones/minuto, incluye fixtures). Para conseguirla:
https://www.football-data.org/client/register

Pon la key en la variable de entorno FOOTBALL_DATA_API_KEY, o en un archivo .env en la raíz
del proyecto con la línea:  FOOTBALL_DATA_API_KEY=tu_key
(el .env ya está en .gitignore: nunca se sube al repositorio).

Uso:
    python -m pipelines.ingest_fixtures

Nota de diseño: se pidió primero filtrar por rango de fechas (los próximos N días), pero eso
falla en cualquier semana con pausa de selecciones nacionales (no hay partidos de clubes, la
ventana cae en un hueco vacío y el script no encuentra nada). Por eso se trae la temporada
completa —son pocos partidos, no pesa nada— y se toma la jornada más próxima que aún no se
jugó, sin importar cuántos días falten para que empiece.
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "raw" / "fixtures_next.json"
COMPETITIONS = {"PL": "Premier League", "PD": "La Liga"}
DIVISION_CODE = {"PL": "E0", "PD": "SP1"}  # para que combine con division en staging.stg_matches
API_BASE = "https://api.football-data.org/v4"
PENDING_STATUS = {"SCHEDULED", "TIMED"}  # partidos que aún no se juegan


def load_api_key() -> str:
    key = os.environ.get("FOOTBALL_DATA_API_KEY")
    if key:
        return key
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("FOOTBALL_DATA_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise SystemExit(
        "Falta la API key. Regístrate gratis en https://www.football-data.org/client/register "
        "y ponla en la variable de entorno FOOTBALL_DATA_API_KEY o en un archivo .env "
        "en la raíz del proyecto (FOOTBALL_DATA_API_KEY=tu_key)."
    )


def fetch_season_matches(code: str, api_key: str) -> list[dict]:
    url = f"{API_BASE}/competitions/{code}/matches"
    req = urllib.request.Request(url, headers={"X-Auth-Token": api_key})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp)["matches"]
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise SystemExit(f"football-data.org devolvió {exc.code} para {code}: {detail}") from exc


def next_matchday_fixtures(matches: list[dict]) -> list[dict]:
    """De los partidos que aún no se juegan, se queda con la jornada más próxima."""
    pending = [m for m in matches if m["status"] in PENDING_STATUS]
    if not pending:
        return []
    next_md = min(m["matchday"] for m in pending)
    return [m for m in pending if m["matchday"] == next_md]


def main() -> None:
    api_key = load_api_key()

    all_matches = []
    for code, name in COMPETITIONS.items():
        season_matches = fetch_season_matches(code, api_key)
        fixtures = next_matchday_fixtures(season_matches)
        if fixtures:
            md = fixtures[0]["matchday"]
            fecha = min(f["utcDate"] for f in fixtures)[:10]
            print(f"OK   {name}: jornada {md}, {len(fixtures)} partidos, primero el {fecha}")
        else:
            print(f"OK   {name}: no quedan partidos sin jugar en la temporada (o terminó).")
        for m in fixtures:
            all_matches.append({
                "division": DIVISION_CODE[code],
                "utc_date": m["utcDate"],
                "matchday": m.get("matchday"),
                "home_team_fixture": m["homeTeam"]["name"],
                "away_team_fixture": m["awayTeam"]["name"],
            })

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(all_matches, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Guardado: {OUT_PATH}")


if __name__ == "__main__":
    main()
