"""
Scoring engine: compares user predictions against actual results.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import ActualResult, Prediction, User
from app.tournament.data import ROUND_POINTS, GROUP_MATCH_BY_ID, KNOCKOUT_BY_ID

TOTAL_GS_MATCHES = len(GROUP_MATCH_BY_ID)  # 72
TOTAL_KO_MATCHES = len(KNOCKOUT_BY_ID)     # 31
TOTAL_MATCHES = TOTAL_GS_MATCHES + TOTAL_KO_MATCHES  # 103


@dataclass
class ScoreBreakdown:
    total: int = 0
    by_round: dict[str, int] = field(default_factory=lambda: {
        "GS": 0, "R32": 0, "R16": 0, "QF": 0, "SF": 0, "F": 0,
    })
    predictions_made: int = 0  # number of matches the user has filled in
    exact_scores: int = 0  # group-stage matches with the exact predicted score
    gs_correct: int = 0    # group-stage matches with the correct outcome (includes exact scores)
    ko_correct: int = 0    # knockout teams correctly picked to advance, summed across all rounds
    # Points earned per match_id. Sums to `total`; lets callers (e.g. the daily
    # view) attribute points to a specific day without diverging from the totals.
    points_by_match: dict[str, int] = field(default_factory=dict)
    # round → set of team codes the user correctly picked to win that round
    # (predicted-winners ∩ actual-winners). Authoritative source for the per-round
    # view's highlighting, so it can never diverge from the scoring above:
    # len(ko_correct_picks[r]) * ROUND_POINTS[r] == by_round[r].
    ko_correct_picks: dict[str, set[str]] = field(default_factory=dict)


def _gs_outcome(home: int, away: int) -> int:
    """Return 1 (home win), 0 (draw), -1 (away win)."""
    if home > away: return 1
    if home < away: return -1
    return 0


def compute_user_score(user_id: int, db: Session) -> ScoreBreakdown:
    breakdown = ScoreBreakdown()

    predictions = {p.match_id: p for p in db.query(Prediction).filter(Prediction.user_id == user_id)}
    results = {r.match_id: r for r in db.query(ActualResult).filter(ActualResult.completed == True)}

    breakdown.predictions_made = sum(
        1 for p in predictions.values()
        if (p.match_id.startswith("GS_") and p.home_score is not None and p.away_score is not None)
        or (not p.match_id.startswith("GS_") and p.winner_code is not None)
    )

    # Group stage: compare outcome (W/D/L)
    for match_id, result in results.items():
        if not match_id.startswith("GS_"):
            continue
        pred = predictions.get(match_id)
        if pred is None:
            continue
        if pred.home_score is None or pred.away_score is None:
            continue
        if result.home_score is None or result.away_score is None:
            continue
        if _gs_outcome(pred.home_score, pred.away_score) == _gs_outcome(result.home_score, result.away_score):
            if pred.home_score == result.home_score and pred.away_score == result.away_score:
                pts = 3  # Exact score match
                breakdown.exact_scores += 1
            else:
                pts = ROUND_POINTS["GS"]  # Correct outcome only
            breakdown.total += pts
            breakdown.by_round["GS"] += pts
            breakdown.points_by_match[match_id] = pts
            breakdown.gs_correct += 1

    # Knockout: round-based — award points if the predicted team won in that round,
    # regardless of which specific match slot they ended up in.
    actual_by_round: defaultdict[str, set[str]] = defaultdict(set)
    for match_id, result in results.items():
        if match_id.startswith("GS_") or not result.winner_code:
            continue
        km = KNOCKOUT_BY_ID.get(match_id)
        if km:
            actual_by_round[km.round].add(result.winner_code)

    pred_by_round: defaultdict[str, set[str]] = defaultdict(set)
    for match_id, pred in predictions.items():
        if match_id.startswith("GS_") or not pred.winner_code:
            continue
        km = KNOCKOUT_BY_ID.get(match_id)
        if km:
            pred_by_round[km.round].add(pred.winner_code)

    correct_by_round: dict[str, set[str]] = {}
    for round_name, actual_winners in actual_by_round.items():
        round_preds = pred_by_round.get(round_name, set())
        correct_picks = round_preds & actual_winners
        correct_by_round[round_name] = correct_picks
        pts = len(correct_picks) * ROUND_POINTS[round_name]
        breakdown.total += pts
        breakdown.by_round[round_name] += pts
        breakdown.ko_correct += len(correct_picks)
    breakdown.ko_correct_picks = correct_by_round

    # Attribute each round's points to the actual match where the correctly-picked
    # team won. A team wins at most one match per round, so the per-match sum equals
    # the round total computed above (keeps daily totals consistent with the leaderboard).
    for match_id, result in results.items():
        km = KNOCKOUT_BY_ID.get(match_id)
        if km is None or not result.winner_code:
            continue
        if result.winner_code in correct_by_round.get(km.round, set()):
            breakdown.points_by_match[match_id] = ROUND_POINTS[km.round]

    return breakdown


def compute_all_scores(db: Session) -> dict[int, ScoreBreakdown]:
    """Return a dict of user_id → ScoreBreakdown for all users."""
    users = db.query(User).all()
    return {u.id: compute_user_score(u.id, db) for u in users}
