"""
Suivi de la consommation de tokens LLM par utilisateur.

Le module expose deux fonctions :
- `record_usage(user_id, provider_id, model, prompt_tokens, completion_tokens)`
  → insère une ligne dans `public.usage_events`. Best-effort : toute
    exception est avalée pour ne jamais casser une génération de fiche.
- `get_usage_totals_by_user()`
  → retourne {user_id: {prompt, completion, total, total_30d}} pour
    afficher la consommation par utilisateur dans l'admin.

Pour l'instant on stocke un événement par appel LLM réussi. Pas de
batchage ni de cache : la table est petite (1 ligne par requête) et
l'admin lit la somme à la volée.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional


def record_usage(
    user_id: Optional[str],
    provider_id: str,
    model: Optional[str],
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    """Best-effort : insère une ligne usage_events. N'échoue jamais."""
    try:
        if not user_id:
            return  # Appel sans contexte utilisateur (admin ping, OCR sans user) → ignore
        prompt = max(0, int(prompt_tokens or 0))
        completion = max(0, int(completion_tokens or 0))
        total = prompt + completion
        if total == 0:
            return  # Rien à enregistrer (parsing usage a échoué)
        from db import service_client
        sb = service_client()
        sb.table("usage_events").insert({
            "user_id": str(user_id),
            "provider_id": provider_id or "",
            "model": model or "",
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
        }).execute()
    except Exception:
        return


def reset_usage(user_id: str) -> bool:
    """Supprime tous les événements de consommation d'un utilisateur.
    Retourne True si l'opération a réussi."""
    try:
        from db import service_client
        sb = service_client()
        sb.table("usage_events").delete().eq("user_id", str(user_id)).execute()
        return True
    except Exception:
        return False


def get_usage_totals_by_user() -> dict:
    """Retourne {user_id: {prompt, completion, total, total_30d, last_used}}.
    
    Best-effort : si la table n'existe pas (migration pas appliquée) ou si
    Supabase est down, retourne un dict vide pour ne pas casser l'admin.
    """
    try:
        from db import service_client
        sb = service_client()
        # Tout l'historique
        res = (
            sb.table("usage_events")
            .select("user_id, prompt_tokens, completion_tokens, total_tokens, created_at")
            .execute()
        )
        rows = getattr(res, "data", None) or []
    except Exception:
        return {}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    out: dict = {}
    for r in rows:
        uid = str(r.get("user_id") or "")
        if not uid:
            continue
        agg = out.setdefault(uid, {
            "prompt": 0,
            "completion": 0,
            "total": 0,
            "total_30d": 0,
            "calls": 0,
            "last_used": "",
        })
        p = int(r.get("prompt_tokens") or 0)
        c = int(r.get("completion_tokens") or 0)
        t = int(r.get("total_tokens") or (p + c))
        agg["prompt"] += p
        agg["completion"] += c
        agg["total"] += t
        agg["calls"] += 1
        created = str(r.get("created_at") or "")
        if created and created > (agg["last_used"] or ""):
            agg["last_used"] = created
        if created and created >= cutoff:
            agg["total_30d"] += t
    return out
