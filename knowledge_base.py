"""
Knowledge base search module.
Loads pre-extracted PDF content and finds relevant fiches.
"""
import json
import os
import re


class KnowledgeBase:
    def __init__(self, kb_path: str):
        self.kb_path = kb_path
        self.documents = []
        self._load()

    def _load(self):
        if os.path.exists(self.kb_path):
            with open(self.kb_path, "r", encoding="utf-8") as f:
                self.documents = json.load(f)

    @staticmethod
    def _matiere_variants(matiere: str) -> list[str]:
        """Renvoie les variantes lexicales d'une matière (sing/plur, abréviations)."""
        m = (matiere or "").lower().strip()
        if not m:
            return []
        variants = {m}
        # plur ↔ sing : "mathématiques" ↔ "mathématique"
        if m.endswith("s") and len(m) > 3:
            variants.add(m[:-1])
        elif not m.endswith("s"):
            variants.add(m + "s")
        # alias usuels
        if m in {"est", "e.s.t", "e.s.t."}:
            variants.update({"est", "e.s.t", "e.s.t."})
        if m in {"es", "education sociale", "éducation sociale"}:
            variants.update({"es", "education sociale", "éducation sociale"})
        return list(variants)

    def search(self, matiere: str = "", niveau: str = "", sa: str = "", sequence: str = "", type_fiche: str = "", sous_matiere: str = "", limit: int = 3) -> list:
        """Search knowledge base for relevant fiches."""
        results = []
        query_terms: list[str] = []
        matiere_variants = self._matiere_variants(matiere)
        query_terms.extend(matiere_variants)
        # La sous-matière (ex. Histoire, Chant) est souvent le terme le plus
        # discriminant pour retrouver le bon document, alors qu'une matière
        # parente (ES, Activités artistiques) est trop générique.
        if sous_matiere:
            query_terms.append(sous_matiere.lower())
        if niveau:
            query_terms.append(niveau.lower())
        if sa:
            query_terms.append(f"sa{sa}".lower())
            query_terms.append(f"san°{sa}".lower())
            query_terms.append(f"sa n°{sa}".lower())

        for doc in self.documents:
            score = 0
            text_lower = doc["text"].lower()
            fname_lower = doc["filename"].lower()

            for term in query_terms:
                if term in text_lower:
                    score += 2
                if term in fname_lower:
                    score += 3

            # Match matiere keywords (variantes singulier/pluriel + alias)
            if matiere:
                mat_lower = matiere.lower()
                if mat_lower in ["est", "e.s.t", "e.s.t."]:
                    if "est" in fname_lower or "e.s.t" in text_lower:
                        score += 5
                elif any(v in text_lower[:500] for v in matiere_variants):
                    score += 4

            # Match sous-matière (forte affinité)
            if sous_matiere:
                sm_lower = sous_matiere.lower()
                if sm_lower in fname_lower:
                    score += 5
                if sm_lower in text_lower[:500]:
                    score += 3

            # Match niveau
            if niveau and niveau.lower() in text_lower[:200]:
                score += 3

            if score > 0:
                results.append({
                    "filename": doc["filename"],
                    "score": score,
                    "text": doc["text"],
                    "page_count": doc["page_count"],
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def get_all_est_fiches(self) -> str:
        """Get all EST fiches content for context."""
        est_texts = []
        for doc in self.documents:
            if "est" in doc["filename"].lower() or "e.s.t" in doc["text"][:500].lower():
                est_texts.append(f"=== {doc['filename']} ===\n{doc['text'][:5000]}")
        return "\n\n".join(est_texts)

    def get_fiches_by_matiere(self, matiere: str) -> str:
        """Get fiches for a specific subject."""
        texts = []
        mat_lower = matiere.lower()
        for doc in self.documents:
            if mat_lower in doc["filename"].lower() or mat_lower in doc["text"][:500].lower():
                texts.append(f"=== {doc['filename']} ===\n{doc['text'][:5000]}")
        return "\n\n".join(texts) if texts else ""
