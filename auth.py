"""
Authentification utilisateur via Supabase Auth.

Wrapper Flask :
- signup_user(email, password, full_name) → crée le compte
- login_user(email, password) → renvoie tokens (access + refresh)
- get_current_user() → décode le JWT en session, renvoie le profil enrichi
- require_login / require_admin → décorateurs Flask
- bootstrap_admin(email) → marque un profil existant comme admin (utilisé
  par CLI ou variable d'env `ADMIN_BOOTSTRAP_EMAIL` au démarrage).

La session Flask stocke uniquement les tokens Supabase (access + refresh) et
le user_id ; on ne duplique pas le profil. Le profil est récupéré à la volée.
"""
from __future__ import annotations

import os
from functools import wraps
from typing import Any, Callable, Optional

from flask import abort, jsonify, redirect, request, session, url_for

from db import service_client, supabase_configured, user_client

SESSION_KEY_ACCESS = "sb_access_token"
SESSION_KEY_REFRESH = "sb_refresh_token"
SESSION_KEY_USER_ID = "sb_user_id"
SESSION_KEY_EMAIL = "sb_email"


# =========================================================================
# Auth primitives
# =========================================================================

class AuthError(Exception):
    pass


def signup_user(email: str, password: str, full_name: str = "") -> dict[str, Any]:
    """Crée un compte Supabase et retourne {user, session}.

    On utilise l'API admin (service_role) pour créer le compte avec
    `email_confirm=true` afin que l'utilisateur puisse se connecter
    immédiatement, sans cliquer un lien de confirmation. Pour un futur
    durcissement (envoi d'email de vérification réel), il suffira de
    repasser sur `auth.sign_up()`.
    """
    email = (email or "").strip().lower()
    password = password or ""
    if not email or not password:
        raise AuthError("Email et mot de passe requis.")
    if len(password) < 6:
        raise AuthError("Mot de passe trop court (6 caractères minimum).")

    admin_sb = service_client()
    try:
        admin_sb.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"full_name": full_name or ""},
        })
    except Exception as e:
        msg = str(e).lower()
        if "already" in msg or "exist" in msg or "registered" in msg:
            raise AuthError("Un compte existe déjà pour cette adresse.") from e
        raise AuthError(f"Inscription impossible : {e}") from e

    # Connecte directement via password.
    return login_user(email, password)


def login_user(email: str, password: str) -> dict[str, Any]:
    """Connecte un user et renvoie {user, session}."""
    email = (email or "").strip().lower()
    password = password or ""
    if not email or not password:
        raise AuthError("Email et mot de passe requis.")
    sb = user_client()
    try:
        res = sb.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as e:
        # Supabase remonte typiquement "Invalid login credentials".
        raise AuthError(f"Connexion impossible : {e}") from e
    if not res.session or not res.user:
        raise AuthError("Identifiants invalides.")
    profile = _fetch_profile(str(res.user.id))
    if profile and profile.get("is_suspended"):
        # Compte bloqué par un admin → on refuse la connexion immédiatement.
        try:
            sb.auth.sign_out()
        except Exception:
            pass
        raise AuthError("Ce compte est suspendu. Contactez l'administrateur.")
    return {"user": res.user, "session": res.session}


def store_session(session_obj: Any, user_obj: Any) -> None:
    """Persiste les tokens dans la session Flask."""
    session[SESSION_KEY_ACCESS] = session_obj.access_token
    session[SESSION_KEY_REFRESH] = session_obj.refresh_token
    session[SESSION_KEY_USER_ID] = str(user_obj.id)
    session[SESSION_KEY_EMAIL] = user_obj.email or ""
    session.permanent = True


def clear_session() -> None:
    for k in (
        SESSION_KEY_ACCESS,
        SESSION_KEY_REFRESH,
        SESSION_KEY_USER_ID,
        SESSION_KEY_EMAIL,
        # legacy
        "is_admin",
    ):
        session.pop(k, None)


def logout_user() -> None:
    """Détruit la session côté Supabase + côté Flask."""
    token = session.get(SESSION_KEY_ACCESS)
    if token:
        try:
            sb = user_client(token)
            sb.auth.sign_out()
        except Exception:
            # Best-effort : on nettoie quand même la session Flask.
            pass
    clear_session()


