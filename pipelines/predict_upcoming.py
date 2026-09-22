"""Predicciones para los próximos partidos: 1X2, marcador más probable y goles esperados.

A diferencia de run_backtest.py, aquí no se evalúa nada: se entrena el modelo Poisson con
TODO el historial disponible, porque el objetivo es la mejor predicción posible para partidos
reales que todavía no se jugaron.

Uso:
    python -m pipelines.ingest_fixtures      # primero, para tener data/raw/fixtures_next.json
    python -m pipelines.predict_upcoming
"""
import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from predict_football import expected_goals, fit_poisson, matrix_to_1x2, scoreline_matrix  # noqa: E402
from team_name_map import build_team_name_map  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "warehouse" / "portafolio.duckdb"
FIXTURES_PATH = ROOT / "data" / "raw" / "fixtures_next.json"
OUT_PATH = ROOT / "data" / "marts" / "mart_predictions_next.csv"


def main() -> None:
    if not FIXTURES_PATH.exists():
        raise SystemExit("No hay fixtures descargados. Corre primero: python -m pipelines.ingest_fixtures")
    fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    if not fixtures:
        print("No hay partidos próximos en la ventana descargada. Nada que predecir.")
        return

    con = duckdb.connect(str(DB_PATH), read_only=True)
    matches = con.execute("select * from staging.stg_matches").fetchdf()
    con.close()

    rows = []
    for division, div_matches in matches.groupby("division"):
        div_fixtures = [f for f in fixtures if f["division"] == division]
        if not div_fixtures:
            continue
        # Solo los nombres de ESTA liga: si se revisan los de las dos ligas juntas, los de
        # una aparecen como "sin equivalencia" contra el historial de la otra por pura mezcla.
        fixture_names = sorted({f["home_team_fixture"] for f in div_fixtures}
                                | {f["away_team_fixture"] for f in div_fixtures})

        model = fit_poisson(div_matches)
        historical_names = list(model["attack"].keys())
        name_map, uncertain = build_team_name_map(fixture_names, historical_names)
        if uncertain:
            print(f"AVISO ({division}): sin equivalencia clara para {uncertain}. "
                  "Agrégalos a KNOWN_OVERRIDES en pipelines/team_name_map.py y vuelve a correr; "
                  "esos partidos se omiten mientras tanto.")

        for f in div_fixtures:
            home = name_map.get(f["home_team_fixture"])
            away = name_map.get(f["away_team_fixture"])
            if home is None or away is None:
                continue  # ya se avisó arriba
            lh, la = expected_goals(model, home, away)
            matrix = scoreline_matrix(lh, la)
            p_home, p_draw, p_away = matrix_to_1x2(matrix)
            top_idx = np.unravel_index(np.argmax(matrix), matrix.shape)
            rows.append({
                "division": division,
                "utc_date": f["utc_date"],
                "matchday": f["matchday"],
                "home_team_fixture": f["home_team_fixture"],
                "away_team_fixture": f["away_team_fixture"],
                "home_team": home,
                "away_team": away,
                "goles_esperados_local": round(lh, 2),
                "goles_esperados_visita": round(la, 2),
                "p_gana_local": round(float(p_home), 3),
                "p_empate": round(float(p_draw), 3),
                "p_gana_visita": round(float(p_away), 3),
                "marcador_mas_probable": f"{top_idx[0]}-{top_idx[1]}",
                "prob_marcador_mas_probable": round(float(matrix[top_idx]), 3),
            })

    if not rows:
        print("Ningún partido se pudo predecir (revisa los avisos de nombres sin equivalencia).")
        return

    out = pd.DataFrame(rows).sort_values(["utc_date", "division"])
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_PATH, index=False)
    print(f"\nGuardado: {OUT_PATH} ({len(out)} partidos)\n")
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
