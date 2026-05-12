"""Charge les documents pré-extraits de `knowledge_base/fiches_kb.json`
dans la table `assistant_documents` de l'assistant CM2.

Idempotent : skippe les fichiers déjà présents (par nom).

Usage :
    python scripts/seed_cm2_kb.py [--force]

`--force` réinsère même si déjà présent (re-création complète des entrées).
"""
import json
import os
import sys
from pathlib import Path

# Permet d'exécuter le script depuis n'importe où.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db import service_client, supabase_configured  # noqa: E402
from assistants_store import get_assistant_by_classe  # noqa: E402


def main(force: bool = False) -> int:
    if not supabase_configured():
        print("[ERROR] Supabase non configuré (variables d'env manquantes).")
        return 2

    kb_path = ROOT / "knowledge_base" / "fiches_kb.json"
    if not kb_path.exists():
        print(f"[ERROR] Fichier KB introuvable: {kb_path}")
        return 2

    with kb_path.open("r", encoding="utf-8") as f:
        docs = json.load(f)

    cm2 = get_assistant_by_classe("CM2")
    if not cm2:
        print("[ERROR] Assistant CM2 non trouvé. Applique d'abord la migration 003.")
        return 2

    sb = service_client()
    res = (
        sb.table("assistant_documents")
        .select("name")
        .eq("assistant_id", cm2["id"])
        .execute()
    )
    existing = {row["name"] for row in (getattr(res, "data", None) or [])}

    inserted = 0
    skipped = 0
    for d in docs:
        name = d.get("filename") or ""
        if not name:
            continue
        text = d.get("text") or ""
        if not force and name in existing:
            skipped += 1
            continue
        if force and name in existing:
            sb.table("assistant_documents").delete().eq(
                "assistant_id", cm2["id"]
            ).eq("name", name).execute()
        sb.table("assistant_documents").insert(
            {
                "assistant_id": cm2["id"],
                "name": name,
                "content": text,
                "bytes": len(text.encode("utf-8")),
            }
        ).execute()
        inserted += 1
        print(f"  + {name} ({len(text)} chars)")

    print(f"OK — {inserted} doc(s) inséré(s), {skipped} skippé(s) (déjà présent).")
    return 0


if __name__ == "__main__":
    force = "--force" in sys.argv
    sys.exit(main(force=force))
