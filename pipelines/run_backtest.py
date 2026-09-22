"""Backtest: ¿el modelo hubiera predicho mejor que el mercado la temporada pasada?

Para cada semana de la última temporada completa, entrena con todo lo anterior
(sin ver el futuro) y predice esa semana. Compara Poisson, Elo y el mercado con
Brier score y RPS (más bajo es mejor en ambos).

Uso:
    python -m pipelines.run_backtest
"""
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from predict_football import (  # noqa: E402
    EloRatings,
    brier_score,
    fit_poisson,
    outcome_vector,
    poisson_predict_1x2,
    rps,
)

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "warehouse" / "portafolio.duckdb"
OUT_PATH = ROOT / "data" / "marts" / "mart_backtest_results.csv"
MIN_TRAIN_MATCHES = 100  # semanas con menos historial que esto se saltan (muy poco confiables)


def pick_backtest_season(df: pd.DataFrame) -> str:
    """Elige la temporada completa más reciente (380 partidos: 20 equipos, ida y vuelta)."""
    counts = df.groupby("season_code").size()
    complete = counts[counts >= 370].index  # tolerancia por si falta algún partido suspendido
    if len(complete) == 0:
        raise SystemExit("No hay ninguna temporada completa en los datos todavía.")
    return sorted(complete)[-1]


def backtest_division(df: pd.DataFrame, division: str, target_season: str) -> pd.DataFrame:
    d = df[df["division"] == division].sort_values("match_date").reset_index(drop=True)
    d["match_date"] = pd.to_datetime(d["match_date"])
    d["iso_week"] = d["match_date"].dt.strftime("%G-%V")

    elo = EloRatings()
    rows = []
    for _, m in d.iterrows():
        is_target = m["season_code"] == target_season
        if is_target:
            elo_probs = elo.predict_1x2(m["home_team"], m["away_team"])
        elo.update(m["home_team"], m["away_team"], m["home_goals"], m["away_goals"])
        if is_target:
            rows.append({"match_idx": m.name, "elo_home": elo_probs[0],
                         "elo_draw": elo_probs[1], "elo_away": elo_probs[2]})
    elo_df = pd.DataFrame(rows).set_index("match_idx")

    target = d[d["season_code"] == target_season]
    poisson_rows = []
    for week, week_matches in target.groupby("iso_week"):
        cutoff = week_matches["match_date"].min()
        train = d[d["match_date"] < cutoff]
        if len(train) < MIN_TRAIN_MATCHES:
            continue
        model = fit_poisson(train)
        for idx, m in week_matches.iterrows():
            probs = poisson_predict_1x2(model, m["home_team"], m["away_team"])
            poisson_rows.append({"match_idx": idx, "poisson_home": probs[0],
                                  "poisson_draw": probs[1], "poisson_away": probs[2]})
    poisson_df = pd.DataFrame(poisson_rows).set_index("match_idx")

    return target.join(elo_df, how="inner").join(poisson_df, how="inner")


def add_metrics(out: pd.DataFrame) -> pd.DataFrame:
    outcomes = [outcome_vector(r.home_goals, r.away_goals) for r in out.itertuples()]
    for method, cols in [
        ("poisson", ["poisson_home", "poisson_draw", "poisson_away"]),
        ("elo", ["elo_home", "elo_draw", "elo_away"]),
        ("market", ["market_p_home", "market_p_draw", "market_p_away"]),
    ]:
        probs = out[cols].to_numpy()
        out[f"brier_{method}"] = [brier_score(probs[i], outcomes[i]) for i in range(len(out))]
        out[f"rps_{method}"] = [rps(probs[i], outcomes[i]) for i in range(len(out))]
    return out


def main() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = con.execute("select * from staging.stg_matches").fetchdf()
    con.close()

    target_season = pick_backtest_season(df)
    print(f"Temporada de backtest: {target_season} (última temporada completa)\n")

    results = []
    for division in sorted(df["division"].unique()):
        res = backtest_division(df, division, target_season)
        if res.empty:
            print(f"{division}: sin suficiente historial para evaluar, se omite")
            continue
        results.append(res)

    if not results:
        raise SystemExit("No se pudo evaluar ninguna división (revisa MIN_TRAIN_MATCHES).")

    all_results = add_metrics(pd.concat(results, ignore_index=True))
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    all_results.to_csv(OUT_PATH, index=False)
    print(f"Guardado: {OUT_PATH} ({len(all_results)} partidos evaluados)\n")

    summary = (
        all_results.groupby("division")[
            ["brier_poisson", "brier_elo", "brier_market", "rps_poisson", "rps_elo", "rps_market"]
        ]
        .mean()
        .round(4)
    )
    print("Promedio por división (más bajo = mejor):")
    print(summary.to_string())
    print()
    overall = all_results[
        ["brier_poisson", "brier_elo", "brier_market", "rps_poisson", "rps_elo", "rps_market"]
    ].mean().round(4)
    print("Promedio general:")
    print(overall.to_string())


if __name__ == "__main__":
    main()
