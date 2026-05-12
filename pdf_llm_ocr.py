"""
Fallback : utiliser un LLM avec capacités PDF/vision pour extraire le texte
d'un PDF que PyMuPDF ne sait pas lire (PDFs scannés, images-only…).

Pour l'instant on supporte :
- Gemini  (envoi inline du PDF en base64)
- Claude  (Anthropic, document type=base64)

Pour OpenAI gpt-4o on devra convertir le PDF en images (à faire si on
bascule dessus).

Stratégie pour les gros PDFs :
- Si le PDF tient sous le seuil inline (~18 Mo), on l'envoie en un seul
  appel.
- Sinon, on le découpe en morceaux de N pages avec PyMuPDF et on
  envoie chaque morceau séparément, puis on concatène les transcriptions.
  Cela évite la limite Gemini ~20 Mo / Claude ~32 Mo en inline.
"""
from __future__ import annotations

import base64
import os
import tempfile
import time

import fitz  # PyMuPDF — déjà utilisé ailleurs dans le projet
import requests

from llm_providers import PROVIDERS, LLMProviderError, _check_response


# Retries pour les erreurs transitoires des fournisseurs LLM (Gemini "high
# demand" 503, OpenAI/Anthropic 429, 500, 502, 504). On essaie plusieurs
# fois avec un backoff exponentiel pour qu'un pic de charge côté Google
# ne fasse pas sauter tout l'upload.
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
RETRY_BACKOFFS_SECONDS = (2, 5, 15, 30)  # 4 retries → 5 tentatives au total


# Prompt minimaliste : on demande la transcription brute, pas d'analyse.
TRANSCRIPTION_PROMPT = (
    "Transcris fidèlement TOUT le texte de ce document, page par page.\n"
    "- Préserve la structure (titres, sections, listes, tableaux).\n"
    "- N'ajoute aucun commentaire, aucune explication, aucune introduction.\n"
    "- Restitue uniquement le contenu textuel du document, en français.\n"
    "- Si une page contient un tableau, formate-le de façon lisible "
    "(une ligne par enregistrement, colonnes séparées par des « | »).\n"
    "- Conserve les sauts de page sous forme de marqueur "
    "« --- Page N --- » avant chaque nouvelle page."
)


# Seuil au-delà duquel on découpe en morceaux. Gemini accepte ~20 Mo en
# inline, Claude ~32 Mo, on prend une marge confortable.
INLINE_BYTES_THRESHOLD = 18 * 1024 * 1024
# Nombre de pages par morceau quand on découpe. Avec ~0.6 Mo/page sur les
# scans typiques, 12 pages ≈ 7-8 Mo, donc largement sous la limite inline.
DEFAULT_PAGES_PER_CHUNK = 12


class UnsupportedProviderForOCR(RuntimeError):
    """Levé quand le fournisseur configuré ne sait pas lire un PDF."""


def _read_pdf_bytes(pdf_path: str) -> bytes:
    with open(pdf_path, "rb") as f:
        return f.read()


def supports_pdf_ocr(provider_id: str) -> bool:
    """Le fournisseur sait-il lire un PDF directement ?"""
    return provider_id in {"gemini", "claude"}


def _split_pdf_into_chunks(pdf_path: str, pages_per_chunk: int) -> list[tuple[str, int, int]]:
    """Découpe le PDF en morceaux de `pages_per_chunk` pages.

    Retourne une liste de tuples (chunk_path, first_page_index_1based,
    last_page_index_1based). Les fichiers temporaires sont à nettoyer
    par l'appelant.
    """
    src = fitz.open(pdf_path)
    total = src.page_count
    chunks: list[tuple[str, int, int]] = []
    try:
        for start in range(0, total, pages_per_chunk):
            end = min(start + pages_per_chunk - 1, total - 1)
            dst = fitz.open()
            dst.insert_pdf(src, from_page=start, to_page=end)
            tmp = tempfile.NamedTemporaryFile(
                prefix=f"pdf_chunk_{start + 1:04d}_{end + 1:04d}_",
                suffix=".pdf",
                delete=False,
            )
            tmp.close()
            try:
                dst.save(tmp.name)
            except Exception:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass
                raise
            finally:
                dst.close()
            chunks.append((tmp.name, start + 1, end + 1))
    except Exception:
        for chunk_path, _, _ in chunks:
            try:
                os.unlink(chunk_path)
            except OSError:
                pass
        raise
    finally:
        src.close()
    return chunks


