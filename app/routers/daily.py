"""
Public (participant-visible) results views.

- Group stage: one page per calendar date (`/YYYY-MM-DD`) showing every user's
  predictions for that day's games and the points earned.
- Knockout stage: one page per round (`/round/{R32|R16|QF|SF|F}`) showing, as a
  grid, the teams every user picked to win that round with correct picks
  highlighted.
- `/today` resolves to whichever view is current.

Only available once predictions are locked (`settings.is_locked()`), read live on
each request so moving TOURNAMENT_START into the future re-hides these views. All
maths is read straight from the scoring engine (`compute_all_scores`), so these
views can never diverge from the leaderboard.
"""

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import require_user
from app.config import settings
from app.database import get_db
from app.models import Prediction, ActualResult, User
from app.tournament.data import (
    GROUP_MATCH_BY_ID,
    KNOCKOUT_BY_ID,
    KNOCKOUT_BY_ROUND,
    MATCH_DATE,
    MATCHES_BY_DATE,
    ROUND_LABELS,
    ROUND_POINTS,
    TEAM_BY_CODE,
)
from app.tournament.scoring import compute_all_scores

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["is_locked"] = settings.is_locked


# ── Timeline: group-stage dates, then knockout rounds ─────────────────────────
ROUND_ORDER = ["R32", "R16", "QF", "SF", "F"]

GS_DATES = sorted({d for mid, d in MATCH_DATE.items() if mid.startswith("GS_")})
LAST_GS_DATE = GS_DATES[-1]
KO_ROUND_RANGE: dict[str, tuple[date, date]] = {
    r: (min(MATCH_DATE[m.match_id] for m in KNOCKOUT_BY_ROUND[r]),
        max(MATCH_DATE[m.match_id] for m in KNOCKOUT_BY_ROUND[r]))
    for r in ROUND_ORDER
}

# Ordered list of "views" for prev/next navigation across the whole tournament.
_VIEW_SEQUENCE = [
    {"sort_date": d, "url": f"/{d.isoformat()}", "label": d.strftime("%b %-d")}
    for d in GS_DATES
] + [
    {"sort_date": KO_ROUND_RANGE[r][0], "url": f"/round/{r}", "label": ROUND_LABELS[r]}
    for r in ROUND_ORDER
]


def _nav_links(sort_date: date) -> tuple[dict | None, dict | None]:
    """Previous / next view (by timeline position) as {url, label} dicts."""
    prev_item = next_item = None
    for item in _VIEW_SEQUENCE:
        if item["sort_date"] < sort_date:
            prev_item = item
        elif item["sort_date"] > sort_date and next_item is None:
            next_item = item
    fmt = lambda it: {"url": it["url"], "label": it["label"]} if it else None
    return fmt(prev_item), fmt(next_item)


def _round_for_date(d: date) -> str:
    """The knockout round to show for a given date (upcoming round on rest days)."""
    for r in ROUND_ORDER:
        if KO_ROUND_RANGE[r][1] >= d:
            return r
    return "F"


def _require_locked():
    if not settings.is_locked():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This view is hidden until the tournament starts.",
        )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/today")
