from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import require_user
from app.database import get_db
from app.models import User
from app.tournament.scoring import ScoreBreakdown, compute_all_scores

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/leaderboard", response_class=HTMLResponse)
def leaderboard(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    scores = compute_all_scores(db)
    users = db.query(User).all()

    rows = []
    for u in users:
        sb = scores.get(u.id, ScoreBreakdown())
        rows.append({"user": u, "score": sb})

    rows.sort(key=lambda r: r["score"].total, reverse=True)
    # Assign ranks (ties share same rank)
    rank = 1
    for i, row in enumerate(rows):
        if i > 0 and row["score"].total < rows[i - 1]["score"].total:
            rank = i + 1
        row["rank"] = rank

    return templates.TemplateResponse(request, "leaderboard.html", {
        "user": user,
        "rows": rows,
    })
