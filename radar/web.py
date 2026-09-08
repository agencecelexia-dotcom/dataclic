# -*- coding: utf-8 -*-
"""Interface web du radar. Déployable sur Vercel (runtime Python, WSGI).

Trois pages : choix du département, fiche de marché, classement. Les rendus
HTML sont ceux de `radar.fiche` et `radar.tableau` — le site ne réimplémente
rien, il ajoute une navigation et un routage.

Garde-fous, parce qu'une URL publique branchée sur des API facturées se vide vite :

- **Mot de passe** via `RADAR_MOT_DE_PASSE` (authentification HTTP Basic). Non
  défini, le site est ouvert : ne pas déployer sans, sauf en mode démo.
- **Cache mémoire** avec TTL. Sur Vercel, chaque instance froide repart d'un
  cache vide : il amortit les rechargements d'une même session, pas plus. C'est
  suffisant pour un usage en call, pas pour du trafic.
"""

import functools
import hmac
import os
import time
from typing import Dict, Optional, Tuple

from flask import Flask, Response, abort, redirect, request, url_for

from . import demo, metiers
from .fiche import rendre_html
from .geo import charger_departements
from .metiers import Metier
from .scoring import VERDICTS_ELIMINATOIRES, Hypotheses
from .scoring import classer as classer_departements
from .tableau import rendre_tableau

TTL_CACHE_S = int(os.environ.get("RADAR_TTL_CACHE", "3600"))
_cache: Dict[str, Tuple[float, object]] = {}


def cache(cle: str, produire):
    maintenant = time.time()
    entree = _cache.get(cle)
    if entree and maintenant - entree[0] < TTL_CACHE_S:
        return entree[1]
    valeur = produire()
    _cache[cle] = (maintenant, valeur)
    return valeur


def mode_reel() -> bool:
    """Vrai si les deux accès sont configurés. Sinon le site tourne en démo."""
    if os.environ.get("RADAR_FORCER_DEMO"):
        return False
    if not os.environ.get("INSEE_API_KEY"):
        return False
    chemin = os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH", "google-ads.yaml")
    return os.path.exists(chemin) and bool(os.environ.get("GOOGLE_ADS_CUSTOMER_ID"))


# --------------------------------------------------------------------- style

STYLE = """
:root{--encre:#0f1419;--gris:#5b6874;--gris-clair:#8b959e;--trait:#e4e9ee;
--fond:#f4f6f8;--blanc:#fff;--accent:#1f6feb;--accent-fond:#e8f0fe;
--vert:#0f7b3e;--vert-fond:#e6f6ec;--ambre:#9a6300;--ambre-fond:#fff4d9;
--rouge:#b4232b;--rouge-fond:#fdeaea}
*{box-sizing:border-box}
body{margin:0;font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,
Helvetica,Arial,sans-serif;color:var(--encre);background:var(--fond)}
a{color:inherit}
.nav{background:var(--encre);color:#fff;padding:0 22px;display:flex;
align-items:center;gap:6px;flex-wrap:wrap;min-height:46px;position:sticky;top:0;z-index:20}
.nav .marque{font-weight:640;letter-spacing:-.01em;margin-right:12px;font-size:14.5px}
.nav a{color:#c2ccd6;text-decoration:none;font-size:13px;padding:6px 11px;
border-radius:6px;transition:.12s}
.nav a:hover{background:#252d36;color:#fff}
.nav a[aria-current]{background:#2b333d;color:#fff}
.nav .droite{margin-left:auto;font-size:12px;color:#7b8792;display:flex;
align-items:center;gap:8px}
.pastille{font-size:11px;padding:2px 9px;border-radius:20px;border:1px solid}
.pastille.demo{background:#3a2f10;border-color:#7a6420;color:#f0c96a}
.pastille.reel{background:#10301c;border-color:#1f6b3c;color:#6ee7a0}
@media print{.nav{display:none}}
"""

