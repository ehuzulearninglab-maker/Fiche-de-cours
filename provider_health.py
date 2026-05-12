"""
Suivi de santé des fournisseurs LLM : « OK / presque épuisée / épuisée /
clé invalide / erreur / inconnue ».

Le statut courant de chaque fournisseur est mis à jour automatiquement à
chaque appel API (success ou erreur) via les hooks dans `llm_providers.py`.
L'admin peut aussi forcer un test à la demande via `test_provider()`, qui
émet un ping minimal.

Le cache primaire est en mémoire (process-wide), mais les statuts sont
aussi persistés dans Supabase (table api_keys, clés `_health:<pid>`) pour
qu'ils survivent aux redémarrages du serveur.
"""
from __future__ import annotations

import json
import re
import threading
import time
from typing import Optional


# Patterns d'épuisement (insensible à la casse). On match dans le corps
# d'erreur renvoyé par le fournisseur.
_EXHAUSTION_PATTERNS = re.compile(
    r"quota|insufficient_funds|insufficient[\s_]quota|exhausted|"
    r"out of credits|payment_required|insufficient credits|"
    r"billing|exceeded\s+your|you have used all your|crédits? épuisé",
    re.IGNORECASE,
)


_status_cache: dict[str, dict] = {}
_lock = threading.Lock()
_db_loaded = False


def _health_db_key(provider_id: str) -> str:
    return f"_health:{provider_id}"


def _persist_to_db(provider_id: str, entry: dict) -> None:
    """Best-effort : persiste le statut dans Supabase."""
    try:
        from db import service_client, supabase_configured
        if not supabase_configured():
            return
        sb = service_client()
        serializable = {
            "status": entry.get("status", "unknown"),
            "status_code": entry.get("status_code", 0),
            "message": (entry.get("message") or "")[:300],
            "checked_at": entry.get("checked_at", ""),
        }
        sb.table("api_keys").upsert({
            "provider": _health_db_key(provider_id),
            "api_key": json.dumps(serializable),
        }).execute()
    except Exception:
        pass


def _load_all_from_db() -> None:
    """Charge les statuts persistés depuis Supabase dans le cache mémoire."""
    global _db_loaded
    if _db_loaded:
        return
    _db_loaded = True
    try:
        from db import service_client, supabase_configured
        if not supabase_configured():
            return
        sb = service_client()
        res = sb.table("api_keys").select("provider, api_key").like(
            "provider", "_health:%"
        ).execute()
        rows = getattr(res, "data", None) or []
        with _lock:
            for row in rows:
                pid = row["provider"].replace("_health:", "", 1)
                try:
                    data = json.loads(row["api_key"])
                except (json.JSONDecodeError, TypeError):
                    continue
                if pid not in _status_cache:
                    _status_cache[pid] = {
                        "status": data.get("status", "unknown"),
                        "status_code": data.get("status_code", 0),
                        "message": data.get("message", ""),
                        "checked_at": data.get("checked_at", ""),
                    }
    except Exception:
        pass


