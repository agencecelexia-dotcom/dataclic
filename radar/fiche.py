# -*- coding: utf-8 -*-
"""Fiche de marché destinée aux calls de closing avec un artisan.

Objectif : passer d'un discours d'agence à une démonstration chiffrée sur SON
marché. Le document est autonome (aucune ressource externe, graphiques en SVG
inline) pour rester lisible en visio, imprimable en PDF et envoyable par mail.

Le modèle de données est volontairement séparé du rendu : la couche Google Ads
n'aura qu'à remplir `DonneesFiche`.
"""

import datetime
import html
from typing import List, NamedTuple, Optional

from .geo import Departement
from .intention import classer
from .metiers import Metier

MOIS_FR = ["", "janvier", "février", "mars", "avril", "mai", "juin",
           "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
MOIS_COURT = ["", "jan", "fév", "mar", "avr", "mai", "jun",
              "jul", "aoû", "sep", "oct", "nov", "déc"]


class MoisVolume(NamedTuple):
    annee: int
    mois: int          # 1-12
    volume: int


class LigneMotCle(NamedTuple):
    mot_cle: str
    volume_mensuel_moyen: int
    # Fourchette d'enchère haut de page (20e/80e percentile). CE NE SONT PAS DES CPC :
    # ce sont des enchères recommandées par Google, pas des coûts réellement payés.
    enchere_haut_page_basse_eur: Optional[float] = None
    enchere_haut_page_haute_eur: Optional[float] = None
    concurrence_indice: Optional[int] = None  # 0-100


class DonneesFiche(NamedTuple):
    departement: Departement
    metier: Metier
    mots_cles: List[LigneMotCle]
    saisonnalite: List[MoisVolume]
    # Nombre d'établissements actifs du métier dans le département (INSEE).
    nb_etablissements: Optional[int] = None
    # Hypothèse de taux de conversion de la landing page, pour le coût par lead.
    taux_conversion: float = 0.08
    # CPC issu d'une *prévision* Google Ads : dépend du budget et de l'enchère
    # max fournis en entrée. Ce n'est pas une observation de marché.
    cpc_prevu_eur: Optional[float] = None
    cpc_prevu_hypotheses: str = ""
    # "departement" ou "region" : Google plancher-arrondit les petits volumes,
    # un repli région est parfois nécessaire. Doit rester visible.
    niveau_geographique: str = "departement"
    donnees_fictives: bool = False
    date_extraction: Optional[datetime.date] = None
    # Afficher le coût par lead ancre l'artisan sur ce que coûte l'acquisition —
    # ce qui peut jouer contre le prix auquel Celexia revend le lead. À arbitrer
    # selon l'interlocuteur ; voir la note dans le README.
    afficher_cout_par_lead: bool = True

    # -- indicateurs dérivés ------------------------------------------------

    @property
    def volume_total(self) -> int:
        return sum(m.volume_mensuel_moyen for m in self.mots_cles)

    @property
    def volume_transactionnel(self) -> int:
        """Volume pondéré par l'intention : seul celui-là vaut quelque chose."""
        return int(round(sum(
            m.volume_mensuel_moyen * classer(m.mot_cle).poids for m in self.mots_cles)))

    @property
    def enchere_moyenne_eur(self) -> Optional[float]:
        """Milieu des fourchettes d'enchère, pondéré par le volume."""
        paires = [(m.volume_mensuel_moyen,
                   (m.enchere_haut_page_basse_eur + m.enchere_haut_page_haute_eur) / 2)
                  for m in self.mots_cles
                  if m.enchere_haut_page_basse_eur and m.enchere_haut_page_haute_eur]
        if not paires:
            return None
        poids = sum(p for p, _ in paires)
        return sum(p * v for p, v in paires) / poids if poids else None

    @property
    def cout_par_lead_eur(self) -> Optional[float]:
        """CPC ÷ taux de conversion. C'est l'indicateur qui décide, pas le CPC."""
        base = self.cpc_prevu_eur or self.enchere_moyenne_eur
        if not base or self.taux_conversion <= 0:
            return None
        return base / self.taux_conversion

    @property
    def demandes_potentielles_mois(self) -> Optional[int]:
        """Ordre de grandeur : volume transactionnel × part de clics captée × conversion."""
        if not self.taux_conversion:
            return None
        # Hypothèse volontairement basse d'une part de clics de 15 % du volume
        # transactionnel : on n'achète jamais tout le marché.
        return int(round(self.volume_transactionnel * 0.15 * self.taux_conversion))

    @property
    def mois_forts(self) -> List[MoisVolume]:
        if not self.saisonnalite:
            return []
        moyenne = sum(m.volume for m in self.saisonnalite) / len(self.saisonnalite)
        return [m for m in self.saisonnalite if m.volume > moyenne * 1.1]


def _eur(valeur: Optional[float], decimales: int = 2) -> str:
    if valeur is None:
        return "—"
    return ("{:,.%df}" % decimales).format(valeur).replace(",", " ").replace(".", ",") + " €"


def _nombre(valeur: Optional[float]) -> str:
    if valeur is None:
        return "—"
    return "{:,.0f}".format(valeur).replace(",", " ")


def _e(texte: str) -> str:
    return html.escape(str(texte), quote=True)


# ---------------------------------------------------------------------------
# Rendu HTML
# ---------------------------------------------------------------------------

_CSS = """
:root{--encre:#12181f;--gris:#5b6874;--trait:#e2e7ec;--fond:#f6f8fa;
--accent:#1f6feb;--accent-clair:#e8f0fe;--alerte:#b45309}
*{box-sizing:border-box}
body{margin:0;font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
color:var(--encre);background:var(--fond)}
.page{max-width:880px;margin:0 auto;padding:40px 44px 56px;background:#fff}
header{border-bottom:3px solid var(--encre);padding-bottom:18px;margin-bottom:28px}
.sur{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--gris);margin:0 0 6px}
h1{font-size:27px;line-height:1.2;margin:0 0 8px;letter-spacing:-.01em}
h2{font-size:15px;letter-spacing:.09em;text-transform:uppercase;color:var(--gris);
margin:34px 0 14px;padding-bottom:7px;border-bottom:1px solid var(--trait)}
.meta{font-size:13px;color:var(--gris)}
.avert{background:#fef3c7;border-left:4px solid var(--alerte);color:#78350f;
padding:11px 14px;margin:0 0 24px;font-size:13.5px;border-radius:0 4px 4px 0}
.cartes{display:flex;flex-wrap:wrap;gap:12px;margin:0 0 6px}
.carte{flex:1 1 190px;border:1px solid var(--trait);border-radius:7px;padding:15px 17px;background:#fff}
.carte.fort{border-color:var(--accent);background:var(--accent-clair)}
.carte .val{font-size:29px;font-weight:650;letter-spacing:-.02em;line-height:1.1}
.carte .lib{font-size:12.5px;color:var(--gris);margin-top:5px}
.carte .note{font-size:11.5px;color:var(--gris);margin-top:7px;font-style:italic}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;font-size:11.5px;letter-spacing:.05em;text-transform:uppercase;
color:var(--gris);font-weight:600;padding:0 8px 8px;border-bottom:1px solid var(--trait)}
td{padding:8px;border-bottom:1px solid var(--trait)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tr.total td{font-weight:650;border-top:2px solid var(--encre);border-bottom:none}
.tag{display:inline-block;font-size:11px;padding:2px 7px;border-radius:20px;
background:var(--fond);color:var(--gris);border:1px solid var(--trait);white-space:nowrap}
.tag.chaud{background:#fee2e2;border-color:#fca5a5;color:#991b1b}
.tag.devis{background:#dcfce7;border-color:#86efac;color:#166534}
p.intro{font-size:15.5px;color:var(--encre);margin:0 0 22px}
.pied{margin-top:38px;padding-top:16px;border-top:1px solid var(--trait);
font-size:11.5px;color:var(--gris)}
.pied p{margin:0 0 7px}
@media print{body{background:#fff}.page{max-width:none;padding:0}
 .carte{break-inside:avoid}h2{break-after:avoid}}
"""


def _svg_saisonnalite(mois: List[MoisVolume]) -> str:
    """Histogramme 12 mois en SVG inline (aucune dépendance, survit à un envoi mail)."""
    if not mois:
        return ""
    largeur, hauteur = 800, 210
    marge_bas, marge_haut = 34, 22
    maxi = max(m.volume for m in mois) or 1
    moyenne = sum(m.volume for m in mois) / len(mois)
    pas = largeur / len(mois)
    barre = pas * 0.58
    utile = hauteur - marge_bas - marge_haut

    parties = ['<svg viewBox="0 0 {} {}" width="100%" role="img" '
               'aria-label="Volume de recherche mois par mois">'.format(largeur, hauteur)]
    y_moy = marge_haut + utile - (moyenne / maxi) * utile
    parties.append(
        '<line x1="0" y1="{0:.1f}" x2="{1}" y2="{0:.1f}" stroke="#c9d1d9" '
        'stroke-dasharray="4 4"/>'.format(y_moy, largeur))
    parties.append('<text x="{}" y="{:.1f}" font-size="10" fill="#8b949e" '
                   'text-anchor="end">moyenne</text>'.format(largeur - 2, y_moy - 4))

    for i, m in enumerate(mois):
        h = (m.volume / maxi) * utile
        x = i * pas + (pas - barre) / 2
        y = marge_haut + utile - h
        fort = m.volume > moyenne * 1.1
        parties.append('<rect x="{:.1f}" y="{:.1f}" width="{:.1f}" height="{:.1f}" rx="2.5" '
                       'fill="{}"/>'.format(x, y, barre, max(h, 1),
                                            "#1f6feb" if fort else "#b6c2cf"))
        parties.append('<text x="{:.1f}" y="{:.1f}" font-size="10.5" fill="#5b6874" '
                       'text-anchor="middle">{}</text>'.format(
                           x + barre / 2, y - 5, _nombre(m.volume)))
        parties.append('<text x="{:.1f}" y="{}" font-size="11" fill="#5b6874" '
                       'text-anchor="middle">{}</text>'.format(
                           x + barre / 2, hauteur - 14, MOIS_COURT[m.mois]))
    parties.append("</svg>")
    return "".join(parties)


def _tag_intention(mot_cle: str) -> str:
    cle = classer(mot_cle).intention.cle
    classe = {"urgence": "tag chaud", "devis": "tag devis"}.get(cle, "tag")
    libelle = {"urgence": "urgence", "devis": "devis", "prix": "prix",
               "generique": "générique", "information": "info"}.get(cle, cle)
    return '<span class="{}">{}</span>'.format(classe, libelle)


def rendre_html(d: DonneesFiche, entete_html: str = "") -> str:
    """`entete_html` est inséré juste après <body>, pour la navigation du site."""
    dep = d.departement
    date = d.date_extraction or datetime.date.today()
    lignes = sorted(d.mots_cles, key=lambda m: -m.volume_mensuel_moyen)

    avert = ""
    if d.donnees_fictives:
        avert = ('<div class="avert"><strong>Document de démonstration.</strong> '
                 "Les chiffres de cette page sont fictifs et ne doivent pas être "
                 "présentés à un artisan.</div>")

    repli = ""
    if d.niveau_geographique != "departement":
        repli = ('<div class="avert">Volumes mesurés au niveau <strong>{}</strong> : '
                 "le volume départemental était trop faible pour être fiable.</div>"
                 .format(_e(d.niveau_geographique)))

    cartes = [
        ('<div class="carte fort"><div class="val">{}</div>'
         '<div class="lib">recherches/mois, tous mots-clés</div></div>'
         .format(_nombre(d.volume_total))),
        ('<div class="carte"><div class="val">{}</div>'
         '<div class="lib">dont recherches à intention commerciale</div>'
         '<div class="note">Le reste est de la documentation, de la formation ou du bricolage.</div>'
         "</div>".format(_nombre(d.volume_transactionnel))),
    ]
    if d.nb_etablissements is not None:
        cartes.append(
            '<div class="carte"><div class="val">{}</div>'
            '<div class="lib">entreprises {} actives dans le {}</div></div>'
            .format(_nombre(d.nb_etablissements), _e(d.metier.libelle.lower()),
                    _e(dep.code_insee)))
    if d.cout_par_lead_eur and d.afficher_cout_par_lead:
        cartes.append(
            '<div class="carte"><div class="val">{}</div>'
            '<div class="lib">coût estimé par demande de devis</div>'
            '<div class="note">à {:.0f} % de conversion</div></div>'
            .format(_eur(d.cout_par_lead_eur, 0), d.taux_conversion * 100))

    rangs = []
    for m in lignes:
        fourchette = "—"
        if m.enchere_haut_page_basse_eur and m.enchere_haut_page_haute_eur:
            fourchette = "{} – {}".format(_eur(m.enchere_haut_page_basse_eur),
                                          _eur(m.enchere_haut_page_haute_eur))
        rangs.append(
            "<tr><td>{}</td><td>{}</td><td class='num'>{}</td>"
            "<td class='num'>{}</td><td class='num'>{}</td></tr>".format(
                _e(m.mot_cle), _tag_intention(m.mot_cle),
                _nombre(m.volume_mensuel_moyen), fourchette,
                m.concurrence_indice if m.concurrence_indice is not None else "—"))
    rangs.append("<tr class='total'><td colspan='2'>Total</td>"
                 "<td class='num'>{}</td><td class='num'></td>"
                 "<td class='num'></td></tr>".format(_nombre(d.volume_total)))

    saison = ""
    if d.saisonnalite:
        forts = d.mois_forts
        commentaire = ""
        if forts:
            noms = [MOIS_FR[m.mois] for m in forts]
            commentaire = ("<p class='meta'>Pics de demande : <strong>{}</strong>. "
                           "C'est là qu'il faut avoir de la capacité disponible.</p>"
                           .format(_e(", ".join(noms))))
        saison = ("<h2>Quand vos clients cherchent</h2>{}{}"
                  .format(_svg_saisonnalite(d.saisonnalite), commentaire))

    concurrence = ""
    if d.nb_etablissements:
        par_entreprise = d.volume_transactionnel / d.nb_etablissements
        concurrence = (
            "<h2>Le marché face à vous</h2>"
            "<p>Le département compte <strong>{}</strong> entreprises {} actives, "
            "pour <strong>{}</strong> recherches à intention commerciale par mois — soit "
            "<strong>{:.0f} demandes potentielles par entreprise et par mois</strong> "
            "si le marché était réparti également. Il ne l'est pas : il va à celles "
            "qui sont visibles au moment où la recherche est faite.</p>"
            .format(_nombre(d.nb_etablissements), _e(d.metier.libelle.lower()),
                    _nombre(d.volume_transactionnel), par_entreprise))

    notes = ["Source : Google Ads Keyword Planner et INSEE (base Sirene), "
             "données extraites le {}.".format(date.strftime("%d/%m/%Y")),
             "La colonne « enchère haut de page » correspond aux enchères "
             "recommandées par Google (20ᵉ et 80ᵉ percentile). Ce ne sont pas "
             "des coûts par clic réellement payés."]
    if d.cpc_prevu_eur and d.afficher_cout_par_lead:
        notes.append("Le coût par demande est calculé à partir d'une prévision Google Ads{}. "
                     "Une prévision dépend du budget et de l'enchère qu'on lui fournit : "
                     "c'est un ordre de grandeur, pas un tarif."
                     .format(" (" + d.cpc_prevu_hypotheses + ")" if d.cpc_prevu_hypotheses else ""))
    notes.append("Les volumes du Keyword Planner sont directionnels. Ils servent à "
                 "comparer des marchés entre eux, pas à budgéter au centime.")

    return """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Marché {metier} — {dep} ({code})</title>
<style>{css}</style></head><body>{entete}<div class="page">
{avert}{repli}
<header>
  <p class="sur">Étude de marché locale — Celexia</p>
  <h1>{metier} dans le {code} — {dep}</h1>
  <p class="meta">{region} · données au {date}</p>
</header>
<p class="intro">Voici ce que les particuliers de votre département tapent sur Google
quand ils cherchent un professionnel comme vous, et ce que coûte le fait d'être
visible à ce moment-là.</p>
<div class="cartes">{cartes}</div>
{saison}
<h2>Ce que les gens tapent</h2>
<table><thead><tr>
<th>Recherche</th><th>Intention</th><th class="num">Par mois</th>
<th class="num">Enchère haut de page</th><th class="num">Concurrence</th>
</tr></thead><tbody>{rangs}</tbody></table>
{concurrence}
<div class="pied">{notes}</div>
</div></body></html>""".format(
        css=_CSS, entete=entete_html, avert=avert, repli=repli,
        metier=_e(d.metier.libelle), dep=_e(dep.nom), code=_e(dep.code_insee),
        region=_e(dep.region), date=date.strftime("%d/%m/%Y"),
        cartes="".join(cartes), saison=saison, rangs="".join(rangs),
        concurrence=concurrence,
        notes="".join("<p>{}</p>".format(_e(n)) for n in notes))
