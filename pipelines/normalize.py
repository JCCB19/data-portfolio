"""Lee los CSV crudos de football-data y devuelve un DataFrame limpio y tipado.

Se hace en Python (y no en SQL) porque los CSV traen fechas en dos formatos
(dd/mm/yyyy y dd/mm/yy) y columnas de sobra. Aquí solo se estandarizan nombres
y tipos; las reglas de negocio (probabilidades, forma, tabla) viven en sql/.
"""
import re
from pathlib import Path

import pandas as pd

COLUMNS = {
    "Div": "division",
    "Date": "date",
    "HomeTeam": "home_team",
    "AwayTeam": "away_team",
    "FTHG": "home_goals",
    "FTAG": "away_goals",
    "FTR": "result",
    "B365H": "odds_home",
    "B365D": "odds_draw",
    "B365A": "odds_away",
}
FILE_RE = re.compile(r"^(\d{4})_([A-Z0-9]+)\.csv$")


def _parse_dates(series: pd.Series) -> pd.Series:
    four = pd.to_datetime(series, format="%d/%m/%Y", errors="coerce")
    two = pd.to_datetime(series, format="%d/%m/%y", errors="coerce")
    return four.fillna(two)


def read_football_csvs(raw_dir: Path) -> pd.DataFrame:
    frames = []
    for path in sorted(Path(raw_dir).glob("*.csv")):
        match = FILE_RE.match(path.name)
        if not match:
            continue
        df = pd.read_csv(path, dtype=str, on_bad_lines="warn")
        for col in COLUMNS:  # columnas que falten en alguna temporada quedan vacías
            if col not in df.columns:
                df[col] = None
        df = df[list(COLUMNS)].rename(columns=COLUMNS)
        df.insert(0, "season_code", match.group(1))
        frames.append(df)

    if not frames:
        raise SystemExit(f"No hay CSV en {raw_dir}. Corre primero pipelines.ingest_football.")

    out = pd.concat(frames, ignore_index=True)
    out = out[out["home_team"].notna() & (out["home_team"].str.strip() != "")]
    out["match_date"] = _parse_dates(out.pop("date")).dt.date
    for col in ("home_goals", "away_goals"):
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
    for col in ("odds_home", "odds_draw", "odds_away"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.drop_duplicates(["season_code", "division", "match_date", "home_team", "away_team"])
