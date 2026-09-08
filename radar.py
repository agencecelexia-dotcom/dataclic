#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Radar d'opportunité Google Ads — marché artisans FR.

    ./radar.py classement --demo            classe les 96 départements
    ./radar.py fiche 31 --demo              fiche de marché pour un call
    ./radar.py motscles                     intentions et mots-clés à exclure
    ./radar.py artisans                     recensement INSEE (clé requise)
    ./radar.py verifier                     état des accès
    ./radar.py site                         serveur local sur :5000

Toutes les commandes acceptent --demo pour tourner sans aucun accès API.
"""

import argparse
import csv
import datetime
import os
import sys
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from radar import demo, metiers  # noqa: E402
from radar.fiche import rendre_html  # noqa: E402
from radar.geo import charger_departements  # noqa: E402
from radar.intention import INTENTIONS, classer, mots_cles_negatifs  # noqa: E402
from radar.scoring import (  # noqa: E402
    VERDICTS_ELIMINATOIRES, Hypotheses, classer as classer_departements)
from radar.tableau import rendre_tableau  # noqa: E402

SORTIE = "out"
_COULEUR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def c(texte, code):
    return "\033[{}m{}\033[0m".format(code, texte) if _COULEUR else str(texte)


gras = lambda t: c(t, "1")
gris = lambda t: c(t, "90")
vert = lambda t: c(t, "32")
rouge = lambda t: c(t, "31")
bleu = lambda t: c(t, "34")
ambre = lambda t: c(t, "33")


def titre(texte):
    print("\n" + gras(texte))
    print(gris("─" * max(len(texte), 40)))


def ecrire(chemin, contenu, ouvrir=False):
    os.makedirs(os.path.dirname(chemin) or ".", exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(contenu)
    print("\n  " + vert("→") + " " + chemin)
    if ouvrir:
        webbrowser.open("file://" + os.path.abspath(chemin))
    return chemin


def _hypotheses(a):
    return Hypotheses(taux_conversion=a.conversion, prix_revente_lead_eur=a.prix_lead,
                      min_artisans=a.min_artisans, part_clics_captee=a.part_clics,
                      marge_mensuelle_minimale_eur=a.seuil_mensuel)


def _n(v, suffixe="", decimales=0):
    if v is None:
        return "—"
    return ("{:,.%df}" % decimales).format(v).replace(",", " ").replace(".", ",") + suffixe


# ---------------------------------------------------------------- classement

def cmd_classement(a):
    metier = metiers.get(a.metier)
    h = _hypotheses(a)

    if not a.demo:
        print(rouge("Les données réelles exigent le Basic Access Google Ads et la "
                    "clé INSEE.\nEn attendant : ajoute --demo."), file=sys.stderr)
        return 2

    entrees = demo.entrees_scoring(metier)
    if a.sensibilite:
        return _sensibilite(entrees)

    scores = classer_departements(entrees, h)
    retenus = [s for s in scores if s.verdict not in VERDICTS_ELIMINATOIRES]

    titre("{} · {} départements".format(metier.libelle, len(scores)))
    print(gris("conversion {:.0%} · lead {:.0f} € · part clics {:.0%} · "
               "vivier min {} · plancher {:.0f} €/mois".format(
                   h.taux_conversion, h.prix_revente_lead_eur, h.part_clics_captee,
                   h.min_artisans, h.marge_mensuelle_minimale_eur)))

    entete = "  {:<4} {:<22} {:>7} {:>8} {:>8} {:>10} {:>7}  {}".format(
        "dép", "département", "volume", "€/lead", "marge", "marge/mois", "score", "verdict")
    print("\n" + gris(entete))
    for s in scores[:a.top]:
        e = s.entree
        couleur = vert if s.verdict == "prioritaire" else (
            bleu if s.verdict == "a_tester" else rouge)
        print("  {:<4} {:<22} {:>7} {:>8} {:>8} {:>10} {:>7}  {}".format(
            e.departement.code_insee, e.departement.nom[:22],
            _n(e.volume_transactionnel), _n(s.cout_par_lead_eur, " €"),
            _n(s.marge_par_lead_eur, " €"), _n(s.marge_mensuelle_eur, " €"),
            _n(s.score, "", 1), couleur(s.verdict)))

    ecartes = [s for s in scores if s.verdict in VERDICTS_ELIMINATOIRES]
    if ecartes:
        motifs = {}
        for s in ecartes:
            motifs[s.verdict] = motifs.get(s.verdict, 0) + 1
        print("\n  " + gris("{} écartés : {}".format(
            len(ecartes), ", ".join("{} {}".format(n, v) for v, n in
                                    sorted(motifs.items(), key=lambda x: -x[1])))))

    print("\n  " + gras("{} départements retenus".format(len(retenus))) +
          gris(" · {} € de marge mensuelle cumulée".format(
              _n(sum(s.marge_mensuelle_eur or 0 for s in retenus)))))

    csv_chemin = os.path.join(SORTIE, "classement_{}.csv".format(metier.cle))
    os.makedirs(SORTIE, exist_ok=True)
    with open(csv_chemin, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rang", "code_insee", "departement", "region", "volume_transactionnel",
                    "cpc_eur", "cout_par_lead_eur", "marge_par_lead_eur",
                    "leads_potentiels_mois", "marge_mensuelle_eur", "nb_etablissements",
                    "concurrence_indice", "note_marge", "note_demande", "note_absorption",
                    "score", "verdict", "motif", "niveau_geographique"])
        for rang, s in enumerate(scores, 1):
            e = s.entree
            w.writerow([rang, e.departement.code_insee, e.departement.nom,
                        e.departement.region, e.volume_transactionnel, e.cpc_eur,
                        round(s.cout_par_lead_eur or 0, 2), round(s.marge_par_lead_eur or 0, 2),
                        round(s.leads_potentiels_mois or 0, 1),
                        round(s.marge_mensuelle_eur or 0), e.nb_etablissements,
                        e.concurrence_indice, round(s.note_marge, 3),
                        round(s.note_demande, 3), round(s.note_absorption, 3),
                        round(s.score, 2), s.verdict, s.motif, e.niveau_geographique])
    print("  " + vert("→") + " " + csv_chemin)
    ecrire(os.path.join(SORTIE, "classement_{}.html".format(metier.cle)),
           rendre_tableau(scores, metier, h, donnees_fictives=a.demo), a.ouvrir)
    return 0


def _sensibilite(entrees):
    titre("Sensibilité du classement aux hypothèses")
    print(gris("  {:>6} {:>7} {:>11} {:>11} {:>11}  {}".format(
        "conv.", "lead", "part clics", "plancher", "retenus", "tête")))
    for conv, prix, part, seuil in [(0.05, 80, 0.15, 300), (0.08, 80, 0.15, 300),
                                    (0.08, 80, 0.15, 150), (0.08, 80, 0.30, 300),
                                    (0.12, 120, 0.15, 300), (0.12, 120, 0.30, 300)]:
        h = Hypotheses(taux_conversion=conv, prix_revente_lead_eur=prix,
                       part_clics_captee=part, marge_mensuelle_minimale_eur=seuil)
        scores = classer_departements(entrees, h)
        ok = [s for s in scores if s.verdict not in VERDICTS_ELIMINATOIRES]
        print("  {:>6.0%} {:>6.0f}€ {:>11.0%} {:>10.0f}€ {:>8}/{:<3} {}".format(
            conv, prix, part, seuil, len(ok), len(scores),
            ", ".join(s.departement.code_insee for s in ok[:4]) or "aucun"))
    print("\n  " + ambre("Le nombre de départements retenus et la tête du classement"))
    print("  " + ambre("changent du tout au tout selon des paramètres non mesurés."))
    print("  " + ambre("Mesure ton taux de conversion et ton prix de revente réels."))
    return 0


# --------------------------------------------------------------------- fiche

def cmd_fiche(a):
    metier = metiers.get(a.metier)
    if not a.demo:
        print(rouge("Les données réelles exigent le Basic Access Google Ads et la "
                    "clé INSEE.\nEn attendant : ajoute --demo."), file=sys.stderr)
        return 2
    try:
        donnees = demo.fiche(a.departement.upper(), metier,
                             afficher_cout_par_lead=not a.sans_cout)
    except KeyError as err:
        print(rouge(str(err)), file=sys.stderr)
        return 1

    titre("{} · {} ({})".format(metier.libelle, donnees.departement.nom,
                                donnees.departement.code_insee))
    print("  volume total          {}".format(_n(donnees.volume_total)))
    print("  volume transactionnel {}  {}".format(
        _n(donnees.volume_transactionnel),
        gris("({:.0f} % du total)".format(
            100.0 * donnees.volume_transactionnel / max(donnees.volume_total, 1)))))
    print("  entreprises actives   {}".format(_n(donnees.nb_etablissements)))
    print("  coût par lead         {}{}".format(
        _n(donnees.cout_par_lead_eur, " €"),
        gris("  (masqué sur la fiche)") if a.sans_cout else ""))
    print("  demandes/mois         {}  {}".format(
        _n(donnees.demandes_potentielles_mois), gris("(ordre de grandeur)")))
    ecrire(os.path.join(SORTIE, "fiche_{}_{}.html".format(
        metier.cle, donnees.departement.code_insee)), rendre_html(donnees), a.ouvrir)
    return 0


# ------------------------------------------------------------------ motscles

def cmd_motscles(a):
    metier = metiers.get(a.metier)
    titre("{} · NAF {}".format(metier.libelle, ", ".join(metier.codes_naf)))
    largeur = max(len(m) for m in metier.closing)
    par_intention = {}
    for mot_cle in metier.closing:
        cl = classer(mot_cle)
        par_intention.setdefault(cl.intention.cle, []).append(mot_cle)
        print("  {}  {}  {}".format(mot_cle.ljust(largeur),
                                    cl.intention.cle.ljust(16),
                                    gris("×{:.2f}".format(cl.poids))))
    print()
    for intention in INTENTIONS:
        n = len(par_intention.get(intention.cle, []))
        if n:
            print("  {:>3}  {}".format(n, intention.libelle))
    negatifs = mots_cles_negatifs(metier.closing)
    if negatifs:
        print("\n  " + ambre("À retirer :"))
        for cle, mots in negatifs.items():
            print("    {} : {}".format(cle, ", ".join(mots)))
    else:
        print("\n  " + vert("Aucun mot-clé disqualifiant dans la liste."))
    return 0


# ------------------------------------------------------------------ artisans

def cmd_artisans(a):
    from radar.insee import ClientSirene, ErreurInsee
    metier = metiers.get(a.metier)
    titre("{} · NAF {}".format(metier.libelle, ", ".join(metier.codes_naf)))
    try:
        client = ClientSirene(verbeux=True)
        if a.verifier:
            print(gris("  contrôle de cohérence, 4 requêtes…"))
            r = client.verifier(metier.codes_naf)
            print("  national {}".format(_n(r["national"])))
            for code, n in sorted(r["echantillon"].items()):
                print("  dép. {:<3} {}".format(code, _n(n)))
            ok = r["filtre_departemental_operant"] and r["corse_operante"]
            print("\n  " + (vert("filtre départemental et Corse : OK") if ok
                            else rouge("ÉCHEC — le filtre codeCommuneEtablissement:XX* "
                                       "ne discrimine pas comme prévu")))
            return 0 if ok else 1

        departements = charger_departements()
        print(gris("  {} départements, ~4 min (limite 30 req/min)…".format(
            len(departements))))
        comptages = client.compter_par_departement(metier.codes_naf, departements)
    except ErreurInsee as err:
        print("\n" + rouge(str(err)), file=sys.stderr)
        return 2

    print("\n  total {} établissements actifs".format(
        _n(sum(x.nb_etablissements for x in comptages))))
    chemin = os.path.join(SORTIE, "artisans_{}.csv".format(metier.cle))
    os.makedirs(SORTIE, exist_ok=True)
    with open(chemin, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["code_insee", "departement", "nb_etablissements_actifs", "codes_naf"])
        for x in comptages:
            w.writerow([x.code_insee, x.nom, x.nb_etablissements, " ".join(metier.codes_naf)])
    print("  " + vert("→") + " " + chemin)
    return 0


# ------------------------------------------------------------------ verifier

def cmd_verifier(a):
    titre("État des accès")
    ok = True
    manquants = []

    print("  " + gras("Référentiel géographique"))
    try:
        deps = charger_departements()
        print("    " + vert("✓") + " {} départements, geo targets Google rattachés"
              .format(len(deps)))
    except Exception as err:
        ok = False
        print("    " + rouge("✗ " + str(err)[:100]))

    print("\n  " + gras("API Sirene INSEE"))
    if not os.environ.get("INSEE_API_KEY"):
        manquants.append("clé INSEE")
        print("    " + ambre("○") + " INSEE_API_KEY absente — "
              + gris("https://portail-api.insee.fr"))
    else:
        from radar.insee import ClientSirene, ErreurInsee
        try:
            n = ClientSirene().compter(metiers.get("couverture").codes_naf, "31")
            print("    " + vert("✓") + " {} établissements en Haute-Garonne".format(n))
        except ErreurInsee as err:
            ok = False
            print("    " + rouge("✗ " + str(err).split("\n")[0][:100]))

    print("\n  " + gras("API Google Ads"))
    try:
        import google.ads.googleads  # noqa: F401
        from radar.google_ads import ClientGoogleAds, ErreurGoogleAds
        try:
            client = ClientGoogleAds()
            dep = {d.code_insee: d for d in charger_departements()}["31"]
            r = client.verifier(dep.geo_target_resource_name)
            if r["donnees_exploitables"]:
                print("    " + vert("✓") + " API {} · {} mois d'historique · volumes {}"
                      .format(r["version_api"], r["mois_historises"], r["volumes"]))
            else:
                ok = False
                print("    " + ambre("△") + " l'API répond mais les données sont vides "
                      "ou trop arrondies — " + gris("compte sans historique de dépense ?"))
                print("      " + gris("dépense 100-200 € sur quelques jours pour "
                                      "débloquer des estimations précises"))
        except ErreurGoogleAds as err:
            ok = False
            print("    " + rouge("✗ " + str(err).split("\n")[0][:110]))
    except ImportError:
        manquants.append("bibliothèque google-ads")
        print("    " + ambre("○") + " bibliothèque absente — "
              + gris("pip install google-ads==31.4.1"))

    print()
    if not ok:
        print("  " + rouge("Des accès configurés ne fonctionnent pas — voir ci-dessus."))
    elif manquants:
        print("  " + ambre("Manque : {}.".format(", ".join(manquants))))
        print("  " + gris("Toutes les commandes tournent en attendant avec --demo."))
    else:
        print("  " + vert("Tout est en place."))
    return 0 if ok else 1


# ---------------------------------------------------------------------- site

def cmd_site(a):
    try:
        from radar.web import app as application, mode_reel
    except ImportError:
        print(rouge("Flask absent : pip install -r requirements.txt"), file=sys.stderr)
        return 2
    titre("Serveur local")
    print("  mode      {}".format(vert("données réelles") if mode_reel()
                                  else ambre("démonstration")))
    print("  accès     {}".format(
        vert("protégé par mot de passe") if os.environ.get("RADAR_MOT_DE_PASSE")
        else ambre("ouvert — définis RADAR_MOT_DE_PASSE avant de déployer")))
    print("\n  " + bleu("http://127.0.0.1:{}".format(a.port)) + "\n")
    application.run(host=a.hote, port=a.port, debug=a.debug)
    return 0


# ----------------------------------------------------------------------- CLI

def main(argv=None):
    p = argparse.ArgumentParser(
        prog="radar.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sous = p.add_subparsers(dest="commande")

    def commun(sp, avec_metier=True):
        if avec_metier:
            sp.add_argument("--metier", default="couverture", choices=sorted(metiers.METIERS))
        sp.add_argument("--demo", action="store_true",
                        help="données synthétiques, aucun accès requis")
        sp.add_argument("--ouvrir", action="store_true", help="ouvrir dans le navigateur")
        return sp

    cl = commun(sous.add_parser("classement", help="classe les 96 départements"))
    cl.add_argument("--conversion", type=float, default=0.08)
    cl.add_argument("--prix-lead", type=float, default=80.0, dest="prix_lead")
    cl.add_argument("--part-clics", type=float, default=0.15, dest="part_clics")
    cl.add_argument("--seuil-mensuel", type=float, default=300.0, dest="seuil_mensuel")
    cl.add_argument("--min-artisans", type=int, default=25, dest="min_artisans")
    cl.add_argument("--top", type=int, default=15)
    cl.add_argument("--sensibilite", action="store_true",
                    help="montre la dépendance du classement aux hypothèses")
    cl.set_defaults(fonction=cmd_classement)

    fi = commun(sous.add_parser("fiche", help="fiche de marché d'un département"))
    fi.add_argument("departement", help="code INSEE : 31, 75, 2A…")
    fi.add_argument("--sans-cout", action="store_true", dest="sans_cout",
                    help="masquer le coût par lead")
    fi.set_defaults(fonction=cmd_fiche)

    mc = sous.add_parser("motscles", help="intentions et mots-clés à exclure")
    mc.add_argument("--metier", default="couverture", choices=sorted(metiers.METIERS))
    mc.set_defaults(fonction=cmd_motscles)

    ar = sous.add_parser("artisans", help="recensement INSEE par département")
    ar.add_argument("--metier", default="couverture", choices=sorted(metiers.METIERS))
    ar.add_argument("--verifier", action="store_true",
                    help="contrôle de cohérence avant balayage complet")
    ar.set_defaults(fonction=cmd_artisans)

    ve = sous.add_parser("verifier", help="état des accès")
    ve.set_defaults(fonction=cmd_verifier)

    si = sous.add_parser("site", help="serveur web local")
    si.add_argument("--port", type=int, default=5000)
    si.add_argument("--hote", default="127.0.0.1")
    si.add_argument("--debug", action="store_true")
    si.set_defaults(fonction=cmd_site)

    a = p.parse_args(argv)
    if not a.commande:
        p.print_help()
        return 0
    return a.fonction(a)


if __name__ == "__main__":
    raise SystemExit(main())
