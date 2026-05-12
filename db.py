"""
Supabase client wrappers for Fiche-de-cour.

Two clients are exposed:
- `service_client()`: uses the service_role key. Bypasses RLS. Use for
  server-side admin operations (managing api_keys, listing all profiles,
  inserting messages on behalf of users, etc.).
- `user_client(access_token)`: uses the anon key + the user's JWT access
  token, so RLS applies. Use when you want to enforce per-user access.

Connection details are read from environment:
- SUPABASE_URL
- SUPABASE_SERVICE_ROLE_KEY  (server-only secret)
- SUPABASE_ANON_KEY          (public)
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from supabase import Client, create_client


def _env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise RuntimeError(
            f"Variable d'environnement {name} manquante. "
            f"Configure-la dans Render/Fly Secrets ou ton .env local."
        )
    return val


@lru_cache(maxsize=1)
def service_client() -> Client:
    """Client Supabase service_role. Bypasses RLS — admin only."""
    return create_client(_env("SUPABASE_URL"), _env("SUPABASE_SERVICE_ROLE_KEY"))


def user_client(access_token: Optional[str] = None) -> Client:
    """Client Supabase anonyme. Si `access_token` fourni, le JWT est attaché
    à toutes les requêtes (RLS s'applique côté Postgres)."""
    client = create_client(_env("SUPABASE_URL"), _env("SUPABASE_ANON_KEY"))
    if access_token:
        # PostgREST + Realtime + Storage : tous lisent ce header.
        client.postgrest.auth(access_token)
    return client


def supabase_configured() -> bool:
    """Renvoie True si toutes les variables Supabase sont définies."""
    for name in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"):
        if not os.environ.get(name, "").strip():
            return False
    return True
