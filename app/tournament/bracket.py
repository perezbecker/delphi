"""
Per-user bracket computation.
Resolves group stage predictions → group standings → best-3rd-place assignment
→ knockout bracket populated with actual teams + predicted winners.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import Prediction
from app.tournament.data import (
    GROUPS,
    KNOCKOUT_MATCHES,
    KNOCKOUT_BY_NUM,
    Team,
    TEAM_BY_CODE,
    TEAMS_BY_GROUP,
)
from app.tournament.standings import TeamStanding, compute_group_standings


@dataclass
class MatchState:
    match_id: str
    round: str
    match_num: int
    home_team: Team | None
    away_team: Team | None
    predicted_winner: Team | None  # None = not yet predicted


@dataclass
class BracketState:
    group_standings: dict[str, list[TeamStanding]]  # group → [1st, 2nd, 3rd, 4th]
    slot_map: dict[str, Team]                        # slot_key → Team
    knockout_matches: list[MatchState]
    is_complete: bool  # True if every match has a predicted winner


def load_user_predictions(user_id: int, db: Session) -> dict[str, tuple[int, int] | str]:
    """
    Returns a dict of match_id → value.
    Group stage: (home_score, away_score)
    Knockout:    winner_code (str)
    """
    preds = db.query(Prediction).filter(Prediction.user_id == user_id).all()
    result: dict[str, tuple[int, int] | str] = {}
    for p in preds:
        if p.home_score is not None and p.away_score is not None:
            result[p.match_id] = (p.home_score, p.away_score)
        elif p.winner_code:
            result[p.match_id] = p.winner_code
    return result


def _assign_third_place_teams(
    group_standings: dict[str, list[TeamStanding]],
) -> dict[str, Team]:
    """
    Select best 8 of 12 third-place teams and assign them to R32 slots.

    Third-place slots and their eligible source groups:
        M74: {A,B,C,D,F}
        M77: {C,D,F,G,H}
        M79: {C,E,F,H,I}
        M80: {E,H,I,J,K}
        M81: {B,E,F,I,J}
        M82: {A,E,H,I,J}
        M85: {E,F,G,I,J}
        M87: {D,E,I,J,L}

    Uses backtracking to find a valid assignment (always fast: 8 slots / 8 teams).
    Falls back to best available if standings are incomplete.
    Returns dict: "3rd_M{n}" → Team.
    """
    # Collect all 3rd-place teams with ranking key
    third_teams: list[tuple[tuple, str, Team]] = []  # (sort_key, group, team)
    for group in GROUPS:
        standings = group_standings.get(group, [])
        if len(standings) >= 3:
            s = standings[2]
            key = (-s.points, -s.gd, -s.gf, s.team.fifa_ranking)
            third_teams.append((key, group, s.team))

    third_teams.sort(key=lambda x: x[0])
    top8 = third_teams[:8]
    qualifying_groups = {g for _, g, _ in top8}

    # R32 third-place slot definitions: match_num → eligible groups
    THIRD_SLOTS: list[tuple[int, frozenset[str]]] = [
        (74, frozenset("ABCDF")),
        (77, frozenset("CDFGH")),
        (79, frozenset("CEFHI")),
        (80, frozenset("EHIJK")),
        (81, frozenset("BEFIJ")),
        (82, frozenset("AEHIJ")),
        (85, frozenset("EFGIJ")),
        (87, frozenset("DEIJL")),
    ]

    # Sort slots by number of eligible qualifying groups (most constrained first)
    def slot_constraint(slot: tuple[int, frozenset[str]]) -> int:
        return len(slot[1] & qualifying_groups)

    slots_sorted = sorted(THIRD_SLOTS, key=slot_constraint)

    # Build: group → team dict for quick lookup
    group_to_team = {g: t for _, g, t in top8}

    # Backtracking assignment
    assignment: dict[int, str] = {}   # match_num → group letter
    used_groups: set[str] = set()

    def backtrack(idx: int) -> bool:
        if idx == len(slots_sorted):
            return True
        match_num, eligible = slots_sorted[idx]
        available = (eligible & qualifying_groups) - used_groups
        # Sort available groups by their team's ranking (best first)
        available_sorted = sorted(
            available,
            key=lambda g: next(key for key, grp, _ in top8 if grp == g),
        )
        for g in available_sorted:
            assignment[match_num] = g
            used_groups.add(g)
            if backtrack(idx + 1):
                return True
            used_groups.discard(g)
            del assignment[match_num]
        return False

    backtrack(0)

    return {f"3rd_M{n}": group_to_team[g] for n, g in assignment.items() if g in group_to_team}


def compute_user_bracket(user_id: int, db: Session) -> BracketState:
    """Compute the full bracket state for a user based on their predictions."""
    predictions = load_user_predictions(user_id, db)

    # ── Step 1: Group standings ───────────────────────────────────────────────
    group_scores: dict[str, dict[str, tuple[int, int]]] = {g: {} for g in GROUPS}
    for match_id, value in predictions.items():
        if match_id.startswith("GS_") and isinstance(value, tuple):
            parts = match_id.split("_")  # ["GS", group, n]
            group = parts[1]
            group_scores[group][match_id] = value

    group_standings: dict[str, list[TeamStanding]] = {}
    for group in GROUPS:
        group_standings[group] = compute_group_standings(group, group_scores[group])

    # ── Step 2: Build slot map ────────────────────────────────────────────────
    slot_map: dict[str, Team] = {}
    for group, standings in group_standings.items():
        if len(standings) >= 1:
            slot_map[f"W_{group}"] = standings[0].team
        if len(standings) >= 2:
            slot_map[f"RU_{group}"] = standings[1].team

    # Assign 3rd-place teams to R32 slots
    third_assignments = _assign_third_place_teams(group_standings)
    slot_map.update(third_assignments)

    # ── Step 3: Build knockout bracket ───────────────────────────────────────
    match_states: list[MatchState] = []
    winner_by_num: dict[int, Team] = {}  # match_num → predicted winner team

    for km in KNOCKOUT_MATCHES:
        home_team = _resolve_slot(km.home_slot, slot_map, winner_by_num)
        away_team = _resolve_slot(km.away_slot, slot_map, winner_by_num)

        pred = predictions.get(km.match_id)
        predicted_winner: Team | None = None
        if isinstance(pred, str) and pred in TEAM_BY_CODE:
            predicted_winner = TEAM_BY_CODE[pred]
            winner_by_num[km.match_num] = predicted_winner

        match_states.append(MatchState(
            match_id=km.match_id,
            round=km.round,
            match_num=km.match_num,
            home_team=home_team,
            away_team=away_team,
            predicted_winner=predicted_winner,
        ))

    # Determine completeness
    total_matches = 72 + len(KNOCKOUT_MATCHES)
    predicted_gs = sum(
        1 for mid, v in predictions.items()
        if mid.startswith("GS_") and isinstance(v, tuple)
    )
    predicted_ko = sum(
        1 for ms in match_states if ms.predicted_winner is not None
    )
    is_complete = (predicted_gs == 72 and predicted_ko == len(KNOCKOUT_MATCHES))

    return BracketState(
        group_standings=group_standings,
        slot_map=slot_map,
        knockout_matches=match_states,
        is_complete=is_complete,
    )


def _resolve_slot(
    slot: str,
    slot_map: dict[str, Team],
    winner_by_num: dict[int, Team],
) -> Team | None:
    """Resolve a slot string to a Team, or None if not yet determinable."""
    if slot in slot_map:
        return slot_map[slot]
    if slot.startswith("W_M"):
        num = int(slot[3:])
        return winner_by_num.get(num)
    if slot.startswith("3rd_M"):
        return slot_map.get(slot)
    return None
