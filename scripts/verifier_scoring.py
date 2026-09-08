#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vérifie que le scoring respecte les règles métier, sur des cas construits.

Ce ne sont pas des tests de code mais des tests de *jugement* : chaque cas
encode une conviction métier. Si l'un tombe après un réglage des pondérations,
c'est le réglage qu'il faut revoir, pas le test.

    python3 scripts/verifier_scoring.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from radar.geo import charger_departements  # noqa: E402
from radar.scoring import EntreeDepartement, Hypotheses, classer, evaluer  # noqa: E402

DEPS = {d.code_insee: d for d in charger_departements()}
ECHECS = []


def E(code, volume, cpc, artisans):
    return EntreeDepartement(DEPS[code], volume, cpc, 50, artisans)


def verifie(nom, condition, detail=""):
    print(("  OK    " if condition else "  ÉCHEC ") + nom + ("   " + detail if detail else ""))
    if not condition:
        ECHECS.append(nom)


def main() -> int:
    h = Hypotheses()

    print("1. Un CPC bas n'est pas une bonne nouvelle en soi")
    desert = evaluer(E("23", 90, 0.90, 30), h)
    solide = evaluer(E("35", 900, 3.20, 110), h)
    verifie("marché à CPC bas mais sans volume : écarté, pas juste mal classé",
            desert.verdict == "marche_trop_petit" and desert.score < solide.score,
            "{} vs score {:.1f}".format(desert.verdict, solide.score))

    print("\n2. Le coût par lead prime sur le coût par clic")
    riche = Hypotheses(taux_conversion=0.15, prix_revente_lead_eur=200)
    pauvre = Hypotheses(taux_conversion=0.03, prix_revente_lead_eur=200)
    a = evaluer(E("35", 900, 12.0, 110), riche)
    b = evaluer(E("35", 900, 5.0, 110), pauvre)
    verifie("CPC 12 € à 15 % bat CPC 5 € à 3 %",
            a.score > b.score,
            "{:.0f} €/lead vs {:.0f} €/lead".format(a.cout_par_lead_eur, b.cout_par_lead_eur))

    print("\n3. Le vivier d'artisans est éliminatoire")
    v = evaluer(E("75", 5000, 3.0, 8), h)
    verifie("volume énorme mais vivier vide : disqualifié",
            v.verdict == "vivier_insuffisant" and v.score == 0, v.verdict)

    print("\n4. Volume et vivier saturent — pas de classement démographique")
    moyen = evaluer(E("35", 1000, 3.0, 120), h)
    enorme = evaluer(E("35", 8000, 3.0, 900), h)
    gain = (enorme.score - moyen.score) / moyen.score
    verifie("×8 de volume et ×7,5 de vivier n'apportent presque rien",
            gain < 0.25, "+{:.0%} de score".format(gain))

    print("\n5. Marge négative : éliminé quel que soit le volume")
    n = evaluer(E("75", 9000, 9.0, 400), h)
    verifie("CPC 9 € à 8 % = 112 €/lead pour un lead vendu 80 €",
            n.verdict == "marge_insuffisante" and n.score == 0,
            "{:.0f} € de marge unitaire".format(n.marge_par_lead_eur))

    print("\n6. Un marché rentable mais minuscule ne vaut pas une campagne")
    petit = evaluer(E("48", 120, 1.20, 40), h)
    verifie("bonne marge unitaire mais quelques dizaines d'euros par mois",
            petit.verdict == "marche_trop_petit",
            "{:.0f} €/mois".format(petit.marge_mensuelle_eur))

    print("\n7. Les hypothèses doivent réellement peser sur le résultat")
    entrees = [E(c, 900, 3.0, 100) for c in ("35", "44", "31", "59", "69")]
    bas = classer(entrees, Hypotheses(prix_revente_lead_eur=40))
    haut = classer(entrees, Hypotheses(prix_revente_lead_eur=150))
    verifie("un lead revendu 40 € vs 150 € change le verdict",
            bas[0].verdict != haut[0].verdict,
            "{} → {}".format(bas[0].verdict, haut[0].verdict))
    verifie("... et change le score",
            abs(bas[0].score - haut[0].score) > 5,
            "{:.1f} vs {:.1f}".format(bas[0].score, haut[0].score))

    print("\n8. Données incomplètes : écarté explicitement, jamais deviné")
    sans = evaluer(EntreeDepartement(DEPS["35"], 900, None, 50, 100), h)
    verifie("CPC manquant : verdict donnees_absentes",
            sans.verdict == "donnees_absentes" and sans.score == 0, sans.verdict)

    print("\n" + ("Toutes les règles métier tiennent."
                  if not ECHECS else "ÉCHECS : {}".format(ECHECS)))
    return 1 if ECHECS else 0


if __name__ == "__main__":
    raise SystemExit(main())