ACCUEIL_CSS = STYLE + """
.enveloppe{max-width:1080px;margin:0 auto;padding:34px 26px 70px}
.sur{font-size:11.5px;letter-spacing:.15em;text-transform:uppercase;
color:var(--gris-clair);margin:0 0 6px}
h1{font-size:27px;margin:0 0 8px;letter-spacing:-.015em}
.chapo{font-size:15px;color:var(--gris);margin:0 0 26px;max-width:66ch}
.avert{background:var(--ambre-fond);border-left:3px solid var(--ambre);color:#6b4400;
padding:11px 15px;margin:0 0 24px;font-size:13.5px;border-radius:0 5px 5px 0}
h2{font-size:12px;letter-spacing:.09em;text-transform:uppercase;color:var(--gris);
margin:30px 0 12px;font-weight:640}
.metiers{display:flex;gap:8px;flex-wrap:wrap}
.metiers a{text-decoration:none;border:1px solid var(--trait);background:var(--blanc);
border-radius:22px;padding:7px 16px;font-size:13.5px;color:var(--gris);transition:.12s}
.metiers a:hover{border-color:var(--gris-clair);color:var(--encre)}
.metiers a[aria-current]{background:var(--encre);border-color:var(--encre);color:#fff}
.actions{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0 0}
.bouton{display:inline-flex;align-items:center;gap:7px;text-decoration:none;
background:var(--accent);color:#fff;border:1px solid var(--accent);border-radius:8px;
padding:9px 17px;font-size:13.5px;font-weight:530;transition:.12s}
.bouton:hover{background:#175bc7;border-color:#175bc7}
.bouton.second{background:var(--blanc);color:var(--encre);border-color:var(--trait)}
.bouton.second:hover{border-color:var(--gris-clair);background:var(--blanc)}
input[type=search]{width:100%;max-width:380px;padding:9px 14px;border:1px solid var(--trait);
border-radius:22px;font:inherit;font-size:13.5px;background:var(--blanc);color:var(--encre)}
input[type=search]:focus{outline:2px solid var(--accent-fond);border-color:var(--accent)}
.region{margin:0 0 18px}
.region h3{font-size:12.5px;color:var(--gris-clair);margin:0 0 7px;font-weight:600}
.grille{display:flex;flex-wrap:wrap;gap:6px}
.dep{display:inline-flex;align-items:baseline;gap:6px;text-decoration:none;
background:var(--blanc);border:1px solid var(--trait);border-radius:7px;
padding:6px 11px;font-size:13px;transition:.12s;color:var(--encre)}
.dep:hover{border-color:var(--accent);background:var(--accent-fond)}
.dep b{font-variant-numeric:tabular-nums;font-weight:640;font-size:12px;color:var(--gris)}
.dep:hover b{color:var(--accent)}
.vide{color:var(--gris-clair);font-size:13px;padding:10px 0}
.pied{margin-top:40px;padding-top:16px;border-top:1px solid var(--trait);
font-size:11.5px;color:var(--gris-clair);line-height:1.7}
.pied p{margin:0 0 5px}
"""


def nav(actif: str, cle_metier: str, reel: bool) -> str:
    liens = [("accueil", url_for("accueil", metier=cle_metier), "Départements"),
             ("classement", url_for("classement", cle_metier=cle_metier), "Classement")]
    html = ['<nav class="nav"><span class="marque">Radar Celexia</span>']
    for cle, href, libelle in liens:
        html.append('<a href="{}"{}>{}</a>'.format(
            href, ' aria-current="page"' if cle == actif else "", libelle))
    html.append('<span class="droite"><span class="pastille {}">{}</span></span></nav>'
                .format("reel" if reel else "demo",
                        "données réelles" if reel else "démonstration"))
    return "".join(html)


# ------------------------------------------------------------ authentification

def protege(vue):
    @functools.wraps(vue)
    def enveloppe(*args, **kwargs):
        attendu = os.environ.get("RADAR_MOT_DE_PASSE")
        if not attendu:
            return vue(*args, **kwargs)
        auth = request.authorization
        if auth and hmac.compare_digest(auth.password or "", attendu):
            return vue(*args, **kwargs)
        return Response(
            "Accès restreint.", 401,
            {"WWW-Authenticate": 'Basic realm="Radar Celexia"'})
    return enveloppe