def today(user: User = Depends(require_user)):
    _require_locked()
    today_d = datetime.now(tz=timezone.utc).date()
    if today_d <= LAST_GS_DATE:
        target = f"/{today_d.isoformat()}"
    else:
        target = f"/round/{_round_for_date(today_d)}"
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/round/{round_code}", response_class=HTMLResponse)
def ko_round(
    request: Request,
    round_code: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    rc = round_code.upper()
    if rc not in KNOCKOUT_BY_ROUND:
        raise HTTPException(status_code=404, detail="Unknown round.")
    _require_locked()

    matches = KNOCKOUT_BY_ROUND[rc]
    match_ids = [m.match_id for m in matches]
    results = {
        r.match_id: r
        for r in db.query(ActualResult).filter(ActualResult.match_id.in_(match_ids))
    }
    # "Actual winners" header row: one cell per match, in match order.
    actual_cells = []
    for mid in match_ids:
        r = results.get(mid)
        team = TEAM_BY_CODE.get(r.winner_code) if (r and r.completed and r.winner_code) else None
        actual_cells.append(team)
    decided_count = sum(1 for t in actual_cells if t is not None)

    users = db.query(User).order_by(User.username).all()
    scores = compute_all_scores(db)
    pred_rows = db.query(Prediction).filter(Prediction.match_id.in_(match_ids)).all()
    preds = {(p.user_id, p.match_id): p for p in pred_rows}

    user_rows = []
    for u in users:
        correct_set = scores[u.id].ko_correct_picks.get(rc, set())
        cells = []
        for mid in match_ids:
            p = preds.get((u.id, mid))
            team = TEAM_BY_CODE.get(p.winner_code) if (p and p.winner_code) else None
            cells.append({
                "team": team,
                "correct": team is not None and team.code in correct_set,
            })
        user_rows.append({
            "user": u,
            "cells": cells,
            "points": scores[u.id].by_round[rc],      # straight from the engine
            "correct_count": sum(1 for c in cells if c["correct"]),
        })

    # Order like a per-round mini-leaderboard; assign ranks (ties share a rank).
    user_rows.sort(key=lambda r: (-r["points"], r["user"].username.lower()))
    rank = 1
    for i, row in enumerate(user_rows):
        if i > 0 and row["points"] < user_rows[i - 1]["points"]:
            rank = i + 1
        row["rank"] = rank

    prev_link, next_link = _nav_links(KO_ROUND_RANGE[rc][0])
    start, end = KO_ROUND_RANGE[rc]
    today_d = datetime.now(tz=timezone.utc).date()

    return templates.TemplateResponse(request, "ko_round.html", {
        "user": user,
        "round_code": rc,
        "round_label": ROUND_LABELS[rc],
        "round_points": ROUND_POINTS[rc],
        "num_matches": len(match_ids),
        "actual_cells": actual_cells,
        "decided_count": decided_count,
        "user_rows": user_rows,
        "prev_link": prev_link,
        "next_link": next_link,
        "is_today": start <= today_d <= end,
    })


@router.get("/{match_date}", response_class=HTMLResponse)
def daily(
    request: Request,
    match_date: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    # This route is greedy (any single path segment), so it is registered last in
    # main.py and 404s anything that is not an ISO date.
    try:
        d = date.fromisoformat(match_date)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found.")
    _require_locked()

    # Knockout dates are presented per-round, not per-date.
    if d > LAST_GS_DATE:
        return RedirectResponse(f"/round/{_round_for_date(d)}",
                                status_code=status.HTTP_303_SEE_OTHER)

    match_ids = MATCHES_BY_DATE.get(d, [])
    users = db.query(User).order_by(User.username).all()

    # Predictions for just this day's matches, keyed by (user_id, match_id).
    preds: dict[tuple[int, str], Prediction] = {}
    results: dict[str, ActualResult] = {}
    scores = {}
    if match_ids:
        rows = db.query(Prediction).filter(Prediction.match_id.in_(match_ids)).all()
        preds = {(p.user_id, p.match_id): p for p in rows}
        results = {
            r.match_id: r
            for r in db.query(ActualResult).filter(ActualResult.match_id.in_(match_ids))
        }
        scores = compute_all_scores(db)

    matches = []
    day_totals: dict[int, int] = {u.id: 0 for u in users}

    for mid in match_ids:
        result = results.get(mid)
        completed = bool(result and result.completed)
        gm = GROUP_MATCH_BY_ID[mid]
        heading = {"home": gm.home, "away": gm.away}
        round_label = "Group " + gm.group
        round_points = ROUND_POINTS["GS"]
        if completed and result.home_score is not None:
            actual = f"{result.home_score}–{result.away_score}"
        else:
            actual = None

        user_rows = []
        for u in users:
            p = preds.get((u.id, mid))
            if p and p.home_score is not None and p.away_score is not None:
                pred_display = f"{p.home_score}–{p.away_score}"
            else:
                pred_display = None
            pts = scores[u.id].points_by_match.get(mid, 0) if completed else None
            if pts:
                day_totals[u.id] += pts
            user_rows.append({
                "user": u,
                "pred_display": pred_display,
                "points": pts,  # None until completed
            })

        matches.append({
            "match_id": mid,
            "round_label": round_label,
            "round_points": round_points,
            "heading": heading,
            "completed": completed,
            "actual": actual,
            "user_rows": user_rows,
        })

    any_completed = any(m["completed"] for m in matches)
    totals_ranked = sorted(
        ({"user": u, "points": day_totals[u.id]} for u in users),
        key=lambda r: r["points"], reverse=True,
    )

    prev_link, next_link = _nav_links(d)
    today_d = datetime.now(tz=timezone.utc).date()

    return templates.TemplateResponse(request, "daily.html", {
        "user": user,
        "the_date": d,
        "is_today": d == today_d,
        "prev_link": prev_link,
        "next_link": next_link,
        "matches": matches,
        "totals_ranked": totals_ranked,
        "any_completed": any_completed,
        "num_users": len(users),
    })
