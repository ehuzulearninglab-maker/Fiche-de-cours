"""
Multi-provider LLM abstraction layer.
Supports: OpenAI, Claude, Gemini, Groq, OpenRouter, Cerebras, GLM
"""
import requests
import json


def _extract_usage(provider_id: str, data: dict) -> tuple[int, int]:
    """Extrait (prompt_tokens, completion_tokens) d'une réponse LLM JSON.

    Renvoie (0, 0) si l'usage n'est pas disponible (parsing échoué) — le
    code appelant peut ignorer l'enregistrement dans ce cas."""
    if not isinstance(data, dict):
        return 0, 0
    try:
        if provider_id == "claude":
            u = data.get("usage") or {}
            return int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0)
        if provider_id == "gemini":
            u = data.get("usageMetadata") or {}
            return int(u.get("promptTokenCount") or 0), int(u.get("candidatesTokenCount") or 0)
        # OpenAI-compat (openai, groq, openrouter, cerebras, glm)
        u = data.get("usage") or {}
        return int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)
    except (TypeError, ValueError):
        return 0, 0


def _record_call_usage(provider_id: str, model: str, data: dict) -> None:
    """Enregistre la consommation de tokens dans usage_events si on a le
    contexte utilisateur (Flask `g.current_user_id`). Best-effort."""
    try:
        from flask import g, has_request_context
        if not has_request_context():
            return
        user_id = getattr(g, "current_user_id", None)
        if not user_id:
            return
        prompt, completion = _extract_usage(provider_id, data)
        if (prompt + completion) <= 0:
            return
        from usage_store import record_usage
        record_usage(user_id, provider_id, model, prompt, completion)
    except Exception:
        return


class LLMProviderError(RuntimeError):
    """Erreur enrichie avec le message renvoyé par le fournisseur upstream."""

    def __init__(self, provider_name: str, status_code: int, body_excerpt: str):
        self.provider_name = provider_name
        self.status_code = status_code
        self.body_excerpt = body_excerpt
        super().__init__(
            f"{provider_name} a renvoyé HTTP {status_code} : {body_excerpt}"
        )


def _extract_error_message(resp: requests.Response) -> str:
    """Extrait le message d'erreur lisible d'une réponse HTTP fournisseur."""
    try:
        data = resp.json()
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                msg = err.get("message") or err.get("type") or err.get("code")
                if msg:
                    return str(msg)
            if isinstance(err, str):
                return err
            if "message" in data:
                return str(data["message"])
        return resp.text[:500]
    except (ValueError, AttributeError):
        return resp.text[:500] if resp.text else f"HTTP {resp.status_code}"


def _check_response(provider, resp: requests.Response) -> None:
    """Lève LLMProviderError avec un message exploitable si la réponse est en erreur.

    Met aussi à jour le cache de santé du fournisseur (provider_health) si
    le dict `provider` contient un `_id`. Réussite et échec sont tous deux
    enregistrés pour suivre l'état courant côté admin."""
    provider_id = provider.get("_id") if isinstance(provider, dict) else None
    if resp.status_code >= 400:
        message = _extract_error_message(resp)
        if provider_id:
            try:
                from provider_health import record_error
                record_error(provider_id, resp.status_code, message)
            except Exception:
                pass
        raise LLMProviderError(
            provider_name=provider.get("name", "fournisseur"),
            status_code=resp.status_code,
            body_excerpt=message,
        )
    if provider_id:
        try:
            from provider_health import record_success
            record_success(provider_id)
        except Exception:
            pass


