import csv
import io
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import ActualResult, Prediction, User
from app.tournament.data import (
    GROUP_MATCHES_BY_GROUP,
    GROUPS,
    KNOCKOUT_MATCHES,
    ROUND_LABELS,
    TEAM_BY_CODE,
)

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
def admin_index(request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return RedirectResponse("/admin/results", status_code=302)


@router.get("/results", response_class=HTMLResponse)
def results_page(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    msg: str = "",  # populated via ?msg= query param after import redirect
):
    all_results = {r.match_id: r for r in db.query(ActualResult).all()}
    return templates.TemplateResponse(request, "admin/results.html", {
        "user": user,
        "groups": GROUPS,
        "group_matches": GROUP_MATCHES_BY_GROUP,
        "knockout_matches": KNOCKOUT_MATCHES,
        "round_labels": ROUND_LABELS,
        "results": all_results,
        "team_by_code": TEAM_BY_CODE,
        "flash": msg,
    })


@router.post("/results/group/{match_id}", response_class=HTMLResponse)
def save_group_result(
    match_id: str,
    request: Request,
    home_score: int = Form(...),
    away_score: int = Form(...),
    completed: bool = Form(False),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if home_score < 0 or away_score < 0:
        raise HTTPException(status_code=400, detail="Scores must be non-negative.")

    result = db.get(ActualResult, match_id)
    if result:
        result.home_score = home_score
        result.away_score = away_score
        result.completed = completed
    else:
        db.add(ActualResult(
            match_id=match_id,
            home_score=home_score,
            away_score=away_score,
            completed=completed,
        ))
    db.commit()
    return RedirectResponse("/admin/results#" + match_id, status_code=302)


@router.post("/results/knockout/{match_id}", response_class=HTMLResponse)
def save_knockout_result(
    match_id: str,
    request: Request,
    winner_code: str = Form(...),
    completed: bool = Form(False),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if winner_code not in TEAM_BY_CODE:
        raise HTTPException(status_code=400, detail="Unknown team code.")

    result = db.get(ActualResult, match_id)
    if result:
        result.winner_code = winner_code
        result.completed = completed
    else:
        db.add(ActualResult(
            match_id=match_id,
            winner_code=winner_code,
            completed=completed,
        ))
    db.commit()
    return RedirectResponse("/admin/results#" + match_id, status_code=302)


# ── Backup / Restore ──────────────────────────────────────────────────────────

def _csv_bytes(rows: list[dict], fieldnames: list[str]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


@router.get("/export/backup")
def export_backup(
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    # ── users.csv ────────────────────────────────────────────────────────────
    users_rows = [
        {
            "username": u.username,
            "password_hash": u.password_hash,
            "is_admin": str(u.is_admin).lower(),
            "created_at": u.created_at.isoformat(),
        }
        for u in db.query(User).order_by(User.id).all()
    ]

    # ── predictions.csv ──────────────────────────────────────────────────────
    preds_rows = [
        {
            "username": p.user.username,
            "match_id": p.match_id,
            "home_score": "" if p.home_score is None else p.home_score,
            "away_score": "" if p.away_score is None else p.away_score,
            "winner_code": p.winner_code or "",
        }
        for p in db.query(Prediction).join(User).order_by(User.username, Prediction.match_id).all()
    ]

    # ── results.csv ──────────────────────────────────────────────────────────
    results_rows = [
        {
            "match_id": r.match_id,
            "home_score": "" if r.home_score is None else r.home_score,
            "away_score": "" if r.away_score is None else r.away_score,
            "winner_code": r.winner_code or "",
            "completed": str(r.completed).lower(),
        }
        for r in db.query(ActualResult).order_by(ActualResult.match_id).all()
    ]

    # ── Build ZIP in memory ───────────────────────────────────────────────────
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("users.csv", _csv_bytes(users_rows, ["username", "password_hash", "is_admin", "created_at"]))
        zf.writestr("predictions.csv", _csv_bytes(preds_rows, ["username", "match_id", "home_score", "away_score", "winner_code"]))
        zf.writestr("results.csv", _csv_bytes(results_rows, ["match_id", "home_score", "away_score", "winner_code", "completed"]))
    zip_buf.seek(0)

    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    filename = f"delphi_backup_{date_str}.zip"

    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import/backup", response_class=HTMLResponse)
def import_backup(
    request: Request,
    backup_file: UploadFile = File(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not backup_file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload must be a .zip file.")

    try:
        zip_bytes = backup_file.file.read()
        zip_buf = io.BytesIO(zip_bytes)

        with zipfile.ZipFile(zip_buf, "r") as zf:
            names = zf.namelist()
            if not all(f in names for f in ["users.csv", "predictions.csv", "results.csv"]):
                raise HTTPException(status_code=400, detail="ZIP must contain users.csv, predictions.csv, results.csv.")

            def read_csv(filename: str) -> list[dict]:
                text = zf.read(filename).decode("utf-8")
                return list(csv.DictReader(io.StringIO(text)))

            users_rows = read_csv("users.csv")
            preds_rows = read_csv("predictions.csv")
            results_rows = read_csv("results.csv")

        # ── Full restore inside one transaction ───────────────────────────────
        # Delete in dependency order
        db.query(Prediction).delete()
        db.query(User).delete()
        db.query(ActualResult).delete()
        db.flush()

        # Re-insert users
        username_to_id: dict[str, int] = {}
        for row in users_rows:
            u = User(
                username=row["username"],
                password_hash=row["password_hash"],
                is_admin=row["is_admin"].lower() == "true",
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            db.add(u)
            db.flush()  # get the auto-assigned id
            username_to_id[u.username] = u.id

        # Re-insert predictions
        for row in preds_rows:
            uid = username_to_id.get(row["username"])
            if uid is None:
                continue
            db.add(Prediction(
                user_id=uid,
                match_id=row["match_id"],
                home_score=int(row["home_score"]) if row["home_score"] != "" else None,
                away_score=int(row["away_score"]) if row["away_score"] != "" else None,
                winner_code=row["winner_code"] or None,
            ))

        # Re-insert actual results
        for row in results_rows:
            db.add(ActualResult(
                match_id=row["match_id"],
                home_score=int(row["home_score"]) if row["home_score"] != "" else None,
                away_score=int(row["away_score"]) if row["away_score"] != "" else None,
                winner_code=row["winner_code"] or None,
                completed=row["completed"].lower() == "true",
            ))

        db.commit()

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Import failed: {e}")

    return RedirectResponse("/admin/results?msg=Backup+restored+successfully.", status_code=302)
