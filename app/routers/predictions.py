from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import require_user
from app.config import settings
from app.database import get_db
from app.models import Prediction, User
from app.tournament.bracket import compute_user_bracket
from app.tournament.data import (
    BRACKET_F_ORDER,
    BRACKET_QF_ORDER,
    BRACKET_R16_ORDER,
    BRACKET_R32_ORDER,
    BRACKET_SF_ORDER,
    BRACKET_SVG_PATHS,
    BRACKET_TOPS,
    BRACKET_HEIGHT,
    GROUPS,
    GROUP_MATCHES_BY_GROUP,
    ROUND_LABELS,
    TEAM_BY_CODE,
)

router = APIRouter(prefix="/predictions")
templates = Jinja2Templates(directory="templates")


def _get_bracket(user_id: int, db: Session):
    return compute_user_bracket(user_id, db)


def _knockout_context(bracket, locked: bool, readonly: bool) -> dict:
    return {
        "matches_by_id": {ms.match_id: ms for ms in bracket.knockout_matches},
        "bracket_r32_order": BRACKET_R32_ORDER,
        "bracket_r16_order": BRACKET_R16_ORDER,
        "bracket_qf_order": BRACKET_QF_ORDER,
        "bracket_sf_order": BRACKET_SF_ORDER,
        "bracket_f_order": BRACKET_F_ORDER,
        "bracket_tops": BRACKET_TOPS,
        "bracket_height": BRACKET_HEIGHT,
        "bracket_svg_paths": BRACKET_SVG_PATHS,
        "round_labels": ROUND_LABELS,
        "locked": locked,
        "readonly": readonly,
    }


@router.get("", response_class=HTMLResponse)
def predictions_index(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    bracket = _get_bracket(user.id, db)
    locked = settings.is_locked()
    preds = db.query(Prediction).filter(
        Prediction.user_id == user.id,
        Prediction.match_id.like("GS_%"),
    ).all()
    predictions = {p.match_id: (p.home_score, p.away_score) for p in preds if p.home_score is not None}
    all_users = db.query(User).order_by(User.username).all()
    return templates.TemplateResponse(request, "predictions/index.html", {
        "user": user,
        "bracket": bracket,
        "groups": GROUPS,
        "group_matches": GROUP_MATCHES_BY_GROUP,
        "knockout_rounds": ["R32", "R16", "QF", "SF", "F"],
        "round_labels": ROUND_LABELS,
        "locked": locked,
        "predictions": predictions,
        "readonly": False,
        "all_users": all_users,
    })


@router.post("/group/{match_id}", response_class=HTMLResponse)
def save_group_prediction(
    match_id: str,
    request: Request,
    home_score: int = Form(...),
    away_score: int = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if settings.is_locked():
        raise HTTPException(status_code=403, detail="Predictions are locked.")
    if home_score < 0 or away_score < 0 or home_score > 20 or away_score > 20:
        raise HTTPException(status_code=400, detail="Score must be between 0 and 20.")

    existing = db.query(Prediction).filter(
        Prediction.user_id == user.id,
        Prediction.match_id == match_id,
    ).first()
    if existing:
        existing.home_score = home_score
        existing.away_score = away_score
        existing.winner_code = None
    else:
        db.add(Prediction(
            user_id=user.id,
            match_id=match_id,
            home_score=home_score,
            away_score=away_score,
        ))

    # Group stage changes invalidate knockout predictions (teams may have changed),
    # so reset them to let the user re-pick with the updated bracket.
    db.query(Prediction).filter(
        Prediction.user_id == user.id,
        Prediction.match_id.notlike("GS_%"),
    ).delete(synchronize_session=False)
    db.commit()

    bracket = _get_bracket(user.id, db)
    parts = match_id.split("_")
    group = parts[1] if len(parts) >= 2 else "A"
    group_standings = bracket.group_standings.get(group, [])
    locked = settings.is_locked()

    resp = templates.TemplateResponse(request, "predictions/partials/group_card.html", {
        "user": user,
        "group": group,
        "standings": group_standings,
        "matches": GROUP_MATCHES_BY_GROUP[group],
        "predictions": {
            p.match_id: (p.home_score, p.away_score)
            for p in db.query(Prediction).filter(
                Prediction.user_id == user.id,
                Prediction.match_id.like(f"GS_{group}_%"),
                Prediction.home_score.isnot(None),
            )
        },
        "locked": locked,
    })
    resp.headers["HX-Trigger"] = "refreshKnockout"
    return resp


@router.get("/knockout", response_class=HTMLResponse)
def get_knockout_bracket(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    bracket = _get_bracket(user.id, db)
    locked = settings.is_locked()
    return templates.TemplateResponse(request, "predictions/partials/knockout_bracket.html", {
        "user": user, **_knockout_context(bracket, locked, False),
    })


@router.post("/knockout/{match_id}", response_class=HTMLResponse)
def save_knockout_prediction(
    match_id: str,
    request: Request,
    winner_code: str = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if settings.is_locked():
        raise HTTPException(status_code=403, detail="Predictions are locked.")
    if winner_code not in TEAM_BY_CODE:
        raise HTTPException(status_code=400, detail="Unknown team code.")

    existing = db.query(Prediction).filter(
        Prediction.user_id == user.id,
        Prediction.match_id == match_id,
    ).first()
    if existing:
        existing.winner_code = winner_code
        existing.home_score = None
        existing.away_score = None
    else:
        db.add(Prediction(user_id=user.id, match_id=match_id, winner_code=winner_code))
    db.commit()

    bracket = _get_bracket(user.id, db)
    locked = settings.is_locked()
    return templates.TemplateResponse(request, "predictions/partials/knockout_bracket.html", {
        "user": user, **_knockout_context(bracket, locked, False),
    })


@router.get("/{username}", response_class=HTMLResponse)
def view_user_predictions(
    username: str,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not settings.is_locked():
        raise HTTPException(status_code=403, detail="Other users' predictions are hidden until the tournament starts.")
    target = db.query(User).filter(User.username == username).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    bracket = _get_bracket(target.id, db)
    locked = settings.is_locked()
    preds = db.query(Prediction).filter(
        Prediction.user_id == target.id,
        Prediction.match_id.like("GS_%"),
    ).all()
    predictions = {p.match_id: (p.home_score, p.away_score) for p in preds if p.home_score is not None}
    all_users = db.query(User).order_by(User.username).all()
    return templates.TemplateResponse(request, "predictions/index.html", {
        "user": user,
        "target_user": target,
        "readonly": True,
        "bracket": bracket,
        "groups": GROUPS,
        "group_matches": GROUP_MATCHES_BY_GROUP,
        "knockout_rounds": ["R32", "R16", "QF", "SF", "F"],
        "round_labels": ROUND_LABELS,
        "locked": locked,
        "predictions": predictions,
        "all_users": all_users,
    })


@router.get("/{username}/knockout", response_class=HTMLResponse)
def view_user_knockout(
    username: str,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not settings.is_locked():
        raise HTTPException(status_code=403, detail="Other users' predictions are hidden until the tournament starts.")
    target = db.query(User).filter(User.username == username).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    bracket = _get_bracket(target.id, db)
    locked = settings.is_locked()
    return templates.TemplateResponse(request, "predictions/partials/knockout_bracket.html", {
        "user": user, **_knockout_context(bracket, True, True),
    })
