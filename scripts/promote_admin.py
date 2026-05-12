#!/usr/bin/env python3
"""
Promeut un utilisateur existant au rang d'administrateur.

Usage :
    python scripts/promote_admin.py user@example.com

Pré-requis : variables d'environnement SUPABASE_URL et
SUPABASE_SERVICE_ROLE_KEY définies.
"""
from __future__ import annotations

import argparse
import sys

# Permet d'appeler le script depuis la racine du repo.
sys.path.insert(0, ".")

from db import service_client  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Promeut un utilisateur en admin.")
    parser.add_argument("email", help="Adresse email du compte à promouvoir.")
    parser.add_argument(
        "--demote",
        action="store_true",
        help="Au lieu de promouvoir, retire le statut admin.",
    )
    args = parser.parse_args()

    sb = service_client()
    res = (
        sb.table("profiles")
        .select("id, email, is_admin")
        .eq("email", args.email.strip().lower())
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if not rows:
        print(
            f"Aucun profil trouvé pour {args.email!r}. "
            "L'utilisateur doit d'abord s'inscrire via /signup.",
            file=sys.stderr,
        )
        return 1

    profile = rows[0]
    new_value = not args.demote
    if profile["is_admin"] == new_value:
        verb = "déjà admin" if new_value else "déjà non-admin"
        print(f"{profile['email']} est {verb}, rien à faire.")
        return 0

    sb.table("profiles").update({"is_admin": new_value}).eq("id", profile["id"]).execute()
    action = "promu admin" if new_value else "rétrogradé"
    print(f"{profile['email']} ({profile['id']}) {action}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
