"""
Lecture du solde/quota restant auprès des fournisseurs LLM qui exposent
un endpoint public basé sur la clé API.

- **OpenRouter** : `GET /api/v1/auth/key` → renvoie `usage`, `limit`,
  `is_free_tier`. Si `limit` est défini, on calcule le ratio restant.
- **OpenAI** : il n'y a plus d'endpoint billing accessible avec une clé
  API seule depuis 2024 (les anciens `/v1/dashboard/billing/*` renvoient
  401 pour les clés de projet). On tente quand même par courtoisie ; en
  cas d'échec on retourne None et on continue avec la détection via
  erreurs 402/429+quota.

Les autres fournisseurs (Gemini, Claude, Groq, Cerebras, GLM) n'exposent
aucune API publique de solde — on ne peut détecter l'épuisement qu'au
moment où un appel renvoie 402 ou 429 avec un message « quota ».
"""
from __future__ import annotations

import os
from typing import Optional

import requests


def _threshold() -> float:
    """Seuil (fraction restante en dessous duquel on signale « presque
    épuisée »). Configurable via QUOTA_ALMOST_THRESHOLD (0.20 par défaut)."""
    try:
        v = float(os.environ.get("QUOTA_ALMOST_THRESHOLD", "0.20"))
    except ValueError:
        v = 0.20
    return max(0.01, min(0.99, v))


def fetch_openrouter_quota(api_key: str) -> Optional[dict]:
    """Retourne {usage, limit, remaining, ratio_remaining, is_free_tier}
    ou None si non disponible."""
    if not api_key:
        return None
    try:
        r = requests.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
    except Exception:
        return None
    if r.status_code != 200:
        return None
    try:
        data = (r.json() or {}).get("data") or {}
    except ValueError:
        return None
    usage = data.get("usage")
    limit = data.get("limit")
    is_free_tier = bool(data.get("is_free_tier"))
    # Les clés "pay-as-you-go" ont limit=None → on ne peut pas calculer
    # un pourcentage restant. On retourne quand même les données brutes.
    if not isinstance(usage, (int, float)):
        usage = None
    if not isinstance(limit, (int, float)):
        limit = None
    if limit and limit > 0 and isinstance(usage, (int, float)):
        remaining = max(0.0, float(limit) - float(usage))
        ratio = remaining / float(limit)
    else:
        remaining = None
        ratio = None
    return {
        "usage": usage,
        "limit": limit,
        "remaining": remaining,
        "ratio_remaining": ratio,
        "is_free_tier": is_free_tier,
        "unit": "USD",
    }


def fetch_openai_quota(api_key: str) -> Optional[dict]:
    """OpenAI n'expose plus de solde public depuis 2024 pour les clés
    standard. On tente l'ancien endpoint par courtoisie ; s'il renvoie
    autre chose que 200 on retourne None."""
    if not api_key:
        return None
    try:
        r = requests.get(
            "https://api.openai.com/dashboard/billing/credit_grants",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
    except Exception:
        return None
    if r.status_code != 200:
        return None
    try:
        data = r.json() or {}
    except ValueError:
        return None
    total_granted = data.get("total_granted")
    total_used = data.get("total_used")
    total_available = data.get("total_available")
    if not isinstance(total_granted, (int, float)) or total_granted <= 0:
        return None
    usage = float(total_used or 0)
    limit = float(total_granted)
    remaining = float(total_available or max(0.0, limit - usage))
    return {
        "usage": usage,
        "limit": limit,
        "remaining": remaining,
        "ratio_remaining": remaining / limit if limit > 0 else None,
        "is_free_tier": False,
        "unit": "USD",
    }


# Table d'orchestration : à étendre si un jour un fournisseur ajoute un
# endpoint de solde (Anthropic, Groq, Gemini, etc.).
_FETCHERS = {
    "openrouter": fetch_openrouter_quota,
    "openai": fetch_openai_quota,
}


def supports_quota(provider_id: str) -> bool:
    return provider_id in _FETCHERS


def fetch_quota_info(provider_id: str, api_key: str) -> Optional[dict]:
    fetcher = _FETCHERS.get(provider_id)
    if not fetcher:
        return None
    try:
        return fetcher(api_key)
    except Exception:
        return None


def quota_status(quota_info: Optional[dict]) -> Optional[str]:
    """À partir d'un dict de quota, renvoie 'ok', 'almost_exhausted',
    'exhausted' ou None si on ne peut rien conclure."""
    if not quota_info:
        return None
    ratio = quota_info.get("ratio_remaining")
    if ratio is None:
        return None
    if ratio <= 0:
        return "exhausted"
    if ratio < _threshold():
        return "almost_exhausted"
    return "ok"
