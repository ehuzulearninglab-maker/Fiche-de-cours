"""
Matières et sous-matières du système éducatif béninois (CI au CM2).

Taxonomie alignée avec le Ministère des Enseignements Maternel et Primaire (MEMP).
Permet à l'utilisateur de choisir une matière puis, le cas échéant,
une sous-matière (ex. Français > Conjugaison, Grammaire, Orthographe…).
"""

# Mapping matière -> liste ordonnée de sous-matières.
# Une liste vide signifie que la matière n'a pas de sous-matières.
SOUS_MATIERES: dict[str, list[str]] = {
    "ES": [
        "Morale",
        "Civisme",
        "Histoire",
        "Géographie",
        "Langue et Culture",
    ],
    "EST": [],
    "Mathématiques": [
        "Arithmétique",
        "Géométrie",
        "Mesure",
    ],
    "Français": [
        "Vocabulaire thématique",
        "Orthographe",
        "Conjugaison",
        "Écriture",
        "Graphisme",
        "Communication orale",
        "Expression écrite — imprégnation",
        "Expression écrite — 1er jet",
        "Expression écrite — amélioration",
        "Expression écrite — mise au propre de la production écrite",
        "Expression écrite — compte rendu de la production",
        "Lecture silencieuse",
        "Lecture oralisée",
        "Lecture audition",
    ],
    "EPS": [],
    "Activités artistiques": [
        "EA Chant",
        "EA Conte",
        "EA Poésie",
        "EA Dessin",
        "EA TM (Couture, Découpage, …)",
    ],
}


def get_sous_matieres(matiere: str) -> list[str]:
    """Retourne la liste des sous-matières d'une matière, ou [] si inconnue."""
    return SOUS_MATIERES.get(matiere, [])


def matiere_label(matiere: str, sous_matiere: str = "") -> str:
    """Construit un libellé lisible : 'Français - Conjugaison' ou 'Français'."""
    matiere = (matiere or "").strip()
    sous_matiere = (sous_matiere or "").strip()
    if matiere and sous_matiere:
        return f"{matiere} - {sous_matiere}"
    return matiere
