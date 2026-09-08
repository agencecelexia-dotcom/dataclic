# -*- coding: utf-8 -*-
"""Classement des départements par attractivité d'ouverture de campagne.

Principes, hérités des contraintes métier :

1. **Le CPC bas n'est pas une bonne nouvelle.** Il est bas parce que peu
   d'annonceurs enchérissent, et souvent parce qu'il n'y a pas d'argent à faire.
   Le score ne récompense donc jamais un CPC bas en soi : il regarde la *marge
   par lead* (prix de revente − coût par lead), qui intègre le CPC et le taux de
   conversion.
2. **Seul le volume transactionnel compte.** L'entrée est déjà pondérée par
   l'intention (voir `radar.intention`).
3. **Le vrai goulot d'étranglement est le vivier d'artisans recrutables.** Il est
   traité comme un *seuil éliminatoire* puis comme une fonction saturante : en
   dessous du minimum le département est disqualifié quel que soit son volume ;
   au-dessus d'une centaine d'entreprises, en avoir davantage n'apporte plus rien
   puisqu'on ne travaille qu'avec une poignée de partenaires.
4. **Volume et vivier saturent.** Sans cela le classement se réduirait au
   classement démographique des départements, qui n'apprend rien.

Tous les paramètres de jugement sont regroupés dans `Hypotheses` : ce sont des
hypothèses de travail, pas des mesures, et elles doivent être recalées sur les
chiffres réels dès qu'ils existent.
"""

import math
from typing import List, NamedTuple, Optional

from .geo import Departement


class Hypotheses(NamedTuple):
    # -- économie du lead --------------------------------------------------
    taux_conversion: float = 0.08          # conversion de la landing page
    prix_revente_lead_eur: float = 80.0    # ce que l'artisan paie le lead
    marge_minimale_eur: float = 15.0       # marge unitaire plancher
    # Plancher de marge mensuelle *absolue*. Sans lui, un département minuscule à
    # excellente marge unitaire remonte dans le classement alors qu'il ne
    # dégagerait que quelques dizaines d'euros par mois — moins que le coût
    # opérationnel d'ouvrir et de suivre une campagne.
    marge_mensuelle_minimale_eur: float = 300.0

    # -- capacité d'absorption --------------------------------------------
    min_artisans: int = 25                 # seuil éliminatoire : vivier trop mince
    artisans_suffisants: int = 120         # au-delà, le vivier n'est plus un facteur

    # -- volume ------------------------------------------------------------
    part_clics_captee: float = 0.15        # part du volume transactionnel réellement achetée
    volume_saturation: int = 3000          # au-delà, le volume ne départage plus

    # -- pondérations (somme libre, normalisée à l'usage) ------------------
    poids_marge: float = 0.45
    poids_demande: float = 0.30
    poids_absorption: float = 0.25


class EntreeDepartement(NamedTuple):
    departement: Departement
    volume_transactionnel: int
    # Coût par clic à retenir. Si on ne dispose que des enchères haut de page,
    # passer leur milieu ici — en sachant que c'est une enchère recommandée,
    # pas un CPC payé, et que cela surestime généralement le coût réel.
    cpc_eur: Optional[float]
    concurrence_indice: Optional[int] = None   # 0-100
    nb_etablissements: Optional[int] = None    # INSEE, vivier recrutable
    niveau_geographique: str = "departement"   # "region" si repli sur volume trop faible


class ScoreDepartement(NamedTuple):
    entree: EntreeDepartement
    cout_par_lead_eur: Optional[float]
    marge_par_lead_eur: Optional[float]
    leads_potentiels_mois: Optional[float]
    marge_mensuelle_eur: Optional[float]
    note_marge: float
    note_demande: float
    note_absorption: float
    score: float          # 0-100
    verdict: str          # prioritaire | a_tester | marge_insuffisante | vivier_insuffisant | donnees_absentes
    motif: str

    @property
    def departement(self) -> Departement:
        return self.entree.departement


VERDICTS_ELIMINATOIRES = {"marge_insuffisante", "vivier_insuffisant",
                          "marche_trop_petit", "donnees_absentes"}


def _saturant(valeur: float, plafond: float) -> float:
    """Croissance concave bornée à 1 : forte au début, plate ensuite.

    Traduit le fait qu'au-delà d'un certain point, plus de volume (ou plus
    d'artisans) n'améliore plus l'opportunité réelle.
    """
    if plafond <= 0:
        return 0.0
    return min(1.0, math.sqrt(max(valeur, 0.0) / plafond))