def _now_iso() -> str:
    """Datetime ISO utilisé pour `checked_at`."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _classify(status_code: int, message: str) -> str:
    """Retourne 'ok', 'invalid', 'exhausted', 'rate_limit', 'busy' ou 'error'."""
    msg = message or ""
    if status_code == 0:
        return "error"
    if status_code in (401, 403):
        if _EXHAUSTION_PATTERNS.search(msg):
            return "exhausted"
        return "invalid"
    if status_code == 402:
        return "exhausted"
    if status_code == 429:
        if _EXHAUSTION_PATTERNS.search(msg):
            return "exhausted"
        return "rate_limit"
    if status_code >= 500:
        # 500/502/503/504 = fournisseur indisponible/surchargé, transient.
        return "busy"
    if status_code >= 400:
        if _EXHAUSTION_PATTERNS.search(msg):
            return "exhausted"
        return "error"
    return "ok"


def record_error(provider_id: str, status_code: int, message: str) -> None:
    """Enregistre une erreur API pour `provider_id`."""
    if not provider_id:
        return
    cls = _classify(status_code, message or "")
    with _lock:
        prev = _status_cache.get(provider_id) or {}
        prev_status = prev.get("status")
        # Les statuts transient (rate_limit/busy) ne doivent pas écraser un
        # état antérieur plus informatif (ok/exhausted/invalid). On garde
        # l'ancien statut, mais on rafraîchit le timestamp.
        if cls in {"rate_limit", "busy"} and prev_status in {"ok", "exhausted", "invalid", "almost_exhausted"}:
            cls = prev_status
        entry = {
            "status": cls,
            "status_code": status_code,
            "message": (message or "")[:300],
            "checked_at": _now_iso(),
        }
        # Préserve les infos de quota si on les a déjà récupérées.
        if prev.get("quota"):
            entry["quota"] = prev["quota"]
            entry["quota_checked_at"] = prev.get("quota_checked_at", 0)
        _status_cache[provider_id] = entry
    _persist_to_db(provider_id, entry)


def record_success(provider_id: str) -> None:
    """Enregistre un appel API réussi pour `provider_id`.

    Préserve les infos de quota (usage/limit/ratio) si elles ont été
    récemment récupérées via `refresh_quota()`. Si le quota dit
    `almost_exhausted`, on garde ce statut — il prime sur un 'ok'
    d'appel API (la clé marche, mais le solde est bas)."""
    if not provider_id:
        return
    with _lock:
        prev = _status_cache.get(provider_id) or {}
        quota = prev.get("quota")
        entry = {
            "status": "ok",
            "status_code": 200,
            "message": "",
            "checked_at": _now_iso(),
        }
        if quota:
            entry["quota"] = quota
            ratio = quota.get("ratio_remaining")
            # Un appel API qui réussit contredit un ratio <= 0 mis en cache :
            # probable recharge + cache pas encore rafraîchi. On ne laisse
            # pas 'exhausted' primer sur un succès avéré. On plafonne à
            # 'almost_exhausted' (plus prudent, visuellement visible) et on
            # invalide le timestamp pour forcer un refresh au prochain
            # chargement de /admin.
            if isinstance(ratio, (int, float)) and ratio <= 0:
                entry["status"] = "almost_exhausted"
                entry["quota_checked_at"] = 0
            elif isinstance(ratio, (int, float)) and ratio < _quota_threshold():
                entry["status"] = "almost_exhausted"
                entry["quota_checked_at"] = prev.get("quota_checked_at", 0)
            else:
                entry["quota_checked_at"] = prev.get("quota_checked_at", 0)
        _status_cache[provider_id] = entry
    _persist_to_db(provider_id, entry)


def _quota_threshold() -> float:
    from provider_quota import _threshold
    return _threshold()


_QUOTA_CACHE_TTL_S = 60