def extract_text_via_llm(
    pdf_path: str,
    provider_id: str,
    api_key: str,
    model_override: str | None = None,
    timeout_s: int = 300,
    pages_per_chunk: int = DEFAULT_PAGES_PER_CHUNK,
) -> str:
    """Demande au LLM de transcrire le PDF. Lève si le fournisseur n'est pas
    capable ou si l'API renvoie une erreur. Découpe automatiquement les gros
    PDFs en morceaux de pages."""
    if not supports_pdf_ocr(provider_id):
        raise UnsupportedProviderForOCR(
            f"Le fournisseur {provider_id!r} ne supporte pas la lecture "
            f"directe de PDF (essayez Gemini ou Claude)."
        )
    if not api_key:
        raise RuntimeError("Clé API manquante pour la lecture IA du PDF.")

    provider = PROVIDERS[provider_id]
    model = model_override or provider["model"]
    file_size = os.path.getsize(pdf_path)

    # Cas simple : le PDF tient en inline, un seul appel API.
    if file_size <= INLINE_BYTES_THRESHOLD:
        return _transcribe_with_retries(
            provider_id, provider, api_key, model, pdf_path, timeout_s
        )

    # Découpage : on émet un appel API par morceau, on concatène.
    chunks = _split_pdf_into_chunks(pdf_path, pages_per_chunk)
    parts: list[str] = []
    try:
        for chunk_path, first_page, last_page in chunks:
            text = _transcribe_with_retries(
                provider_id, provider, api_key, model, chunk_path, timeout_s
            )
            header = f"\n=== Pages {first_page}–{last_page} ===\n"
            parts.append(header + (text or "").strip())
    finally:
        for chunk_path, _, _ in chunks:
            try:
                os.unlink(chunk_path)
            except OSError:
                pass
    return "\n".join(parts).strip()


def _transcribe_with_retries(
    provider_id: str,
    provider: dict,
    api_key: str,
    model: str,
    pdf_path: str,
    timeout_s: int,
) -> str:
    """Appelle _transcribe_single avec retries sur erreurs transitoires
    (429/500/502/503/504). Relève la dernière exception si toutes les
    tentatives échouent."""
    last_err: Exception | None = None
    attempts = len(RETRY_BACKOFFS_SECONDS) + 1
    for attempt in range(attempts):
        try:
            return _transcribe_single(
                provider_id, provider, api_key, model, pdf_path, timeout_s
            )
        except LLMProviderError as e:
            last_err = e
            if e.status_code not in RETRY_STATUS_CODES or attempt >= attempts - 1:
                raise
        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = e
            if attempt >= attempts - 1:
                raise
        wait_s = RETRY_BACKOFFS_SECONDS[attempt]
        time.sleep(wait_s)
    # Inatteignable normalement : la boucle ci-dessus retourne ou re-lève.
    if last_err:
        raise last_err
    raise RuntimeError("Échec inattendu de _transcribe_with_retries")


def _transcribe_single(
    provider_id: str,
    provider: dict,
    api_key: str,
    model: str,
    pdf_path: str,
    timeout_s: int,
) -> str:
    """Un seul appel LLM pour un PDF (≤ seuil inline)."""
    pdf_bytes = _read_pdf_bytes(pdf_path)
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
    if provider_id == "gemini":
        return _gemini_transcribe(provider, api_key, model, pdf_b64, timeout_s)
    if provider_id == "claude":
        return _claude_transcribe(provider, api_key, model, pdf_b64, timeout_s)
    raise UnsupportedProviderForOCR(provider_id)


def _gemini_transcribe(provider, api_key, model, pdf_b64, timeout_s):
    url = provider["base_url"].format(model=model) + f"?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": TRANSCRIPTION_PROMPT},
                    {
                        "inline_data": {
                            "mime_type": "application/pdf",
                            "data": pdf_b64,
                        }
                    },
                ],
            }
        ],
        "generationConfig": {
            # Faible température = transcription fidèle.
            "temperature": 0.0,
            # Très large pour ne pas tronquer un long morceau.
            "maxOutputTokens": 32768,
        },
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
    _check_response(provider, resp)
    data = resp.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "\n".join(p.get("text", "") for p in parts if "text" in p).strip()
    except (KeyError, IndexError) as e:
        raise LLMProviderError(
            provider_name=provider["name"],
            status_code=200,
            body_excerpt=f"Réponse Gemini inattendue : {e}",
        )


def _claude_transcribe(provider, api_key, model, pdf_b64, timeout_s):
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": model,
        "max_tokens": 16000,
        "temperature": 0.0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {"type": "text", "text": TRANSCRIPTION_PROMPT},
                ],
            }
        ],
    }
    resp = requests.post(provider["base_url"], headers=headers, json=payload, timeout=timeout_s)
    _check_response(provider, resp)
    data = resp.json()
    content_blocks = data.get("content") or []
    if not isinstance(content_blocks, list) or not content_blocks:
        raise LLMProviderError(
            provider_name=provider["name"],
            status_code=200,
            body_excerpt="Réponse Claude inattendue : pas de blocs 'content'.",
        )
    return "".join(
        block.get("text", "")
        for block in content_blocks
        if block.get("type") == "text"
    ).strip()
