"""Diagnóstico: ¿son accesibles las fuentes de datos desde ESTA máquina?

Solo usa la librería estándar de Python (no hay que instalar nada).
Uso:  python scripts/check_sources.py
"""
import time
import urllib.error
import urllib.request

SOURCES = [
    ("football-data (Premier, CSV)", "https://www.football-data.co.uk/mmz4281/2526/E0.csv"),
    ("football-data (La Liga, CSV)", "https://www.football-data.co.uk/mmz4281/2526/SP1.csv"),
    ("Understat (página Premier)", "https://understat.com/league/EPL/2025"),
    ("Sleeper API (estado NFL)", "https://api.sleeper.app/v1/state/nfl"),
    ("nflverse (releases en GitHub)", "https://github.com/nflverse/nflverse-data/releases"),
    ("TMDB (documentación API)", "https://developer.themoviedb.org/docs"),
]


def check(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "portafolio-datos/0.1"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read(200_000)
            return f"OK   HTTP {resp.status}, {len(body):>7} bytes leídos, {time.time() - t0:.1f}s"
    except urllib.error.HTTPError as exc:
        return f"FALLA HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - es un diagnóstico, se muestra cualquier error
        return f"FALLA {type(exc).__name__}: {exc}"


if __name__ == "__main__":
    for name, url in SOURCES:
        print(f"{name:<32} {check(url)}")
