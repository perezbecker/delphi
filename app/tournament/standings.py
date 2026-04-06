"""
FIFA group stage standings computation with official tiebreaker rules.
"""

from dataclasses import dataclass, field

from app.tournament.data import (
    TEAMS_BY_GROUP,
    GROUP_MATCHES_BY_GROUP,
    Team,
)


@dataclass
class TeamStanding:
    team: Team
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    gf: int = 0   # goals for
    ga: int = 0   # goals against

    @property
    def points(self) -> int:
        return self.wins * 3 + self.draws

    @property
    def gd(self) -> int:
        return self.gf - self.ga

    def outcome_vs(self, other_code: str, scores: dict[str, tuple[int, int]]) -> int:
        """Return points earned in head-to-head match against other_code."""
        return _h2h_points(self.team.code, other_code, scores)


def _sign(x: int) -> int:
    if x > 0: return 1
    if x < 0: return -1
    return 0


def _h2h_points(code_a: str, code_b: str, scores: dict[str, tuple[int, int]]) -> int:
    """Points earned by code_a in the direct match against code_b."""
    from app.tournament.data import GROUP_MATCH_BY_ID, TEAMS_BY_GROUP
    # find the group for code_a
    for group, teams in TEAMS_BY_GROUP.items():
        codes = [t.code for t in teams]
        if code_a in codes and code_b in codes:
            from app.tournament.data import GROUP_MATCHES_BY_GROUP
            for m in GROUP_MATCHES_BY_GROUP[group]:
                s = scores.get(m.match_id)
                if s is None:
                    continue
                h, a = s
                if m.home_code == code_a and m.away_code == code_b:
                    return 3 if h > a else (1 if h == a else 0)
                if m.away_code == code_a and m.home_code == code_b:
                    return 3 if a > h else (1 if a == h else 0)
    return 0


def compute_group_standings(
    group: str,
    scores: dict[str, tuple[int, int]],  # match_id → (home_score, away_score)
) -> list[TeamStanding]:
    """
    Compute and return the 4 team standings for a group, sorted 1st–4th.
    scores may be partial (missing predictions are treated as not yet played).
    """
    teams = TEAMS_BY_GROUP[group]
    standings: dict[str, TeamStanding] = {t.code: TeamStanding(team=t) for t in teams}

    for match in GROUP_MATCHES_BY_GROUP[group]:
        s = scores.get(match.match_id)
        if s is None:
            continue
        h, a = s
        home_s = standings[match.home_code]
        away_s = standings[match.away_code]
        home_s.played += 1
        away_s.played += 1
        home_s.gf += h
        home_s.ga += a
        away_s.gf += a
        away_s.ga += h
        if h > a:
            home_s.wins += 1
            away_s.losses += 1
        elif h < a:
            away_s.wins += 1
            home_s.losses += 1
        else:
            home_s.draws += 1
            away_s.draws += 1

    sorted_standings = _sort_standings(list(standings.values()), scores)
    return sorted_standings


def _sort_standings(
    standings: list[TeamStanding],
    scores: dict[str, tuple[int, int]],
) -> list[TeamStanding]:
    """Sort using FIFA tiebreaker rules."""
    # Primary sort: points DESC, GD DESC, GF DESC
    standings.sort(key=lambda s: (s.points, s.gd, s.gf, -s.team.fifa_ranking), reverse=True)

    # Resolve ties within contiguous groups with equal points
    result: list[TeamStanding] = []
    i = 0
    while i < len(standings):
        j = i + 1
        while j < len(standings) and standings[j].points == standings[i].points:
            j += 1
        tied = standings[i:j]
        if len(tied) > 1:
            tied = _resolve_tie(tied, scores)
        result.extend(tied)
        i = j
    return result


def _resolve_tie(
    tied: list[TeamStanding],
    scores: dict[str, tuple[int, int]],
) -> list[TeamStanding]:
    """
    Apply FIFA head-to-head tiebreakers among a group of tied teams.
    Falls back to overall GD, GF, then FIFA ranking.
    """
    codes = {s.team.code for s in tied}

    def h2h_stats(st: TeamStanding) -> tuple:
        pts = gd = gf = 0
        for other in tied:
            if other.team.code == st.team.code:
                continue
            p = _h2h_points(st.team.code, other.team.code, scores)
            pts += p
            # head-to-head goals
            from app.tournament.data import GROUP_MATCHES_BY_GROUP, TEAMS_BY_GROUP
            g = st.team.group
            for m in GROUP_MATCHES_BY_GROUP[g]:
                s = scores.get(m.match_id)
                if s is None:
                    continue
                h, a = s
                if m.home_code == st.team.code and m.away_code == other.team.code:
                    gf += h; gd += h - a
                elif m.away_code == st.team.code and m.home_code == other.team.code:
                    gf += a; gd += a - h
        return (pts, gd, gf)

    tied.sort(
        key=lambda s: (h2h_stats(s), s.gd, s.gf, -s.team.fifa_ranking),
        reverse=True,
    )
    return tied