def evaluer(entree: EntreeDepartement, h: Hypotheses) -> ScoreDepartement:
    """Note un département. Les seuils éliminatoires priment sur le score."""
    cpl = None
    marge = None
    if entree.cpc_eur and h.taux_conversion > 0:
        cpl = entree.cpc_eur / h.taux_conversion
        marge = h.prix_revente_lead_eur - cpl

    leads = entree.volume_transactionnel * h.part_clics_captee * h.taux_conversion
    marge_mensuelle = leads * marge if marge is not None else None

    note_demande = _saturant(entree.volume_transactionnel, h.volume_saturation)
    note_absorption = (_saturant(entree.nb_etablissements, h.artisans_suffisants)
                       if entree.nb_etablissements is not None else 0.0)
    # La marge est notée par rapport au prix de revente : une marge égale au prix
    # de revente vaudrait 1 (cas théorique d'un coût d'acquisition nul).
    note_marge = (max(0.0, marge) / h.prix_revente_lead_eur) if marge is not None else 0.0

    total_poids = h.poids_marge + h.poids_demande + h.poids_absorption
    score = 100.0 * (
        h.poids_marge * note_marge
        + h.poids_demande * note_demande
        + h.poids_absorption * note_absorption
    ) / total_poids

    verdict, motif = _verdict(entree, h, marge, marge_mensuelle)
    if verdict in VERDICTS_ELIMINATOIRES:
        score = 0.0

    return ScoreDepartement(
        entree=entree, cout_par_lead_eur=cpl, marge_par_lead_eur=marge,
        leads_potentiels_mois=leads, marge_mensuelle_eur=marge_mensuelle,
        note_marge=note_marge, note_demande=note_demande,
        note_absorption=note_absorption, score=score,
        verdict=verdict, motif=motif,
    )


def _verdict(entree: EntreeDepartement, h: Hypotheses,
             marge: Optional[float], marge_mensuelle: Optional[float]):
    if entree.cpc_eur is None or entree.nb_etablissements is None:
        return "donnees_absentes", "CPC ou comptage d'entreprises manquant"
    if entree.nb_etablissements < h.min_artisans:
        return ("vivier_insuffisant",
                "{} entreprises seulement, en dessous du seuil de {} : "
                "personne pour absorber les leads".format(
                    entree.nb_etablissements, h.min_artisans))
    if marge is None or marge < h.marge_minimale_eur:
        return ("marge_insuffisante",
                "marge de {:.0f} € par lead, sous le minimum de {:.0f} €".format(
                    marge or 0.0, h.marge_minimale_eur))
    if marge_mensuelle is None or marge_mensuelle < h.marge_mensuelle_minimale_eur:
        return ("marche_trop_petit",
                "{:.0f} € de marge mensuelle potentielle, sous le minimum de {:.0f} € : "
                "le marché ne paie pas le coût d'ouverture d'une campagne".format(
                    marge_mensuelle or 0.0, h.marge_mensuelle_minimale_eur))
    return "a_tester", ""


def classer(entrees: List[EntreeDepartement],
            hypotheses: Optional[Hypotheses] = None,
            part_prioritaire: float = 0.15) -> List[ScoreDepartement]:
    """Évalue et trie les départements, du plus attractif au moins attractif.

    `part_prioritaire` : fraction des départements retenus (parmi les éligibles)
    promus « prioritaire ». Le reste des éligibles reste « à tester » — la
    validation réelle passe de toute façon par une dépense de quelques centaines
    d'euros sur les deux ou trois premiers.
    """
    h = hypotheses or Hypotheses()
    scores = sorted((evaluer(e, h) for e in entrees), key=lambda s: -s.score)

    eligibles = [s for s in scores if s.verdict not in VERDICTS_ELIMINATOIRES]
    nb_prioritaires = max(1, int(round(len(eligibles) * part_prioritaire))) if eligibles else 0
    promus = {id(s) for s in eligibles[:nb_prioritaires]}

    return [
        s._replace(verdict="prioritaire",
                   motif="{:.0f} € de marge mensuelle potentielle, {} entreprises à démarcher"
                         .format(s.marge_mensuelle_eur or 0,
                                 s.entree.nb_etablissements))
        if id(s) in promus else s
        for s in scores
    ]
