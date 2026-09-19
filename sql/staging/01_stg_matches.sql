-- Staging: partidos jugados, con probabilidades implícitas del mercado (Bet365).
-- Las cuotas incluyen margen de la casa; se normalizan para que sumen 1.
drop table if exists staging.stg_matches;

create table staging.stg_matches as
select
    season_code,
    division,
    match_date,
    home_team,
    away_team,
    home_goals,
    away_goals,
    result,
    odds_home,
    odds_draw,
    odds_away,
    (1.0 / odds_home) / (1.0 / odds_home + 1.0 / odds_draw + 1.0 / odds_away) as market_p_home,
    (1.0 / odds_draw) / (1.0 / odds_home + 1.0 / odds_draw + 1.0 / odds_away) as market_p_draw,
    (1.0 / odds_away) / (1.0 / odds_home + 1.0 / odds_draw + 1.0 / odds_away) as market_p_away
from raw.football_matches
where home_goals is not null
  and away_goals is not null
  and match_date is not null
