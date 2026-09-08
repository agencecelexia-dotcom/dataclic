# -*- coding: utf-8 -*-
"""Collecte réelle : relie Google Ads, l'INSEE et le scoring.

C'est la seule couche qui connaît les deux sources à la fois. Les modules
`google_ads`, `insee`, `scoring` et `fiche` restent indépendants les uns des
autres et testables séparément.
"""

import datetime
from typing import Dict, List, NamedTuple, Optional, Tuple

from .fiche import DonneesFiche, LigneMotCle, MoisVolume
from .geo import Departement
from .google_ads import ClientGoogleAds, MetriquesMotCle
from .insee import ClientSirene
from .intention import classer
from .metiers import Metier
from .scoring import EntreeDepartement

# En dessous de ce volume mensuel total, Google plancher-arrondit trop pour que
# le chiffre départemental veuille dire quoi que ce soit : on retombe sur la
# région, et on le signale partout dans les sorties.
SEUIL_REPLI_REGION = 100


class Collecte(NamedTuple):
    departement: Departement
    metier: Metier
    metriques: List[MetriquesMotCle]
    nb_etablissements: Optional[int]
    niveau_geographique: str
    cpc_prevu_eur: Optional[float] = None
    cpc_prevu_hypotheses: str = ""

    @property
    def volume_total(self) -> int:
        return sum(m.volume_mensuel_moyen for m in self.metriques)

    @property
    def volume_transactionnel(self) -> int:
        return int(round(sum(m.volume_mensuel_moyen * classer(m.mot_cle).poids
                             for m in self.metriques)))

    @property
    def enchere_moyenne_eur(self) -> Optional[float]:
        paires = [(m.volume_mensuel_moyen,
                   (m.enchere_haut_page_basse_eur + m.enchere_haut_page_haute_eur) / 2)
                  for m in self.metriques
                  if m.enchere_haut_page_basse_eur and m.enchere_haut_page_haute_eur]
        total = sum(p for p, _ in paires)
        return sum(p * v for p, v in paires) / total if total else None

    @property
    def saisonnalite(self) -> List[MoisVolume]:
        """Somme des volumes mensuels de tous les mots-clés, mois par mois."""
        cumul: Dict[Tuple[int, int], int] = {}
        for m in self.metriques:
            for v in m.volumes_mensuels:
                cumul[(v.annee, v.mois)] = cumul.get((v.annee, v.mois), 0) + v.volume
        return [MoisVolume(a, mo, v) for (a, mo), v in sorted(cumul.items())]

    @property
    def concurrence_moyenne(self) -> Optional[int]:
        indices = [m.concurrence_indice for m in self.metriques
                   if m.concurrence_indice is not None]
        return int(round(sum(indices) / len(indices))) if indices else None


def collecter(client_ads: ClientGoogleAds, client_insee: Optional[ClientSirene],
              metier: Metier, departement: Departement,
              avec_prevision: bool = False) -> Collecte:
    """Collecte les données d'un département. Deux appels API, trois avec prévision."""
    metriques = client_ads.metriques_historiques(
        metier.closing, departement.geo_target_resource_name)

    niveau = "departement"
    if sum(m.volume_mensuel_moyen for m in metriques) < SEUIL_REPLI_REGION:
        # Volume départemental trop arrondi pour signifier quoi que ce soit.
        # On ne peut pas remonter à la région sans son geo target : on le signale
        # plutôt que de renvoyer un zéro qui serait lu comme « pas de marché ».
        niveau = "departement_volume_insuffisant"

    nb = None
    if client_insee is not None:
        nb = client_insee.compter(metier.codes_naf, departement.code_insee)

    cpc = None
    hypotheses = ""
    if avec_prevision:
        p = client_ads.prevision(metier.closing[:10],
                                 departement.geo_target_resource_name)
        cpc, hypotheses = p.cpc_moyen_eur, p.hypotheses

    return Collecte(departement, metier, metriques, nb, niveau, cpc, hypotheses)


def vers_fiche(c: Collecte, taux_conversion: float = 0.08,
               afficher_cout_par_lead: bool = True) -> DonneesFiche:
    return DonneesFiche(
        departement=c.departement,
        metier=c.metier,
        mots_cles=[LigneMotCle(m.mot_cle, m.volume_mensuel_moyen,
                               m.enchere_haut_page_basse_eur,
                               m.enchere_haut_page_haute_eur,
                               m.concurrence_indice)
                   for m in c.metriques],
        saisonnalite=c.saisonnalite,
        nb_etablissements=c.nb_etablissements,
        taux_conversion=taux_conversion,
        cpc_prevu_eur=c.cpc_prevu_eur,
        cpc_prevu_hypotheses=c.cpc_prevu_hypotheses,
        niveau_geographique=c.niveau_geographique,
        donnees_fictives=False,
        date_extraction=datetime.date.today(),
        afficher_cout_par_lead=afficher_cout_par_lead,
    )


def vers_entree_scoring(c: Collecte) -> EntreeDepartement:
    """Le CPC retenu est le milieu des fourchettes d'enchère, faute de mieux.

    C'est une enchère recommandée, pas un CPC payé : cela surestime généralement
    le coût réel, donc le classement est prudent plutôt qu'optimiste.
    """
    return EntreeDepartement(
        departement=c.departement,
        volume_transactionnel=c.volume_transactionnel,
        cpc_eur=c.cpc_prevu_eur or c.enchere_moyenne_eur,
        concurrence_indice=c.concurrence_moyenne,
        nb_etablissements=c.nb_etablissements,
        niveau_geographique=c.niveau_geographique,
    )