def refresh_quota(
    provider_id: str,
    api_key: str,
    force: bool = False,
) -> Optional[dict]:
    """Interroge l'endpoint de solde du fournisseur (si supporté) et met à
    jour le cache avec {quota, status} selon le ratio restant.

    Si un quota a été rafraîchi il y a moins de _QUOTA_CACHE_TTL_S, on
    retourne le cache courant sans re-faire l'appel réseau (sauf si
    `force=True`).

    Retourne le dict quota brut (usage/limit/ratio_remaining/...) ou None
    si le fournisseur n'expose rien ou si l'appel a échoué."""
    if not provider_id or not api_key:
        return None
    from provider_quota import fetch_quota_info, supports_quota, quota_status
    if not supports_quota(provider_id):
        return None
    # Throttle : garde la valeur en cache si elle est récente.
    if not force:
        with _lock:
            prev = _status_cache.get(provider_id) or {}
            quota = prev.get("quota")
            last = prev.get("quota_checked_at") or 0
            if quota and (time.time() - last) < _QUOTA_CACHE_TTL_S:
                return dict(quota)
    info = fetch_quota_info(provider_id, api_key)
    if info is None:
        return None
    qs = quota_status(info)
    with _lock:
        prev = _status_cache.get(provider_id) or {}
        prev_status = prev.get("status")
        # Le quota prime toujours pour signaler almost_exhausted / exhausted.
        # Pour 'ok', on ne revient pas sur un 'invalid' / 'error' observé via
        # les appels réels — un solde disponible ne prouve pas que la clé
        # authentifie les generateContent.
        if qs == "exhausted":
            new_status = "exhausted"
        elif qs == "almost_exhausted":
            if prev_status in {"invalid", "error"}:
                new_status = prev_status
            else:
                new_status = "almost_exhausted"
        else:  # qs == 'ok' ou None (ratio inconnu, ex. clé pay-as-you-go
            # sans limit fixée). Ces 2 cas doivent être distingués :
            # - qs == 'ok' : solde disponible confirmé → on bascule en 'ok'
            #   sauf si un ping a déjà vu 'invalid' / 'error' (un solde
            #   disponible ne prouve pas que la clé authentifie).
            # - qs is None : on ne sait rien → on laisse le statut
            #   précédent (pour ne pas masquer un 'exhausted' issu d'un 402).
            if prev_status in {"invalid", "error"}:
                new_status = prev_status
            elif qs == "ok":
                new_status = "ok"
            else:  # qs is None
                new_status = prev_status or "ok"
        entry = {
            "status": new_status,
            "status_code": prev.get("status_code", 200),
            "message": prev.get("message", ""),
            "checked_at": _now_iso(),
            "quota": info,
            "quota_checked_at": time.time(),
        }
        _status_cache[provider_id] = entry
    _persist_to_db(provider_id, entry)
    return info


def get_status(provider_id: str) -> dict:
    """Retourne le statut courant ou un dict 'unknown' si jamais testé."""
    _load_all_from_db()
    with _lock:
        cur = _status_cache.get(provider_id)
        if cur:
            return dict(cur)
    return {"status": "unknown", "status_code": 0, "message": "", "checked_at": "", "quota": None}


def get_all_statuses() -> dict[str, dict]:
    _load_all_from_db()
    with _lock:
        return {pid: dict(info) for pid, info in _status_cache.items()}


def test_provider(provider_id: str, api_key: str, model_override: Optional[str] = None) -> dict:
    """Effectue un test minimal de la clé API. Met à jour le cache et le retourne.

    Pour les fournisseurs qui exposent un endpoint dédié au quota
    (OpenRouter `/api/v1/key`), on pourrait l'exploiter, mais pour la
    simplicité on émet un ping de chat à 1 token.
    """
    # Import tardif pour éviter la circularité.
    from llm_providers import PROVIDERS, LLMProviderError, call_llm

    if provider_id not in PROVIDERS:
        return {"status": "error", "status_code": 0, "message": "Fournisseur inconnu", "checked_at": _now_iso()}
    if not api_key:
        record_error(provider_id, 401, "Clé API non configurée")
        return get_status(provider_id)

    # 1) Ping minimal pour valider l'authentification et la génération.
    try:
        call_llm(provider_id, api_key, "Réponds 'ok'.", "ok", model_override=model_override)
        record_success(provider_id)
    except LLMProviderError as e:
        record_error(provider_id, e.status_code, e.body_excerpt)
    except Exception as e:
        record_error(provider_id, 0, str(e)[:200])

    # 2) Complète avec le solde brut si le fournisseur expose un endpoint
    # de quota (OpenRouter, éventuellement OpenAI). Permet de basculer
    # en 'almost_exhausted' même quand le ping réussit. force=True car le
    # bouton « Tester » doit toujours refléter l'état le plus frais.
    try:
        refresh_quota(provider_id, api_key, force=True)
    except Exception:
        pass

    return get_status(provider_id)


def reset_status(provider_id: str) -> None:
    """À appeler quand l'admin enregistre une nouvelle clé pour un fournisseur,
    pour repartir d'un statut 'unknown' propre."""
    with _lock:
        _status_cache.pop(provider_id, None)
    try:
        from db import service_client, supabase_configured
        if supabase_configured():
            service_client().table("api_keys").delete().eq(
                "provider", _health_db_key(provider_id)
            ).execute()
    except Exception:
        pass
