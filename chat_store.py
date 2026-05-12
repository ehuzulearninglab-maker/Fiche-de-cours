"""Store CRUD pour les conversations et messages.

Sécurité : les opérations passent par le service_role (bypass RLS) mais
chaque fonction force le filtre par `user_id` afin que jamais une session
Flask ne puisse lire/écrire dans la conversation d'un autre utilisateur.
"""
from __future__ import annotations

from typing import Any, Optional

from db import service_client, supabase_configured


def _to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    return dict(row) if not isinstance(row, dict) else row


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

def list_conversations(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    if not supabase_configured() or not user_id:
        return []
    sb = service_client()
    res = (
        sb.table("conversations")
        .select("id, assistant_id, title, created_at, updated_at")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .limit(max(1, limit))
        .execute()
    )
    return [_to_dict(r) for r in (getattr(res, "data", None) or [])]


def get_conversation(conversation_id: str, user_id: str) -> Optional[dict[str, Any]]:
    if not supabase_configured() or not conversation_id or not user_id:
        return None
    sb = service_client()
    res = (
        sb.table("conversations")
        .select("*")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    return _to_dict(rows[0]) if rows else None


def create_conversation(
    user_id: str,
    assistant_id: str,
    title: str = "Nouvelle conversation",
) -> dict[str, Any]:
    if not supabase_configured() or not user_id or not assistant_id:
        return {}
    sb = service_client()
    res = (
        sb.table("conversations")
        .insert(
            {
                "user_id": user_id,
                "assistant_id": assistant_id,
                "title": title,
            }
        )
        .execute()
    )
    rows = getattr(res, "data", None) or []
    return _to_dict(rows[0]) if rows else {}


def update_conversation_title(
    conversation_id: str, user_id: str, title: str
) -> dict[str, Any]:
    if not supabase_configured() or not conversation_id or not user_id:
        return {}
    sb = service_client()
    res = (
        sb.table("conversations")
        .update({"title": title})
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    return _to_dict(rows[0]) if rows else {}


def touch_conversation(conversation_id: str, user_id: str) -> None:
    """Met à jour `updated_at` (utilisé après chaque message)."""
    if not supabase_configured() or not conversation_id or not user_id:
        return
    from datetime import datetime, timezone
    sb = service_client()
    sb.table("conversations").update(
        {"updated_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", conversation_id).eq("user_id", user_id).execute()


def delete_conversation(conversation_id: str, user_id: str) -> bool:
    if not supabase_configured() or not conversation_id or not user_id:
        return False
    sb = service_client()
    res = (
        sb.table("conversations")
        .delete()
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .execute()
    )
    return bool(getattr(res, "data", None) or [])


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def list_messages(
    conversation_id: str, user_id: str, limit: int = 200
) -> list[dict[str, Any]]:
    if not supabase_configured() or not conversation_id or not user_id:
        return []
    # Vérifie que la conversation appartient à l'utilisateur
    if not get_conversation(conversation_id, user_id):
        return []
    sb = service_client()
    res = (
        sb.table("messages")
        .select("id, role, content, metadata, created_at")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=False)
        .limit(max(1, limit))
        .execute()
    )
    return [_to_dict(r) for r in (getattr(res, "data", None) or [])]


def add_message(
    conversation_id: str,
    user_id: str,
    role: str,
    content: str,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not supabase_configured() or not conversation_id or not user_id:
        return {}
    if role not in ("user", "assistant", "system"):
        raise ValueError(f"Role invalide: {role!r}")
    # Vérifie que la conversation appartient à l'utilisateur
    if not get_conversation(conversation_id, user_id):
        return {}
    sb = service_client()
    res = (
        sb.table("messages")
        .insert(
            {
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "metadata": metadata or {},
            }
        )
        .execute()
    )
    rows = getattr(res, "data", None) or []
    touch_conversation(conversation_id, user_id)
    return _to_dict(rows[0]) if rows else {}


# ---------------------------------------------------------------------------
# Rétention 14 jours : nettoyage automatique des fiches expirées
# ---------------------------------------------------------------------------

# Marqueurs de fiche dans le contenu d'un message assistant.
_FICHE_START = "===FICHE_DEBUT==="
_FICHE_END = "===FICHE_FIN==="
_EXPIRED_PLACEHOLDER = (
    "[Cette fiche a été supprimée automatiquement (rétention 14 jours)."
    " Demande à l'assistant de la régénérer si besoin.]"
)


def _strip_fiche_block(text: str) -> str:
    """Retire ===FICHE_DEBUT===...===FICHE_FIN=== d'un texte."""
    if not text:
        return text or ""
    i = text.find(_FICHE_START)
    if i < 0:
        return text
    j = text.find(_FICHE_END, i + len(_FICHE_START))
    if j < 0:
        return text
    head = text[:i].rstrip()
    tail = text[j + len(_FICHE_END):].lstrip()
    return ((head + "\n\n" + _EXPIRED_PLACEHOLDER + "\n\n" + tail).strip())


def cleanup_expired_fiches(days: int = 14, generated_folder: str | None = None) -> dict[str, int]:
    """Supprime les fichiers DOCX/PDF/MD et nettoie le contenu des messages
    plus vieux que `days` jours qui contenaient une fiche.

    - Garde le message dans l'historique (rôle/horodatage) mais remplace la
      fiche par un placeholder court.
    - Supprime physiquement les fichiers générés du dossier `generated_folder`.

    Retourne {"messages_cleaned": N, "files_deleted": M}.
    """
    import os
    from datetime import datetime, timedelta, timezone

    counters = {"messages_cleaned": 0, "files_deleted": 0}
    if not supabase_configured():
        return counters

    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, days))).isoformat()
    sb = service_client()

    # On ne sélectionne QUE les candidats à nettoyer :
    #   - rôle assistant + ancienneté > cutoff
    #   - has_fiche=true (flag posé à la création quand un bloc fiche a été
    #     détecté dans la réponse LLM ; cf. app.py)
    #   - PAS encore traité (fiche_expired non posé)
    # Sans ces filtres, le LIMIT 1000 finissait par se remplir de messages
    # déjà nettoyés / sans fiche → nouveaux candidats au-delà du rang 1000
    # jamais atteints.
    res = (
        sb.table("messages")
        .select("id, content, metadata, created_at")
        .lt("created_at", cutoff)
        .eq("role", "assistant")
        .eq("metadata->>has_fiche", "true")
        .is_("metadata->>fiche_expired", "null")
        .limit(1000)
        .execute()
    )
    rows = getattr(res, "data", None) or []

    for row in rows:
        meta = row.get("metadata") or {}
        if not isinstance(meta, dict):
            meta = {}
        content = row.get("content") or ""
        has_files = bool(meta.get("docx_file") or meta.get("pdf_file") or meta.get("md_file"))
        has_fiche_text = (_FICHE_START in content) and (_FICHE_END in content)
        if not (has_files or has_fiche_text):
            continue

        # 1) Met à jour la DB en premier — si on supprimait les fichiers
        # avant et que l'UPDATE échouait, la metadata référencerait des
        # fichiers absents et les boutons de téléchargement renverraient
        # 404. Dans l'ordre actuel, un UPDATE OK suivi d'un échec de
        # suppression laisse au pire des fichiers orphelins (récupérés au
        # passage suivant).
        new_meta = {k: v for k, v in meta.items() if k not in ("docx_file", "pdf_file", "md_file", "base_name")}
        new_meta["fiche_expired"] = True
        new_content = _strip_fiche_block(content) if has_fiche_text else content
        try:
            sb.table("messages").update(
                {"content": new_content, "metadata": new_meta}
            ).eq("id", row["id"]).execute()
            counters["messages_cleaned"] += 1
        except Exception:
            # UPDATE échoué : on ne touche PAS au disque, le job tournera
            # à nouveau dans 24h.
            continue

        # 2) UPDATE OK : on peut maintenant supprimer les fichiers en toute
        # sécurité. Un échec ici laisse simplement des orphelins.
        if generated_folder:
            for key in ("docx_file", "pdf_file", "md_file"):
                fn = meta.get(key)
                if fn:
                    try:
                        path = os.path.join(generated_folder, os.path.basename(fn))
                        if os.path.exists(path):
                            os.remove(path)
                            counters["files_deleted"] += 1
                    except OSError:
                        pass

    return counters
