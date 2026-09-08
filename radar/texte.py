"""Normalisation de texte partagée (accents, casse, ponctuation)."""

import re
import unicodedata


def normalise(texte: str) -> str:
    """Rabat une chaîne sur une forme comparable : sans accent, minuscule, mots séparés par un espace."""
    sans_accent = "".join(
        c for c in unicodedata.normalize("NFD", texte)
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", " ", sans_accent.lower()).strip()