# -------------------------------------------------------------------- routage

def creer_app() -> Flask:
    app = Flask(__name__)

    @app.route("/")
    @protege
    def accueil():
        cle = request.args.get("metier", "couverture")
        if cle not in metiers.METIERS:
            cle = "couverture"
        return Response(page_accueil(metiers.get(cle)), mimetype="text/html")

    @app.route("/fiche/<cle_metier>/<code>")
    @protege
    def fiche(cle_metier, code):
        if cle_metier not in metiers.METIERS:
            abort(404)
        metier = metiers.get(cle_metier)
        code = code.upper()
        sans_cout = request.args.get("sans_cout") == "1"
        cle = "fiche:{}:{}:{}:{}".format(cle_metier, code, sans_cout, mode_reel())
        try:
            donnees = cache(cle, lambda: _donnees_fiche(metier, code, sans_cout))
        except KeyError:
            abort(404)
        entete = nav("accueil", cle_metier, mode_reel())
        return Response(rendre_html(donnees, entete_html=entete), mimetype="text/html")

    @app.route("/classement/<cle_metier>")
    @protege
    def classement(cle_metier):
        if cle_metier not in metiers.METIERS:
            abort(404)
        metier = metiers.get(cle_metier)
        h = _hypotheses_depuis_requete()
        cle = "classement:{}:{}:{}".format(cle_metier, hash(h), mode_reel())
        scores = cache(cle, lambda: classer_departements(
            demo.entrees_scoring(metier), h))
        entete = nav("classement", cle_metier, mode_reel())
        return Response(
            rendre_tableau(scores, metier, h, donnees_fictives=not mode_reel(),
                           entete_html=entete),
            mimetype="text/html")

    @app.route("/sante")
    def sante():
        return {"mode": "reel" if mode_reel() else "demo",
                "departements": len(charger_departements()),
                "metiers": sorted(metiers.METIERS),
                "protege": bool(os.environ.get("RADAR_MOT_DE_PASSE"))}

    @app.errorhandler(404)
    def introuvable(_):
        return Response(page_erreur("Page introuvable.",
                                    "Vérifie le code de département (01 à 95, 2A, 2B)."),
                        404, mimetype="text/html")

    return app


def _hypotheses_depuis_requete() -> Hypotheses:
    def nombre(nom, defaut, conversion=float):
        try:
            return conversion(request.args.get(nom, defaut))
        except (TypeError, ValueError):
            return conversion(defaut)
    return Hypotheses(
        taux_conversion=nombre("conversion", 0.08),
        prix_revente_lead_eur=nombre("prix_lead", 80.0),
        part_clics_captee=nombre("part_clics", 0.15),
        min_artisans=nombre("min_artisans", 25, int),
        marge_mensuelle_minimale_eur=nombre("seuil_mensuel", 300.0),
    )


def _donnees_fiche(metier: Metier, code: str, sans_cout: bool):
    # En mode réel, la collecte passerait par radar.pipeline. Tant que le
    # developer token n'est pas approuvé, le site sert des données de démo et
    # l'annonce explicitement plutôt que de renvoyer une erreur.
    return demo.fiche(code, metier, afficher_cout_par_lead=not sans_cout)


# --------------------------------------------------------------------- pages

def _e(t):
    import html
    return html.escape(str(t), quote=True)


