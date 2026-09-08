# -*- coding: utf-8 -*-
"""Données synthétiques, pour faire tourner l'outil sans aucun accès API.

Sert à valider la mécanique et à montrer les sorties. Les valeurs sont
plausibles mais entièrement inventées : elles ne décrivent aucun marché réel.
"""

import datetime
import random
from typing import List

from .fiche import DonneesFiche, LigneMotCle, MoisVolume
from .geo import charger_departements
from .metiers import Metier
from .scoring import EntreeDepartement

# Saisonnalité type de la couverture : creux hivernal, pic de fin d'été.
PROFIL_SAISON = [0.72, 0.70, 0.88, 1.02, 1.08, 1.12, 1.05, 1.14, 1.22, 1.10, 0.88, 0.74]

# Départements à forte densité urbaine : volume et concurrence plus élevés.
URBAINS = {"75": 6.0, "92": 3.2, "93": 3.0, "94": 2.6, "69": 3.4, "13": 3.2,
           "59": 3.4, "33": 2.8, "31": 2.6, "44": 2.4, "34": 2.0, "06": 2.2,
           "77": 2.2, "78": 2.2, "91": 2.0, "95": 2.0, "38": 1.9, "67": 1.8}


def _facteur(code: str, alea: random.Random) -> float:
    return URBAINS.get(code, alea.uniform(0.35, 1.25))


def entrees_scoring(metier: Metier) -> List[EntreeDepartement]:
    entrees = []
    for dep in charger_departements():
        alea = random.Random("demo-" + dep.code_insee)
        f = _facteur(dep.code_insee, alea)
        entrees.append(EntreeDepartement(
            departement=dep,
            volume_transactionnel=int(round(alea.uniform(180, 620) * f / 10) * 10),
            cpc_eur=round(alea.uniform(1.8, 3.6) * (0.75 + 0.42 * f), 2),
            concurrence_indice=int(min(99, alea.uniform(30, 70) + 9 * f)),
            nb_etablissements=int(alea.uniform(30, 120) * f),
        ))
    return entrees


def fiche(code_departement: str, metier: Metier,
          afficher_cout_par_lead: bool = True) -> DonneesFiche:
    alea = random.Random(code_departement + metier.cle)
    deps = {d.code_insee: d for d in charger_departements()}
    if code_departement not in deps:
        raise KeyError("Département inconnu : {}".format(code_departement))

    lignes = []
    for i, mot_cle in enumerate(metier.closing):
        volume = max(10, int(round(alea.uniform(40, 1400) / (1 + i * 0.16) / 10) * 10))
        basse = round(alea.uniform(0.9, 3.4), 2)
        lignes.append(LigneMotCle(mot_cle, volume, basse,
                                  round(basse * alea.uniform(2.1, 3.6), 2),
                                  int(alea.uniform(35, 98))))

    total = sum(l.volume_mensuel_moyen for l in lignes)
    aujourdhui = datetime.date.today()
    saison = []
    for decalage in range(12, 0, -1):
        mois = (aujourdhui.month - decalage) % 12 or 12
        annee = aujourdhui.year - (1 if aujourdhui.month - decalage <= 0 else 0)
        saison.append(MoisVolume(annee, mois, int(total * PROFIL_SAISON[mois - 1])))

    return DonneesFiche(
        departement=deps[code_departement], metier=metier, mots_cles=lignes,
        saisonnalite=saison, nb_etablissements=int(alea.uniform(90, 900)),
        taux_conversion=0.08, cpc_prevu_eur=round(alea.uniform(2.2, 6.4), 2),
        cpc_prevu_hypotheses="enchère max 8 € en CPC manuel, réseau Search",
        donnees_fictives=True, afficher_cout_par_lead=afficher_cout_par_lead,
    )
