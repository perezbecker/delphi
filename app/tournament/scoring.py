"""
Scoring engine: compares user predictions against actual results.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import ActualResult, Prediction, User
from app.tournament.data import ROUND_POINTS, GROUP_MATCH_BY_ID, KNOCKOUT_BY_ID


@dataclass
class ScoreBreakdown:
    total: int = 0
    by_round: dict[str, int] = field(default_factory=lambda: {
        "GS": 0, "R32": 0, "R16": 0, "QF": 0, "SF": 0, "F": 0,
    })
    correct: int = 0   # number of correct predictions
    total_predicted: int = 0


def _gs_outcome(home: int, away: int) -> int:
    """Return 1 (home win), 0 (draw), -1 (away win)."""
    if home > away: return 1
    if home < away: return -1
    return 0


def compute_user_score(user_id: int, db: Session) -> ScoreBreakdown:
    breakdown = ScoreBreakdown()

    predictions = {p.match_id: p for p in db.query(Prediction).filter(Prediction.user_id == user_id)}
    results = {r.match_id: r for r in db.query(ActualResult).filter(ActualResult.completed == True)}

    for match_id, result in results.items():
        pred = predictions.get(match_id)
        if pred is None:
            continue

        if match_id.startswith("GS_"):
            # Group stage: compare outcome (W/D/L)
            if pred.home_score is None or pred.away_score is None:
                continue
            if result.home_score is None or result.away_score is None:
                continue
            breakdown.total_predicted += 1
            if _gs_outcome(pred.home_score, pred.away_score) == _gs_outcome(result.home_score, result.away_score):
                pts = ROUND_POINTS["GS"]
                breakdown.total += pts
                breakdown.by_round["GS"] += pts
                breakdown.correct += 1
        else:
            # Knockout: compare predicted winner code
            if pred.winner_code is None or result.winner_code is None:
                continue
            km = KNOCKOUT_BY_ID.get(match_id)
            if km is None:
                continue
            breakdown.total_predicted += 1
            if pred.winner_code == result.winner_code:
                pts = ROUND_POINTS[km.round]
                breakdown.total += pts
                breakdown.by_round[km.round] += pts
                breakdown.correct += 1

    return breakdown


def compute_all_scores(db: Session) -> dict[int, ScoreBreakdown]:
    """Return a dict of user_id → ScoreBreakdown for all users."""
    users = db.query(User).all()
    return {u.id: compute_user_score(u.id, db) for u in users}