def page_accueil(metier: Metier) -> str:
    reel = mode_reel()
    departements = charger_departements()

    par_region = {}
    for d in departements:
        par_region.setdefault(d.region or "Autres", []).append(d)

    blocs = []
    for region in sorted(par_region):
        puces = "".join(
            '<a class="dep" href="{}" data-r="{}"><b>{}</b>{}</a>'.format(
                url_for("fiche", cle_metier=metier.cle, code=d.code_insee),
                _e((d.code_insee + " " + d.nom + " " + region).lower()),
                _e(d.code_insee), _e(d.nom))
            for d in par_region[region])
        blocs.append('<div class="region" data-region="{}"><h3>{}</h3>'
                     '<div class="grille">{}</div></div>'.format(
                         _e(region.lower()), _e(region), puces))

    chips = "".join(
        '<a href="{}"{}>{}</a>'.format(
            url_for("accueil", metier=m.cle),
            ' aria-current="true"' if m.cle == metier.cle else "", _e(m.libelle))
        for m in (metiers.get(c) for c in sorted(metiers.METIERS)))

    avert = "" if reel else (
        '<div class="avert"><strong>Mode démonstration.</strong> Les accès '
        "Google Ads et INSEE ne sont pas configurés : les chiffres affichés sont "
        "synthétiques et ne décrivent aucun marché réel. Ne pas les présenter à "
        "un artisan.</div>")

    return """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Radar Celexia — {metier}</title>
<style>{css}</style></head><body>
{nav}
<div class="enveloppe">
  <p class="sur">Radar d'opportunité Google Ads</p>
  <h1>{metier}</h1>
  <p class="chapo">Choisis un département pour générer sa fiche de marché, ou
     ouvre le classement des 96 départements pour savoir où ouvrir une campagne
     en priorité.</p>
  {avert}
  <h2>Métier</h2>
  <div class="metiers">{chips}</div>
  <div class="actions">
    <a class="bouton" href="{lien_classement}">Voir le classement des 96 départements</a>
    <a class="bouton second" href="{lien_classement}?conversion=0.12&amp;prix_lead=120">
      Classement à 12 % / 120 €</a>
  </div>
  <h2>Départements</h2>
  <input type="search" id="recherche" placeholder="Filtrer : 31, Gironde, Bretagne…"
         aria-label="Filtrer les départements" autocomplete="off">
  <div id="blocs" style="margin-top:14px">{blocs}</div>
  <p class="vide" id="vide" hidden>Aucun département ne correspond.</p>
  <div class="pied">
    <p>Les estimations du Keyword Planner sont directionnelles : elles servent à
       comparer des départements entre eux, pas à budgéter au centime.</p>
    <p>Les Local Service Ads sont un angle mort — elles se facturent au lead et
       n'apparaissent ni dans le Keyword Planner ni dans l'API Google Ads.</p>
  </div>
</div>
<script>
(function(){{
 var champ=document.getElementById('recherche');
 var deps=[].slice.call(document.querySelectorAll('.dep'));
 var regions=[].slice.call(document.querySelectorAll('.region'));
 var vide=document.getElementById('vide');
 champ.addEventListener('input',function(){{
  var q=champ.value.toLowerCase().trim(), total=0;
  deps.forEach(function(a){{
   var ok=!q||a.dataset.r.indexOf(q)!==-1; a.hidden=!ok; if(ok) total++;
  }});
  regions.forEach(function(r){{
   r.hidden = !r.querySelector('.dep:not([hidden])');
  }});
  vide.hidden = total>0;
 }});
 champ.focus();
}})();
</script>
</body></html>""".format(
        css=ACCUEIL_CSS, nav=nav("accueil", metier.cle, reel),
        metier=_e(metier.libelle), avert=avert, chips=chips, blocs="".join(blocs),
        lien_classement=url_for("classement", cle_metier=metier.cle))


def page_erreur(titre: str, detail: str) -> str:
    return """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{t}</title><style>{css}
.enveloppe{{max-width:560px;margin:0 auto;padding:70px 26px;text-align:center}}
h1{{font-size:22px;margin:0 0 10px}}p{{color:var(--gris);margin:0 0 22px}}
a{{color:var(--accent)}}</style></head><body>
<div class="enveloppe"><h1>{t}</h1><p>{d}</p><a href="/">← Retour</a></div>
</body></html>""".format(t=_e(titre), d=_e(detail), css=STYLE)


app = creer_app()
