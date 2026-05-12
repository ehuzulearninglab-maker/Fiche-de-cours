"""
Stockage des clés API LLM dans Supabase (table `public.api_keys`).

Remplace l'ancien fichier `knowledge_base/admin/api_keys.json`. Ce module
expose la même API que `AdminStore.{get,set,list}_api_key*` pour ne pas
disperser les modifications dans `app.py`.

Si Supabase n'est pas configuré (variables d'env absentes), les méthodes
basculent automatiquement sur le store fichier (`AdminStore`) — utile en
développement local sans Supabase.
"""
from __future__ import annotations

from typing import Optional

from db import service_client, supabase_configured


def _mask(key: str) -> str:
    if len(key) <= 10:
        return "configurée"
    return f"{key[:4]}…{key[-4:]}"


def _settings_key(name: str) -> str:
    """Convention : on stocke des "réglages globaux" dans la même table en
    utilisant un provider sentinel `_setting:<name>`. Évite de créer une
    table dédiée pour 2 valeurs."""
    return f"_setting:{name}"


class SupabaseKeyStore:
    """Implémentation Supabase de la gestion des clés API LLM."""

    def __init__(self, fallback=None):
        # `fallback` est l'ancien AdminStore. Si Supabase est absent, on s'y rabat.
        self.fallback = fallback

    def _use_db(self) -> bool:
        return supabase_configured()

    # ---------- API keys ----------
    def get_api_key(self, provider_id: str) -> str:
        if not self._use_db():
            return self.fallback.get_api_key(provider_id) if self.fallback else ""
        try:
            sb = service_client()
            res = (
                sb.table("api_keys")
                .select("api_key")
                .eq("provider", provider_id)
                .limit(1)
                .execute()
            )
            rows = getattr(res, "data", None) or []
            return rows[0]["api_key"] if rows else ""
        except Exception:
            return ""

    def set_api_key(self, provider_id: str, key: str, updated_by: Optional[str] = None) -> None:
        if not self._use_db():
            if self.fallback:
                self.fallback.set_api_key(provider_id, key)
            return
        sb = service_client()
        if not key:
            sb.table("api_keys").delete().eq("provider", provider_id).execute()
            return
        payload = {"provider": provider_id, "api_key": key}
        if updated_by:
            payload["updated_by"] = updated_by
        sb.table("api_keys").upsert(payload).execute()

    def list_api_key_status(self) -> dict[str, dict]:
        if not self._use_db():
            return self.fallback.list_api_key_status() if self.fallback else {}
        try:
            sb = service_client()
            res = sb.table("api_keys").select("provider, api_key").execute()
            rows = getattr(res, "data", None) or []
        except Exception:
            return {}
        out: dict[str, dict] = {}
        for row in rows:
            pid = row["provider"]
            if pid.startswith("_setting:") or pid.startswith("_health:"):
                continue
            out[pid] = {"configured": True, "masked": _mask(row.get("api_key") or "")}
        return out

    # ---------- Settings (default_provider / default_model) ----------
    def _get_setting(self, name: str) -> str:
        if not self._use_db():
            if self.fallback and name == "default_provider":
                return self.fallback.get_default_provider()
            if self.fallback and name == "default_model":
                return self.fallback.get_default_model()
            return ""
        try:
            sb = service_client()
            res = (
                sb.table("api_keys")
                .select("api_key")
                .eq("provider", _settings_key(name))
                .limit(1)
                .execute()
            )
            rows = getattr(res, "data", None) or []
            return rows[0]["api_key"] if rows else ""
        except Exception:
            return ""

    def _set_setting(self, name: str, value: str) -> None:
        if not self._use_db():
            if self.fallback and name == "default_provider":
                self.fallback.set_default_provider(value)
            elif self.fallback and name == "default_model":
                self.fallback.set_default_model(value)
            return
        sb = service_client()
        key = _settings_key(name)
        if not value:
            sb.table("api_keys").delete().eq("provider", key).execute()
            return
        sb.table("api_keys").upsert({"provider": key, "api_key": value}).execute()

    def get_default_provider(self) -> str:
        return self._get_setting("default_provider")

    def set_default_provider(self, value: str) -> None:
        self._set_setting("default_provider", value)

    def get_default_model(self) -> str:
        return self._get_setting("default_model")

    def set_default_model(self, value: str) -> None:
        self._set_setting("default_model", value)
