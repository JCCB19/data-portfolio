"""Genera una imagen (heatmap tipo "tarjeta") con la matriz de marcadores de cada
partido de data/marts/mart_predictions_next.csv.

No hace ningún cálculo estadístico nuevo: reutiliza el mismo modelo Poisson que
pipelines/predict_upcoming.py (mismos datos, mismo ajuste) para poder dibujar la
matriz completa de marcadores, que el CSV no guarda por sí sola (solo guarda el
resumen: 1X2, goles esperados, marcador más probable).

Uso (después de correr predict_upcoming, aunque sea de una corrida anterior):
    python -m pipelines.plot_predictions

Las imágenes se guardan en data/marts/plots/, una por partido. En VS Code se ven
haciendo clic sobre el archivo (o desde el explorador de archivos, sin abrir nada más).
"""
import re
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # no abre ventana: solo guarda el archivo, no bloquea la terminal
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

sys.path.insert(0, str(Path(__file__).resolve().parent))
from predict_football import expected_goals, fit_poisson, scoreline_matrix  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "warehouse" / "portafolio.duckdb"
PREDICTIONS_PATH = ROOT / "data" / "marts" / "mart_predictions_next.csv"
PLOTS_DIR = ROOT / "data" / "marts" / "plots"
DISPLAY_MAX_GOALS = 5  # se muestra 0-5; la probabilidad más allá es prácticamente cero

# Paleta (verde, sin barra de escala: los valores ya están anotados en cada celda)
GREEN_DARK = "#1b4332"
GREEN_TEXT = "#2d6a4f"
GRAY_TEXT = "#6b7280"
INK = "#111827"
PILL_BG = "#eef7f1"
PILL_BORDER = "#cfe8d8"
CMAP = "Greens"


def slugify(text: str) -> str:
    text = text.lower().replace(" ", "_")
    return re.sub(r"[^a-z0-9_]", "", text)


