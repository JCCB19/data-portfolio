-- Mart: tabla de posiciones por temporada y liga, calculada desde los resultados.
drop table if exists marts.mart_standings;

create table marts.mart_standings as
with agg as (
    select
        season_code, division, team,
        count(*)                                     as played,
        sum(case when points = 3 then 1 else 0 end)  as wins,
        sum(case when points = 1 then 1 else 0 end)  as draws,
        sum(case when points = 0 then 1 else 0 end)  as losses,
        sum(goals_for)                               as goals_for,
        sum(goals_against)                           as goals_against,
        sum(goals_for) - sum(goals_against)          as goal_diff,
        sum(points)                                  as points
    from marts.mart_team_form
    group by season_code, division, team
)
select
    *,
    rank() over (partition by season_code, division
                 order by points desc, goal_diff desc, goals_for desc) as position
from agg
order by season_code, division, position
