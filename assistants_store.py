"""Store CRUD pour les assistants par classe (table public.assistants)
et leurs documents de KB (table public.assistant_documents).

Les opérations passent par le service_role afin de bypasser RLS, sachant
que toutes les vues qui appellent ces fonctions sont déjà protégées par
les décorateurs @require_admin / @require_login côté Flask.
"""
from __future__ import annotations

from typing import Any, Optional

from db import service_client, supabase_configured


# Ordre canonique des classes du primaire béninois.
CLASSES_ORDER: tuple[str, ...] = ("CI", "CP", "CE1", "CE2", "CM1", "CM2")

# Champs autorisés en update — verrouille les colonnes critiques (id, created_*).
_UPDATABLE_FIELDS: set[str] = {
    "name",
    "description",
    "classe",
    "avatar_url",
    "instructions",
    "provider",
    "model",
    "is_active",
    "is_public",
    "allow_uploads",
}


def _to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    return dict(row)


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------

def list_assistants(only_active: bool = False) -> list[dict[str, Any]]:
    """Retourne tous les assistants triés par classe puis nom.

    `only_active=True` n'expose que les assistants actifs+publics (vue user).
    """
    if not supabase_configured():
        return []
    sb = service_client()
    q = sb.table("assistants").select("*")
    if only_active:
        q = q.eq("is_active", True).eq("is_public", True)
    res = q.execute()
    rows = [_to_dict(r) for r in (getattr(res, "data", None) or [])]

    # Tri par ordre des classes puis nom
    def sort_key(a: dict[str, Any]) -> tuple[int, str]:
        cls = (a.get("classe") or "").upper()
        try:
            idx = CLASSES_ORDER.index(cls)
        except ValueError:
            idx = len(CLASSES_ORDER)
        return (idx, a.get("name") or "")

    rows.sort(key=sort_key)
    return rows


def get_assistant(assistant_id: str) -> Optional[dict[str, Any]]:
    if not supabase_configured() or not assistant_id:
        return None
    sb = service_client()
    res = (
        sb.table("assistants")
        .select("*")
        .eq("id", assistant_id)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    return _to_dict(rows[0]) if rows else None


def get_assistant_by_classe(classe: str) -> Optional[dict[str, Any]]:
    if not supabase_configured() or not classe:
        return None
    sb = service_client()
    res = (
        sb.table("assistants")
        .select("*")
        .eq("classe", classe)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    return _to_dict(rows[0]) if rows else None


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------

def update_assistant(assistant_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Met à jour seulement les champs whitelistés."""
    if not supabase_configured() or not assistant_id:
        return {}
    payload = {k: v for k, v in fields.items() if k in _UPDATABLE_FIELDS}
    if not payload:
        return get_assistant(assistant_id) or {}
    sb = service_client()
    res = (
        sb.table("assistants")
        .update(payload)
        .eq("id", assistant_id)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    return _to_dict(rows[0]) if rows else (get_assistant(assistant_id) or {})


def set_active(assistant_id: str, active: bool) -> dict[str, Any]:
    return update_assistant(assistant_id, {"is_active": bool(active)})


# ---------------------------------------------------------------------------
# Documents par assistant (KB dédiée)
# ---------------------------------------------------------------------------

def list_documents(assistant_id: str) -> list[dict[str, Any]]:
    if not supabase_configured() or not assistant_id:
        return []
    sb = service_client()
    res = (
        sb.table("assistant_documents")
        .select("id, name, bytes, uploaded_at")
        .eq("assistant_id", assistant_id)
        .order("uploaded_at", desc=True)
        .execute()
    )
    return [_to_dict(r) for r in (getattr(res, "data", None) or [])]


def add_document(
    assistant_id: str,
    name: str,
    content: str,
    uploaded_by: Optional[str] = None,
) -> dict[str, Any]:
    if not supabase_configured() or not assistant_id or not name:
        return {}
    sb = service_client()
    payload: dict[str, Any] = {
        "assistant_id": assistant_id,
        "name": name,
        "content": content or "",
        "bytes": len((content or "").encode("utf-8")),
    }
    if uploaded_by:
        payload["uploaded_by"] = uploaded_by
    res = sb.table("assistant_documents").insert(payload).execute()
    rows = getattr(res, "data", None) or []
    return _to_dict(rows[0]) if rows else {}


def remove_document(assistant_id: str, document_id: str) -> bool:
    if not supabase_configured() or not assistant_id or not document_id:
        return False
    sb = service_client()
    res = (
        sb.table("assistant_documents")
        .delete()
        .eq("id", document_id)
        .eq("assistant_id", assistant_id)
        .execute()
    )
    deleted = getattr(res, "data", None) or []
    return bool(deleted)


def get_document_contents(assistant_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """Retourne les `limit` derniers documents (pour injection dans le prompt LLM)."""
    if not supabase_configured() or not assistant_id:
        return []
    sb = service_client()
    res = (
        sb.table("assistant_documents")
        .select("name, content")
        .eq("assistant_id", assistant_id)
        .order("uploaded_at", desc=True)
        .limit(max(1, limit))
        .execute()
    )
    return [_to_dict(r) for r in (getattr(res, "data", None) or [])]
