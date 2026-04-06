from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import User
from app.routers import admin, auth, leaderboard, predictions


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables (Alembic handles migrations in production; this is a dev fallback)
    Base.metadata.create_all(bind=engine)
    # Promote ADMIN_USERNAME to admin if set
    if settings.admin_username:
        db: Session = SessionLocal()
        try:
            user = db.query(User).filter(User.username == settings.admin_username).first()
            if user and not user.is_admin:
                user.is_admin = True
                db.commit()
        finally:
            db.close()
    yield


app = FastAPI(title="Delphi — World Cup 2026 Predictions", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/images", StaticFiles(directory="images"), name="images")

app.include_router(auth.router)
app.include_router(predictions.router)
app.include_router(leaderboard.router)
app.include_router(admin.router)

templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
def root(request: Request, user: User = Depends(get_current_user)):
    if user:
        return RedirectResponse("/predictions", status_code=302)
    return templates.TemplateResponse(request, "home.html", {"user": None})
