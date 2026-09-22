"""Empareja los nombres de equipo de football-data.org (fixtures) con los nombres cortos
usados por football-data.co.uk (histórico, ya cargado en el warehouse).

Las dos fuentes nombran a los equipos distinto: "Manchester United FC" vs "Man United".
Primero se intenta con una lista de equivalencias conocidas; lo que no coincide se resuelve
por similitud de texto; lo que sigue sin coincidir queda marcado para revisión manual.
"""
import difflib

# Equivalencias conocidas y razonablemente estables entre temporadas. Es un punto de partida:
# revisa siempre el aviso de "sin equivalencia clara" que imprime pipelines.predict_upcoming
# antes de confiar en una predicción (un equipo recién ascendido o un nombre distinto a los de
# aquí no va a coincidir solo, y no se advierte de otra forma).
KNOWN_OVERRIDES = {
    "Manchester United FC": "Man United",
    "Manchester City FC": "Man City",
    "Tottenham Hotspur FC": "Tottenham",
    "Wolverhampton Wanderers FC": "Wolves",
    "Nottingham Forest FC": "Nott'm Forest",
    "Newcastle United FC": "Newcastle",
    "Brighton & Hove Albion FC": "Brighton",
    "West Ham United FC": "West Ham",
    "AFC Bournemouth": "Bournemouth",
    "Leeds United FC": "Leeds",
    "Sunderland AFC": "Sunderland",
    "West Bromwich Albion FC": "West Brom",
    "Real Madrid CF": "Real Madrid",
    "FC Barcelona": "Barcelona",
    "Club Atlético de Madrid": "Ath Madrid",
    "Real Sociedad de Fútbol": "Sociedad",
    "Athletic Club": "Ath Bilbao",
    "Villarreal CF": "Villarreal",
    "Real Betis Balompié": "Betis",
    "Sevilla FC": "Sevilla",
    "Valencia CF": "Valencia",
    "RC Celta de Vigo": "Celta",
    "RCD Espanyol de Barcelona": "Espanol",
    "Getafe CF": "Getafe",
    "Deportivo Alavés": "Alaves",
    "RCD Mallorca": "Mallorca",
    "CA Osasuna": "Osasuna",
    "Girona FC": "Girona",
    "Rayo Vallecano de Madrid": "Vallecano",
    "Elche CF": "Elche",
    "Levante UD": "Levante",
    "Real Oviedo": "Oviedo",
    "Hull City AFC": "Hull",
}


def build_team_name_map(fixture_names: list[str], historical_names: list[str]) -> tuple[dict, list]:
    """Devuelve (mapa fixture->histórico, lista de nombres de fixture sin coincidencia clara)."""
    mapping: dict[str, str | None] = {}
    uncertain: list[str] = []
    for name in fixture_names:
        if name in KNOWN_OVERRIDES and KNOWN_OVERRIDES[name] in historical_names:
            mapping[name] = KNOWN_OVERRIDES[name]
            continue
        close = difflib.get_close_matches(name, historical_names, n=1, cutoff=0.6)
        if close:
            mapping[name] = close[0]
        else:
            mapping[name] = None
            uncertain.append(name)
    return mapping, uncertain
