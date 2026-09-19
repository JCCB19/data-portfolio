"""Configuración central del proyecto: rutas, ligas y temporadas."""
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_FOOTBALL = ROOT / "data" / "raw" / "football_data"
MARTS_DIR = ROOT / "data" / "marts"
SQL_DIR = ROOT / "sql"
DB_PATH = ROOT / "warehouse" / "portafolio.duckdb"

# Códigos de división de football-data.co.uk
LEAGUES = {
    "E0": "Premier League",
    "SP1": "La Liga",
}

BASE_URL = "https://www.football-data.co.uk/mmz4281/{season}/{div}.csv"


def current_season_code(today: date | None = None) -> str:
    """Código de temporada de football-data: 2026-27 -> '2627'.

    La temporada arranca en agosto, así que de julio en adelante ya cuenta
    como la nueva.
    """
    today = today or date.today()
    start = today.year if today.month >= 7 else today.year - 1
    return f"{start % 100:02d}{(start + 1) % 100:02d}"
