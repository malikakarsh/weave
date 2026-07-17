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

import jwt
from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select

from api.db import SessionLocal
from api.db_models import User

# ── config ────────────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-insecure-change-me")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

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
        "sub": user["sub"],
        "email": user.get("email"),
        "name": user.get("name"),
        "picture": user.get("picture"),
        "iat": now,
        "exp": now + JWT_TTL_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def _decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        return None


async def _upsert_user(info: dict) -> None:
    """Create or update the user's row from their Google profile on each login."""
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
        await db.commit()


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
    return _decode_token(token)


def current_user_required(request: Request) -> dict:
    """Return the logged-in user's claims, or raise 401. Use to protect routes."""
    user = current_user_optional(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# ── routes ────────────────────────────────────────────────────────────────
@router.get("/login/google")
async def login_google(request: Request):
    """Kick off the Google OAuth consent flow."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured")
    redirect_uri = str(request.url_for("auth_google_callback"))
    return await oauth.google.authorize_redirect(request, redirect_uri)


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

    await _upsert_user(info)

    session_jwt = _mint_token({
        "sub": info["sub"],
        "email": info.get("email"),
        "name": info.get("name"),
        "picture": info.get("picture"),
    })
    response = RedirectResponse(FRONTEND_URL)
    _set_session_cookie(response, session_jwt)
    return response


@router.get("/me")
async def me(user: dict | None = Depends(current_user_optional)):
    """Return the current user's profile, or 401 if not signed in."""
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "sub": user["sub"],
        "email": user.get("email"),
        "name": user.get("name"),
        "picture": user.get("picture"),
        "expires_at": datetime.fromtimestamp(user["exp"], tz=timezone.utc).isoformat(),
    }


@router.post("/logout")
async def logout():
    """Clear the session cookie."""
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response
