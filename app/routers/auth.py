from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import (
    COOKIE_NAME,
    SESSION_MAX_AGE,
    create_session_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.config import settings
from app.database import get_db
from app.models import User

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, user=Depends(get_current_user)):
    if user:
        return RedirectResponse("/predictions", status_code=302)
    return templates.TemplateResponse(request, "auth/login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "Invalid username or password."},
            status_code=401,
        )
    token = create_session_token(user.id)
    resp = RedirectResponse("/predictions", status_code=302)
    resp.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=False,  # set True in production behind HTTPS
    )
    return resp


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, user=Depends(get_current_user)):
    if user:
        return RedirectResponse("/predictions", status_code=302)
    return templates.TemplateResponse(request, "auth/register.html", {"error": None})


@router.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    invite_code: str = Form(...),
    db: Session = Depends(get_db),
):
    if invite_code.strip() != settings.invite_code.strip():
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {"error": "Invalid invite code."},
            status_code=400,
        )
    if len(username) < 3 or len(username) > 50:
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {"error": "Username must be 3–50 characters."},
            status_code=400,
        )
    if len(password) < 6:
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {"error": "Password must be at least 6 characters."},
            status_code=400,
        )
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {"error": "Username already taken."},
            status_code=400,
        )

    is_first_user = db.query(User).count() == 0
    is_admin = is_first_user or (settings.admin_username and username == settings.admin_username)

    user = User(username=username, password_hash=hash_password(password), is_admin=is_admin)
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_session_token(user.id)
    resp = RedirectResponse("/predictions", status_code=302)
    resp.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=False,
    )
    return resp


@router.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie(COOKIE_NAME)
    return resp