def plot_match(home: str, away: str, lh: float, la: float, out_path: Path,
               figsize: tuple[float, float] = (6.2, 6.9)) -> None:
    full_matrix = scoreline_matrix(lh, la)  # matriz completa (fiel al modelo)
    matrix = full_matrix[: DISPLAY_MAX_GOALS + 1, : DISPLAY_MAX_GOALS + 1]  # recorte solo para mostrar

    p_home = float(np.tril(full_matrix, -1).sum())
    p_draw = float(np.trace(full_matrix))
    p_away = float(np.triu(full_matrix, 1).sum())
    max_goals = full_matrix.shape[0] - 1
    total_goals = np.add.outer(np.arange(max_goals + 1), np.arange(max_goals + 1))
    p_over25 = float(full_matrix[total_goals >= 3].sum())

    flat_idx = np.dstack(np.unravel_index(np.argsort(-matrix, axis=None), matrix.shape))[0]
    top3 = [(int(i), int(j), float(matrix[i, j])) for i, j in flat_idx[:3]]

    fig = plt.figure(figsize=figsize, dpi=200)
    fig.patch.set_facecolor("white")
    fig.canvas.draw()  # habilita medir texto con el renderer desde ya
    renderer = fig.canvas.get_renderer()
    fig_w_px = figsize[0] * fig.dpi

    def text_width_frac(s: str, **kw) -> float:
        t = fig.text(-1, -1, s, **kw)
        w = t.get_window_extent(renderer).width / fig_w_px
        t.remove()
        return w

    def centered_multistyle(y: float, parts: list[tuple[str, dict]]) -> None:
        """parts: lista de (texto, kwargs). Centra el conjunto como una sola línea."""
        widths = [text_width_frac(s, **kw) for s, kw in parts]
        x = 0.5 - sum(widths) / 2
        for (s, kw), w in zip(parts, widths):
            fig.text(x, y, s, va="center", ha="left", **kw)
            x += w

    # tarjeta (borde redondeado alrededor de toda la figura)
    fig.add_artist(FancyBboxPatch(
        (0.02, 0.02), 0.96, 0.96,
        transform=fig.transFigure, boxstyle="round,pad=0,rounding_size=0.03",
        linewidth=1.2, edgecolor="#e5e7eb", facecolor="white", zorder=0,
    ))

    # título (equipos en negrita, "vs" más chico y gris) y subtítulo
    centered_multistyle(0.955, [
        (home, dict(fontsize=17, fontweight="bold", color=INK)),
        (" vs ", dict(fontsize=12.5, color=GRAY_TEXT)),
        (away, dict(fontsize=17, fontweight="bold", color=INK)),
    ])
    fig.text(0.5, 0.905, f"Goles esperados: {lh:.2f} – {la:.2f}", ha="center", va="center",
              fontsize=10.5, color=GRAY_TEXT)

    # barra de resultados (marcadores más probables), arriba de la matriz
    top3_txt = "   ·   ".join(f"{i}-{j} {p:.1%}" for i, j, p in top3)
    fig.add_artist(FancyBboxPatch(
        (0.5 - 0.46, 0.825), 0.92, 0.05,
        transform=fig.transFigure, boxstyle="round,pad=0,rounding_size=0.025",
        linewidth=1, edgecolor=PILL_BORDER, facecolor=PILL_BG, zorder=1,
    ))
    fig.text(0.5, 0.85, top3_txt, ha="center", va="center", fontsize=9.5, color=INK)

    fig.text(0.5, 0.80, f"←  goles {away}  →", ha="center", va="center",
              fontsize=9.5, color=GRAY_TEXT)

    # matriz de marcadores
    ax = fig.add_axes((0.14, 0.315, 0.72, 0.43))
    ax.imshow(matrix, cmap=CMAP, vmin=0)
    ax.set_xticks(range(DISPLAY_MAX_GOALS + 1))
    ax.set_yticks(range(DISPLAY_MAX_GOALS + 1))
    ax.xaxis.tick_top()
    ax.tick_params(length=0, labelsize=9, colors=GRAY_TEXT)
    for spine in ax.spines.values():
        spine.set_visible(False)

    threshold = matrix.max() * 0.55
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = matrix[i, j]
            color = "white" if value > threshold else "#1a1a1a"
            ax.text(j, i - 0.12, f"{i}-{j}", ha="center", va="center",
                     color=color, fontsize=9.5, fontweight="bold")
            ax.text(j, i + 0.18, f"{value:.1%}", ha="center", va="center",
                     color=color, fontsize=7.8)

    hi, hj, _ = top3[0]
    ax.add_patch(Rectangle((hj - 0.5, hi - 0.5), 1, 1, fill=False,
                            edgecolor=GREEN_DARK, linewidth=2.2))

    fig.text(0.5, 0.265, f"↓  goles {home}", ha="center", va="center",
              fontsize=9.5, color=GRAY_TEXT)

    # cuadritos de 1X2 / O2.5, tamaño de las celdas ajustado al texto de cada uno
    stats = [
        (f"1 {home}", f"{p_home:.0%}"),
        ("X", f"{p_draw:.0%}"),
        (f"2 {away}", f"{p_away:.0%}"),
        ("O2.5", f"{p_over25:.0%}"),
    ]
    label_kw = dict(fontsize=6.8, color=GRAY_TEXT)
    value_kw = dict(fontsize=9.5, fontweight="bold", color=GREEN_TEXT)
    pad = 0.015
    widths = [max(text_width_frac(l, **label_kw), text_width_frac(v, **value_kw)) + pad * 2
              for l, v in stats]
    gap = 0.014
    total_w = sum(widths) + gap * (len(stats) - 1)
    x = 0.5 - total_w / 2
    y_pill, pill_h = 0.165, 0.048
    for (label, value), w in zip(stats, widths):
        fig.add_artist(FancyBboxPatch(
            (x, y_pill), w, pill_h,
            transform=fig.transFigure, boxstyle="round,pad=0,rounding_size=0.014",
            linewidth=1, edgecolor=PILL_BORDER, facecolor=PILL_BG, zorder=1,
        ))
        cx = x + w / 2
        fig.text(cx, y_pill + pill_h * 0.68, label, ha="center", va="center", **label_kw)
        fig.text(cx, y_pill + pill_h * 0.30, value, ha="center", va="center", **value_kw)
        x += w + gap

    fig.text(0.5, 0.07, "Modelo Poisson (ataque/defensa por equipo, ajuste por máxima verosimilitud, "
                          "regularización ridge) · Datos: football-data.co.uk",
              ha="center", va="center", fontsize=6.6, color="#9ca3af")

    fig.savefig(out_path, facecolor="white")
    plt.close(fig)


def main() -> None:
    if not PREDICTIONS_PATH.exists():
        raise SystemExit(
            "Falta data/marts/mart_predictions_next.csv. Corre primero: "
            "python -m pipelines.ingest_fixtures  y  python -m pipelines.predict_upcoming"
        )
    predictions = pd.read_csv(PREDICTIONS_PATH)
    if predictions.empty:
        print("No hay predicciones que graficar.")
        return

    con = duckdb.connect(str(DB_PATH), read_only=True)
    matches = con.execute("select * from staging.stg_matches").fetchdf()
    con.close()

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    saved = []
    for division, div_predictions in predictions.groupby("division"):
        # Mismo ajuste que predict_upcoming: un modelo Poisson por liga, con todo el historial.
        model = fit_poisson(matches[matches["division"] == division])
        for _, row in div_predictions.iterrows():
            lh, la = expected_goals(model, row["home_team"], row["away_team"])
            out_name = f"{division}_{slugify(row['home_team'])}_vs_{slugify(row['away_team'])}.png"
            out_path = PLOTS_DIR / out_name
            plot_match(row["home_team"], row["away_team"], lh, la, out_path)
            saved.append(out_path)

    print(f"Guardadas {len(saved)} imágenes en {PLOTS_DIR}/")
    for path in saved:
        print(f"  {path.name}")


if __name__ == "__main__":
    main()
