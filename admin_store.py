"""
Stockage des ressources internes administrateur.

Persiste sur disque (sous knowledge_base/admin/) :
- Documents internes catégorisés (canevas, fiches, mesures, règles niveau, règles matière)
- Instructions système permanentes (prompt admin)
- Clés API par fournisseur (api_keys.json) — admin only

Pas de base de données — fichiers texte simples, simple à sauvegarder/migrer.
"""
from __future__ import annotations

import json
import os
import re
import stat
from datetime import datetime
from typing import TypedDict

ADMIN_CATEGORIES: dict[str, str] = {
    "canevas": "Canevas officiels",
    "fiches": "Fiches pédagogiques de référence",
    "mesures": "Mesures correctives MEMP",
    "regles_niveau": "Règles d'adaptation par niveau",
    "regles_matiere": "Règles d'adaptation par matière",
}


class AdminDoc(TypedDict):
    name: str
    category: str
    content: str
    uploaded_at: str


class AdminStore:
    """Persistance fichier des documents admin."""

    def __init__(self, root: str):
        self.root = root
        self.docs_dir = os.path.join(root, "admin")
        os.makedirs(self.docs_dir, exist_ok=True)
        for cat in ADMIN_CATEGORIES:
            os.makedirs(os.path.join(self.docs_dir, cat), exist_ok=True)
        self.instructions_path = os.path.join(self.docs_dir, "instructions.txt")
        self.api_keys_path = os.path.join(self.docs_dir, "api_keys.json")
        self.settings_path = os.path.join(self.docs_dir, "settings.json")

    @staticmethod
    def _safe_name(name: str) -> str:
        base = os.path.basename(name)
        base = re.sub(r"[^A-Za-z0-9._-]", "_", base)
        # On retire les points en tête : list_docs() ignore les fichiers cachés.
        base = base.lstrip('.')
        return base[:200] or "doc.txt"

    def list_docs(self, category: str = "") -> list[AdminDoc]:
        out: list[AdminDoc] = []
        cats = [category] if category else list(ADMIN_CATEGORIES.keys())
        # Empêche le directory traversal : ignore toute catégorie inconnue.
        cats = [c for c in cats if c in ADMIN_CATEGORIES]
        for cat in cats:
            cat_dir = os.path.join(self.docs_dir, cat)
            if not os.path.isdir(cat_dir):
                continue
            for fname in sorted(os.listdir(cat_dir)):
                # Ignore les fichiers cachés (.gitkeep, etc.) pour ne pas polluer le contexte LLM.
                if fname.startswith('.'):
                    continue
                fpath = os.path.join(cat_dir, fname)
                if not os.path.isfile(fpath):
                    continue
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                except OSError:
                    continue
                st = os.stat(fpath)
                out.append({
                    "name": fname,
                    "category": cat,
                    "content": content,
                    "uploaded_at": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                })
        return out

    def add_doc(self, category: str, name: str, content: str) -> AdminDoc:
        if category not in ADMIN_CATEGORIES:
            raise ValueError(f"Catégorie inconnue: {category}")
        cat_dir = os.path.join(self.docs_dir, category)
        os.makedirs(cat_dir, exist_ok=True)
        safe = self._safe_name(name)
        # Si le nom finit en .pdf on le ré-écrit en .txt (le contenu stocké est
        # déjà du texte extrait, pas le PDF binaire).
        if safe.lower().endswith(".pdf"):
            safe = safe[:-4] + ".txt"
        fpath = os.path.join(cat_dir, safe)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        st = os.stat(fpath)
        return {
            "name": safe,
            "category": category,
            "content": content,
            "uploaded_at": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        }

    def remove_doc(self, category: str, name: str) -> bool:
        if category not in ADMIN_CATEGORIES:
            return False
        safe = self._safe_name(name)
        fpath = os.path.join(self.docs_dir, category, safe)
        if os.path.isfile(fpath):
            os.remove(fpath)
            return True
        return False

    def get_instructions(self) -> str:
        if os.path.isfile(self.instructions_path):
            with open(self.instructions_path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def set_instructions(self, text: str) -> None:
        with open(self.instructions_path, "w", encoding="utf-8") as f:
            f.write(text or "")

    def build_context_block(self) -> str:
        """Concatène tous les docs admin en bloc texte pour le LLM, par catégorie."""
        out_parts: list[str] = []
        for cat, label in ADMIN_CATEGORIES.items():
            docs = self.list_docs(cat)
            if not docs:
                continue
            out_parts.append(f"=== {label} ===")
            for d in docs:
                out_parts.append(f"-- {d['name']} --\n{d['content']}")
        return "\n\n".join(out_parts)

    def build_context_for_matiere(
        self,
        matiere: str = "",
        sous_matiere: str = "",
        max_chars: int = 20000,
    ) -> str:
        """Construit le contexte admin filtré par matière/sous-matière.

        Priorité : documents dont le nom ou le contenu (~500 premiers chars)
        contiennent la matière ou la sous-matière demandée. Si aucun document
        ne correspond, on retourne le bloc complet (tronqué à *max_chars*).
        """
        if not matiere:
            return self.build_context_block()[:max_chars]

        mat_lower = matiere.lower()
        sm_lower = (sous_matiere or "").lower()
        # Variantes : singulier/pluriel, accents simplifiés
        variants = {mat_lower}
        if mat_lower.endswith("s") and len(mat_lower) > 3:
            variants.add(mat_lower[:-1])
        elif not mat_lower.endswith("s"):
            variants.add(mat_lower + "s")
        if sm_lower:
            variants.add(sm_lower)

        matched_parts: list[str] = []
        other_parts: list[str] = []

        for cat, label in ADMIN_CATEGORIES.items():
            docs = self.list_docs(cat)
            if not docs:
                continue
            for d in docs:
                name_lower = d["name"].lower()
                content_head = d["content"][:500].lower()
                is_match = any(
                    v in name_lower or v in content_head for v in variants
                )
                entry = f"[{label}] -- {d['name']} --\n{d['content']}"
                if is_match:
                    matched_parts.append(entry)
                else:
                    other_parts.append(entry)

        if matched_parts:
            result = "\n\n".join(matched_parts)
            # Si il reste de la place, ajouter les autres docs
            remaining = max_chars - len(result)
            if remaining > 500 and other_parts:
                result += "\n\n" + "\n\n".join(other_parts)
            return result[:max_chars]

        # Aucun doc filtré trouvé → retourner tout
        return self.build_context_block()[:max_chars]

    # ===== API keys (admin-only) =====

    def _load_api_keys(self) -> dict[str, str]:
        if not os.path.isfile(self.api_keys_path):
            return {}
        try:
            with open(self.api_keys_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {str(k): str(v) for k, v in data.items() if v}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_api_keys(self, keys: dict[str, str]) -> None:
        with open(self.api_keys_path, "w", encoding="utf-8") as f:
            json.dump(keys, f, ensure_ascii=False, indent=2)
        # Restreint l'accès au fichier (lecture/écriture propriétaire uniquement).
        try:
            os.chmod(self.api_keys_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    def get_api_key(self, provider_id: str) -> str:
        """Renvoie la clé stockée pour ce fournisseur, ou ''. Usage backend uniquement."""
        return self._load_api_keys().get(provider_id, "")

    def set_api_key(self, provider_id: str, key: str) -> None:
        """Stocke ou efface la clé d'un fournisseur (clé vide = suppression)."""
        keys = self._load_api_keys()
        if key:
            keys[provider_id] = key
        else:
            keys.pop(provider_id, None)
        self._save_api_keys(keys)

    def list_api_key_status(self) -> dict[str, dict]:
        """Renvoie {provider_id: {configured: bool, masked: 'sk-…1234'}}.
        N'expose JAMAIS la clé en clair côté frontend."""
        keys = self._load_api_keys()
        out: dict[str, dict] = {}
        for pid, key in keys.items():
            masked = (key[:4] + "…" + key[-4:]) if len(key) > 10 else "configurée"
            out[pid] = {"configured": True, "masked": masked}
        return out

    # ===== Settings (admin-only, exposé en lecture aux non-admins) =====

    def _load_settings(self) -> dict:
        if not os.path.isfile(self.settings_path):
            return {}
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_settings(self, data: dict) -> None:
        with open(self.settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_default_provider(self) -> str:
        return self._load_settings().get("default_provider", "")

    def set_default_provider(self, provider_id: str) -> None:
        data = self._load_settings()
        if provider_id:
            data["default_provider"] = provider_id
        else:
            data.pop("default_provider", None)
        self._save_settings(data)

    def get_default_model(self) -> str:
        return self._load_settings().get("default_model", "")

    def set_default_model(self, model: str) -> None:
        data = self._load_settings()
        if model:
            data["default_model"] = model
        else:
            data.pop("default_model", None)
        self._save_settings(data)
