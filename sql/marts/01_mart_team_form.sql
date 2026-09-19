-- Mart: una fila por equipo y partido, con forma reciente (últimos 5) y acumulado.
-- Base del tablero de KPIs (Liverpool / Barcelona) y de las variables del modelo.
drop table if exists marts.mart_team_form;

create table marts.mart_team_form as
with team_matches as (
    select season_code, division, match_date,
           home_team as team, away_team as opponent, 1 as is_home,
           home_goals as goals_for, away_goals as goals_against
    from staging.stg_matches
    union all
    select season_code, division, match_date,
           away_team as team, home_team as opponent, 0 as is_home,
           away_goals as goals_for, home_goals as goals_against
    from staging.stg_matches
),
scored as (
    select *,
           case when goals_for > goals_against then 3
                when goals_for = goals_against then 1
                else 0 end as points
    from team_matches
)
select
    season_code, division, match_date, team, opponent, is_home,
    goals_for, goals_against, points,
    row_number() over w_all                                                as match_number,
    sum(points) over (partition by season_code, division, team
                      order by match_date
                      rows between unbounded preceding and current row)   as points_cumulative,
    sum(points) over (partition by season_code, division, team
                      order by match_date
                      rows between 4 preceding and current row)           as points_last5,
    avg(goals_for) over (partition by season_code, division, team
                         order by match_date
                         rows between 4 preceding and current row)        as goals_for_avg_last5,
    avg(goals_against) over (partition by season_code, division, team
                             order by match_date
                             rows between 4 preceding and current row)    as goals_against_avg_last5
from scored
window w_all as (partition by season_code, division, team order by match_date)
order by season_code, division, team, match_date
