"""Configuration par métier artisanal.

Un métier = des mots-clés racines (semences envoyées à GenerateKeywordIdeas pour
la découverte, livrable 1) + une liste fermée de mots-clés (envoyée à
GenerateKeywordHistoricalMetrics pour la fiche de closing, livrable 2) + le code
NAF servant à compter les entreprises concurrentes via l'API Sirene de l'INSEE.
"""

from typing import Dict, List, NamedTuple


class Metier(NamedTuple):
    cle: str
    libelle: str
    codes_naf: List[str]     # ex. ["43.91B"] — sert au comptage INSEE
    libelle_naf: str
    racines: List[str]       # semences pour la découverte de mots-clés
    closing: List[str]       # liste fermée pour la fiche artisan


COUVERTURE = Metier(
    cle="couverture",
    libelle="Couverture / toiture",
    # 43.91B = « Travaux de couverture par éléments » (le couvreur).
    # 43.91A = « Travaux de charpente » : beaucoup d'artisans exercent les deux
    # sous une seule immatriculation, on compte donc les deux pour estimer le
    # vivier recrutable — quitte à surestimer légèrement.
    codes_naf=["43.91B", "43.91A"],
    libelle_naf="Travaux de couverture par éléments (+ charpente)",
    racines=[
        "couvreur",
        "couverture toiture",
        "réfection toiture",
        "rénovation toiture",
        "zinguerie",
        "démoussage toiture",
        "réparation toiture",
        "charpente couverture",
    ],
    closing=[
        # Générique métier — le socle de volume
        "couvreur",
        "entreprise de couverture",
        "artisan couvreur",
        "couvreur zingueur",
        # Devis / recherche de professionnel — le cœur du lead
        "devis toiture",
        "devis couvreur",
        "devis réfection toiture",
        "refaire sa toiture",
        "rénovation toiture",
        "réfection toiture",
        "changer sa toiture",
        # Urgence — le lead le plus chaud
        "fuite toiture",
        "réparation toiture",
        "urgence toiture",
        "dépannage toiture",
        "infiltration toiture",
        # Travaux connexes à fort ticket
        "démoussage toiture",
        "nettoyage toiture",
        "isolation toiture",
        "changement gouttière",
        "zinguerie",
        # Prix — intention plus faible mais volume important
        "prix réfection toiture",
        "prix toiture au m2",
    ],
)

MACONNERIE = Metier(
    cle="maconnerie",
    libelle="Maçonnerie",
    codes_naf=["43.99C"],
    libelle_naf="Travaux de maçonnerie générale et gros œuvre de bâtiment",
    racines=["maçon", "maçonnerie", "mur de clôture", "extension maison", "dalle béton"],
    closing=[
        "maçon", "entreprise de maçonnerie", "artisan maçon", "devis maçonnerie",
        "mur de clôture", "extension maison", "dalle béton", "terrasse béton",
        "prix maçonnerie",
    ],
)

METIERS: Dict[str, Metier] = {m.cle: m for m in (COUVERTURE, MACONNERIE)}


def get(cle: str) -> Metier:
    if cle not in METIERS:
        raise KeyError(
            "Métier inconnu : {!r}. Disponibles : {}".format(cle, sorted(METIERS))
        )
    return METIERS[cle]