# =========================================================================
# Profile & admin lookup
# =========================================================================

def _fetch_profile(user_id: str) -> Optional[dict[str, Any]]:
    """Lit le profil via service_role (bypass RLS)."""
    try:
        sb = service_client()
        res = sb.table("profiles").select("*").eq("id", user_id).limit(1).execute()
    except Exception:
        return None
    rows = getattr(res, "data", None) or []
    return rows[0] if rows else None


def get_current_user() -> Optional[dict[str, Any]]:
    """Retourne {id, email, full_name, is_admin, is_suspended} ou None.

    Si le profil est suspendu, on détruit la session courante et on retourne
    None : l'utilisateur sera traité comme non connecté par les décorateurs
    `require_login` / `require_admin`.
    """
    user_id = session.get(SESSION_KEY_USER_ID)
    if not user_id:
        return None
    profile = _fetch_profile(user_id)
    if not profile:
        return None
    if profile.get("is_suspended"):
        clear_session()
        return None
    return {
        "id": profile["id"],
        "email": profile.get("email") or session.get(SESSION_KEY_EMAIL, ""),
        "full_name": profile.get("full_name") or "",
        "is_admin": bool(profile.get("is_admin", False)),
        "is_suspended": bool(profile.get("is_suspended", False)),
    }


def is_admin() -> bool:
    user = get_current_user()
    return bool(user and user.get("is_admin"))


# =========================================================================
# Decorators
# =========================================================================

def _wants_json() -> bool:
    """Détecte les requêtes AJAX/JSON pour lesquelles un redirect HTML
    casserait le `fetch().json()` côté client."""
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    accept = (request.headers.get("Accept") or "").lower()
    if "application/json" in accept and "text/html" not in accept:
        return True
    if (request.headers.get("Content-Type") or "").startswith("application/json"):
        return True
    return False


def _unauthenticated_response():
    if _wants_json():
        return jsonify({"error": "Connexion requise."}), 401
    return redirect(url_for("login", next=request.full_path))


def _forbidden_response():
    if _wants_json():
        return jsonify({"error": "Accès réservé à l'administrateur."}), 403
    abort(403, description="Accès réservé à l'administrateur.")


def require_login(view: Callable) -> Callable:
    @wraps(view)
    def wrapper(*args, **kwargs):
        # get_current_user() vide la session si le profil est suspendu, et
        # retourne None si l'utilisateur n'est plus authentifié.
        if not get_current_user():
            return _unauthenticated_response()
        return view(*args, **kwargs)

    return wrapper


def require_admin(view: Callable) -> Callable:
    @wraps(view)
    def wrapper(*args, **kwargs):
        # get_current_user() détruit la session si l'utilisateur a été
        # suspendu, ce qui doit donner un 401 (à reconnecter), pas un 403.
        user = get_current_user()
        if not user:
            return _unauthenticated_response()
        if not user.get("is_admin"):
            return _forbidden_response()
        return view(*args, **kwargs)

    return wrapper


# =========================================================================
# Bootstrap admin (au démarrage du serveur)
# =========================================================================

def bootstrap_admin_from_env() -> None:
    """Si `ADMIN_BOOTSTRAP_EMAIL` est défini, marque le profil correspondant
    comme admin. Idempotent : safe à appeler à chaque démarrage."""
    email = (os.environ.get("ADMIN_BOOTSTRAP_EMAIL") or "").strip().lower()
    if not email or not supabase_configured():
        return
    try:
        sb = service_client()
        # On cherche d'abord dans profiles (plus simple que de pager auth.users).
        res = sb.table("profiles").select("id, is_admin").eq("email", email).limit(1).execute()
        rows = getattr(res, "data", None) or []
        if not rows:
            # Le user ne s'est pas encore inscrit. On le note pour la prochaine fois.
            return
        if rows[0].get("is_admin"):
            return
        sb.table("profiles").update({"is_admin": True}).eq("id", rows[0]["id"]).execute()
    except Exception:
        # Best-effort : ne pas casser le démarrage si Supabase est down.
        pass
