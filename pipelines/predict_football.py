"""Modelo de predicción de partidos: Poisson (Dixon-Coles simplificado) + Elo como línea base.

Ambos modelos aprenden solo de partidos ya jugados (sin ver el futuro) y se comparan
contra las probabilidades implícitas del mercado (columnas market_p_* de staging.stg_matches).

Elo: línea base minimalista, solo usa resultados (gana/empata/pierde), sin goles.
Poisson: usa los goles y produce, además de 1X2, la matriz completa de marcadores.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

MAX_GOALS = 8  # cubre >99.8% de la masa de probabilidad en futbol de clubes


# ---------------------------------------------------------------------------
# Elo (línea base)
# ---------------------------------------------------------------------------
class EloRatings:
    """Elo con ventaja de local. Se actualiza partido a partido, en orden cronológico."""

    def __init__(self, k: float = 20.0, home_adv: float = 60.0, base: float = 1500.0):
        self.k = k
        self.home_adv = home_adv
        self.base = base
        self.ratings: dict[str, float] = {}

    def get(self, team: str) -> float:
        return self.ratings.get(team, self.base)

    def predict_1x2(self, home: str, away: str) -> np.ndarray:
        """Probabilidad de local/empate/visita a partir de la diferencia de rating.

        La probabilidad de empate se modela con un margen fijo alrededor del punto
        de indiferencia (una aproximación simple y estándar en implementaciones de Elo
        para deportes con empate, no una derivación teórica exacta).
        """
        diff = (self.get(home) + self.home_adv) - self.get(away)
        p_home_no_draw = 1.0 / (1.0 + 10 ** (-diff / 400))
        draw_margin = 0.18
        p_draw = draw_margin * (1 - abs(2 * p_home_no_draw - 1))
        p_home = p_home_no_draw * (1 - p_draw)
        p_away = (1 - p_home_no_draw) * (1 - p_draw)
        return np.array([p_home, p_draw, p_away])

    def update(self, home: str, away: str, home_goals: int, away_goals: int) -> None:
        probs = self.predict_1x2(home, away)  # ya incluye la ventaja de local
        p_home_win = probs[0] + probs[1] / 2  # score esperado tipo "torneo" (gana=1, empata=0.5)
        if home_goals > away_goals:
            score = 1.0
        elif home_goals == away_goals:
            score = 0.5
        else:
            score = 0.0
        delta = self.k * (score - p_home_win)
        self.ratings[home] = self.get(home) + delta
        self.ratings[away] = self.get(away) - delta


# ---------------------------------------------------------------------------
# Poisson (Dixon-Coles simplificado: ataque, defensa y ventaja de local; sin el
# ajuste de correlación rho para resultados bajos, que se puede añadir después)
# ---------------------------------------------------------------------------
def fit_poisson(train_df: pd.DataFrame, ridge: float = 0.03) -> dict:
    """Ajusta fuerza de ataque/defensa por equipo mediante máxima verosimilitud.

    log(goles_esperados_local)  = mu + home_adv + ataque[local]  - defensa[visita]
    log(goles_esperados_visita) = mu + ataque[visita] - defensa[local]

    Un término ridge evita que el ajuste diverja con equipos de pocos partidos
    (por ejemplo, recién ascendidos) y hace innecesaria una restricción de
    identificabilidad explícita. Caso real que motivó subir este valor: un equipo
    recién ascendido sin goles en sus primeros 4 partidos de la temporada hacía que
    el ajuste sin regularizar le diera una fuerza de ataque casi cero (goles
    esperados ~0.02), un valor técnicamente coherente con esos datos pero poco
    prudente para predecir con tan poca muestra.
    """
    teams = sorted(set(train_df["home_team"]) | set(train_df["away_team"]))
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    home_i = train_df["home_team"].map(idx).to_numpy()
    away_i = train_df["away_team"].map(idx).to_numpy()
    hg = train_df["home_goals"].to_numpy(dtype=float)
    ag = train_df["away_goals"].to_numpy(dtype=float)

    def unpack(x):
        mu, home_adv = x[0], x[1]
        attack = x[2 : 2 + n]
        defense = x[2 + n : 2 + 2 * n]
        return mu, home_adv, attack, defense

    def neg_log_lik(x):
        mu, home_adv, attack, defense = unpack(x)
        log_lh = mu + home_adv + attack[home_i] - defense[away_i]
        log_la = mu + attack[away_i] - defense[home_i]
        lh, la = np.exp(log_lh), np.exp(log_la)
        # Verosimilitud de Poisson sin el término log(y!) (constante, no afecta la optimización)
        ll = np.sum(hg * log_lh - lh) + np.sum(ag * log_la - la)
        penalty = ridge * (np.sum(attack**2) + np.sum(defense**2))
        return -ll + penalty

    x0 = np.zeros(2 + 2 * n)
    x0[0] = np.log(hg.mean())  # punto de partida razonable para mu
    result = minimize(neg_log_lik, x0, method="L-BFGS-B")
    mu, home_adv, attack, defense = unpack(result.x)
    return {
        "mu": mu,
        "home_adv": home_adv,
        "attack": dict(zip(teams, attack)),
        "defense": dict(zip(teams, defense)),
        "converged": result.success,
    }


def expected_goals(model: dict, home: str, away: str) -> tuple[float, float]:
    a_h = model["attack"].get(home, 0.0)
    d_h = model["defense"].get(home, 0.0)
    a_a = model["attack"].get(away, 0.0)
    d_a = model["defense"].get(away, 0.0)
    lh = np.exp(model["mu"] + model["home_adv"] + a_h - d_a)
    la = np.exp(model["mu"] + a_a - d_h)
    return float(lh), float(la)


def scoreline_matrix(lh: float, la: float, max_goals: int = MAX_GOALS) -> np.ndarray:
    """Matriz [goles_local, goles_visita] -> probabilidad, asumiendo independencia Poisson."""
    from scipy.stats import poisson

    ph = poisson.pmf(np.arange(max_goals + 1), lh)
    pa = poisson.pmf(np.arange(max_goals + 1), la)
    matrix = np.outer(ph, pa)
    return matrix / matrix.sum()  # renormaliza por la masa truncada en max_goals


def matrix_to_1x2(matrix: np.ndarray) -> np.ndarray:
    p_home = np.tril(matrix, -1).sum()
    p_draw = np.trace(matrix)
    p_away = np.triu(matrix, 1).sum()
    return np.array([p_home, p_draw, p_away])


def poisson_predict_1x2(model: dict, home: str, away: str) -> np.ndarray:
    lh, la = expected_goals(model, home, away)
    return matrix_to_1x2(scoreline_matrix(lh, la))


# ---------------------------------------------------------------------------
# Métricas de evaluación (partido a partido; ambas se promedian al final)
# ---------------------------------------------------------------------------
def outcome_vector(home_goals: int, away_goals: int) -> np.ndarray:
    """[1,0,0] si gana el local, [0,1,0] empate, [0,0,1] gana la visita."""
    if home_goals > away_goals:
        return np.array([1.0, 0.0, 0.0])
    if home_goals == away_goals:
        return np.array([0.0, 1.0, 0.0])
    return np.array([0.0, 0.0, 1.0])


def brier_score(probs: np.ndarray, outcome: np.ndarray) -> float:
    return float(np.sum((probs - outcome) ** 2))


def rps(probs: np.ndarray, outcome: np.ndarray) -> float:
    """Ranked Probability Score para 3 resultados ordenados [local, empate, visita].

    Penaliza menos un error "cercano" (predecir empate cuando ganó el local) que uno
    "lejano" (predecir visita cuando ganó el local), a diferencia del Brier score.
    """
    cum_p = np.cumsum(probs)
    cum_o = np.cumsum(outcome)
    return float(np.sum((cum_p - cum_o) ** 2) / (len(probs) - 1))
