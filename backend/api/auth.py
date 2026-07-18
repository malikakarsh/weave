"""Google OAuth login with a FastAPI-owned JWT session.

The backend is the single source of truth for identity. Google is used only to
authenticate the user; once verified we mint our OWN short-lived JWT and store
it in an httpOnly cookie. Every subsequent request carries that cookie, and
`get_current_user` decodes it — no Google round-trip per request, and no user
table needed yet (the JWT carries the identity until persistence lands).
"""

import os
import time
from datetime import datetime, timezone

import uuid

import jwt
from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, select, update

from api import usage
from api.db import SessionLocal
from api.db_models import User

# ── config ────────────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-insecure-change-me")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
# Emails that get the admin role (unlimited, full access), comma-separated.
ADMIN_EMAILS = {
    e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()
}

JWT_ALG = "HS256"
JWT_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
COOKIE_NAME = "weave_session"
# In dev, frontend (localhost:3000) and backend (localhost:8000) share the site
# "localhost", so SameSite=Lax cookies flow on same-site fetches and on the
# top-level OAuth callback redirect. In prod behind HTTPS, set COOKIE_SECURE=1.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "").lower() in ("1", "true", "yes")

oauth = OAuth()
oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

router = APIRouter(prefix="/auth", tags=["auth"])


# ── JWT helpers ───────────────────────────────────────────────────────────
def _mint_token(user: dict) -> str:
    now = int(time.time())
    payload = {
        "sub": user["sub"],          # Google's stable subject id
        "uid": user["uid"],          # our User row UUID — DB key for usage/threads
        "email": user.get("email"),
        "name": user.get("name"),
        "picture": user.get("picture"),
        "role": user.get("role", "user"),
        "iat": now,
        "exp": now + JWT_TTL_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def _decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        return None


async def _upsert_user(info: dict) -> tuple[str, str]:
    """Create or update the user's row from their Google profile on each login.
    Returns (role, user_row_uuid). Admin if the email is in ADMIN_EMAILS."""
    role = "admin" if (info.get("email") or "").lower() in ADMIN_EMAILS else "user"
    async with SessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.google_sub == info["sub"]))
        ).scalar_one_or_none()
        if user is None:
            user = User(google_sub=info["sub"])
            db.add(user)
        user.email = info.get("email")
        user.name = info.get("name")
        user.picture = info.get("picture")
        user.role = role
        await db.commit()
        await db.refresh(user)
        return role, str(user.id)


def _set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=JWT_TTL_SECONDS,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


# ── dependencies ──────────────────────────────────────────────────────────
def current_user_optional(request: Request) -> dict | None:
    """Return the logged-in user's claims, or None if not authenticated."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    claims = _decode_token(token)
    # Tokens minted before the 'uid' claim existed can't key DB rows — treat
    # them as logged-out so the user re-authenticates and gets a fresh token.
    if claims is not None and "uid" not in claims:
        return None
    return claims


def current_user_required(request: Request) -> dict:
    """Return the logged-in user's claims, or raise 401. Use to protect routes."""
    user = current_user_optional(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def require_admin(user: dict = Depends(current_user_required)) -> dict:
    """Guard admin-only routes. The role is re-checked against the DB (the
    source of truth) rather than trusting the JWT claim, so admin can be
    revoked instantly and a stale token can't retain access."""
    async with SessionLocal() as db:
        row = await db.get(User, uuid.UUID(user["uid"]))
    if row is None or row.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ── routes ────────────────────────────────────────────────────────────────
@router.get("/login/google")
async def login_google(request: Request):
    """Kick off the Google OAuth consent flow."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured")
    redirect_uri = str(request.url_for("auth_google_callback"))
    # prompt=select_account forces Google's account chooser so the user can pick
    # a different email instead of being silently signed in with the active one.
    return await oauth.google.authorize_redirect(request, redirect_uri, prompt="select_account")


@router.get("/google/callback", name="auth_google_callback")
async def google_callback(request: Request):
    """Exchange the code, verify the Google profile, mint our JWT, redirect back."""
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError:
        return RedirectResponse(f"{FRONTEND_URL}?auth_error=1")

    info = token.get("userinfo") or {}
    if not info.get("sub"):
        return RedirectResponse(f"{FRONTEND_URL}?auth_error=1")

    role, uid = await _upsert_user(info)

    session_jwt = _mint_token({
        "sub": info["sub"],
        "uid": uid,
        "email": info.get("email"),
        "name": info.get("name"),
        "picture": info.get("picture"),
        "role": role,
    })
    response = RedirectResponse(FRONTEND_URL)
    _set_session_cookie(response, session_jwt)
    return response


@router.get("/me")
async def me(user: dict | None = Depends(current_user_optional)):
    """Return the current user's profile + role and today's usage, or 401."""
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    role = user.get("role", "user")
    admin = role == "admin"
    return {
        "sub": user["sub"],
        "email": user.get("email"),
        "name": user.get("name"),
        "picture": user.get("picture"),
        "role": role,
        "usage": {
            "used": await usage.get_used(user["uid"]),
            "limit": None if admin else await usage.effective_limit(user["uid"]),
            "remaining": await usage.remaining(user),
        },
        "expires_at": datetime.fromtimestamp(user["exp"], tz=timezone.utc).isoformat(),
    }


@router.post("/visit")
async def visit(user: dict = Depends(current_user_required)):
    """Record a page open — bumps the visit count and last-seen time."""
    async with SessionLocal() as db:
        await db.execute(
            update(User)
            .where(User.id == uuid.UUID(user["uid"]))
            .values(visits=User.visits + 1, last_seen_at=func.now())
        )
        await db.commit()
    return {"ok": True}


@router.post("/logout")
async def logout():
    """Clear the session cookie."""
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response