PROVIDERS = {
    "openai": {
        "_id": "openai",
        "name": "OpenAI (GPT-4o)",
        "base_url": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
    "claude": {
        "_id": "claude",
        "name": "Claude (Anthropic)",
        "base_url": "https://api.anthropic.com/v1/messages",
        "model": "claude-sonnet-4-20250514",
        "auth_header": "x-api-key",
        "auth_prefix": "",
    },
    "gemini": {
        "_id": "gemini",
        "name": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "model": "gemini-2.5-flash",
        "auth_header": None,  # uses query param
        "auth_prefix": "",
    },
    "groq": {
        "_id": "groq",
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
    "openrouter": {
        "_id": "openrouter",
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "model": "anthropic/claude-sonnet-4-20250514",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
    "cerebras": {
        "_id": "cerebras",
        "name": "Cerebras",
        "base_url": "https://api.cerebras.ai/v1/chat/completions",
        "model": "llama-3.3-70b",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
    "glm": {
        "_id": "glm",
        "name": "GLM (Zhipu AI)",
        "base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "model": "glm-4-flash",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
}


def call_llm(provider_id: str, api_key: str, system_prompt: str, user_prompt: str, model_override: str = None) -> str:
    """Call the specified LLM provider and return the generated text."""
    provider = PROVIDERS.get(provider_id)
    if not provider:
        raise ValueError(f"Provider inconnu: {provider_id}")

    model = model_override or provider["model"]

    if provider_id == "claude":
        return _call_claude(provider, api_key, system_prompt, user_prompt, model)
    elif provider_id == "gemini":
        return _call_gemini(provider, api_key, system_prompt, user_prompt, model)
    else:
        return _call_openai_compat(provider, api_key, system_prompt, user_prompt, model)


def call_llm_chat(
    provider_id: str,
    api_key: str,
    system_prompt: str,
    messages: list[dict],
    model_override: str = None,
) -> str:
    """Multi-turn chat. `messages` est une liste de {role, content} alternant
    entre 'user' et 'assistant'. Le system prompt est passé séparément.
    """
    provider = PROVIDERS.get(provider_id)
    if not provider:
        raise ValueError(f"Provider inconnu: {provider_id}")
    model = model_override or provider["model"]

    if provider_id == "claude":
        return _call_claude_chat(provider, api_key, system_prompt, messages, model)
    if provider_id == "gemini":
        return _call_gemini_chat(provider, api_key, system_prompt, messages, model)
    return _call_openai_compat_chat(provider, api_key, system_prompt, messages, model)


def _call_openai_compat_chat(provider, api_key, system_prompt, messages, model):
    headers = {
        "Content-Type": "application/json",
        provider["auth_header"]: f"{provider['auth_prefix']}{api_key}",
    }
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}, *messages],
        "temperature": 0.3,
        "max_tokens": 8000,
    }
    resp = requests.post(provider["base_url"], headers=headers, json=payload, timeout=120)
    _check_response(provider, resp)
    data = resp.json()
    _record_call_usage(provider.get("_id", ""), model, data)
    return data["choices"][0]["message"]["content"]


def _call_claude_chat(provider, api_key, system_prompt, messages, model):
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": model,
        "max_tokens": 8000,
        "temperature": 0.3,
        "system": system_prompt,
        "messages": messages,
    }
    resp = requests.post(provider["base_url"], headers=headers, json=payload, timeout=120)
    _check_response(provider, resp)
    data = resp.json()
    _record_call_usage("claude", model, data)
    return data["content"][0]["text"]


def _call_gemini_chat(provider, api_key, system_prompt, messages, model):
    url = provider["base_url"].format(model=model) + f"?key={api_key}"
    headers = {"Content-Type": "application/json"}
    # Gemini : 'role' doit être 'user' ou 'model'
    contents = []
    for m in messages:
        role = "model" if m.get("role") == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 8000,
        },
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    _check_response(provider, resp)
    data = resp.json()
    _record_call_usage("gemini", model, data)
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_openai_compat(provider, api_key, system_prompt, user_prompt, model):
    """Call OpenAI-compatible APIs (OpenAI, Groq, OpenRouter, Cerebras, GLM)."""
    headers = {
        "Content-Type": "application/json",
        provider["auth_header"]: f"{provider['auth_prefix']}{api_key}",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 8000,
    }
    resp = requests.post(provider["base_url"], headers=headers, json=payload, timeout=120)
    _check_response(provider, resp)
    data = resp.json()
    _record_call_usage(provider.get("_id", ""), model, data)
    return data["choices"][0]["message"]["content"]


def _call_claude(provider, api_key, system_prompt, user_prompt, model):
    """Call Anthropic Claude API."""
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": model,
        "max_tokens": 8000,
        "temperature": 0.3,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_prompt},
        ],
    }
    resp = requests.post(provider["base_url"], headers=headers, json=payload, timeout=120)
    _check_response(provider, resp)
    data = resp.json()
    _record_call_usage("claude", model, data)
    return data["content"][0]["text"]


def _call_gemini(provider, api_key, system_prompt, user_prompt, model):
    """Call Google Gemini API."""
    url = provider["base_url"].format(model=model) + f"?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 8000,
        },
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    _check_response(provider, resp)
    data = resp.json()
    _record_call_usage("gemini", model, data)
    return data["candidates"][0]["content"]["parts"][0]["text"]
