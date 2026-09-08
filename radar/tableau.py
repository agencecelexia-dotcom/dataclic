# -*- coding: utf-8 -*-
"""Tableau de bord HTML du classement des départements.

Fichier statique autonome : aucune ressource externe, tri et filtres en
JavaScript inline. On l'ouvre, on trie, on filtre, on imprime. Pas de serveur.
"""

import datetime
import html
import json
from typing import List, Optional

from .metiers import Metier
from .scoring import VERDICTS_ELIMINATOIRES, Hypotheses, ScoreDepartement

LIBELLES_VERDICT = {
    "prioritaire": "Prioritaire",
    "a_tester": "À tester",
    "marge_insuffisante": "Marge insuffisante",
    "vivier_insuffisant": "Vivier insuffisant",
    "marche_trop_petit": "Marché trop petit",
    "donnees_absentes": "Données absentes",
}

_CSS = """
:root{--encre:#0f1419;--gris:#5b6874;--gris-clair:#8b959e;--trait:#e4e9ee;
--fond:#f4f6f8;--blanc:#fff;--accent:#1f6feb;--accent-fond:#e8f0fe;
--vert:#0f7b3e;--vert-fond:#e6f6ec;--ambre:#9a6300;--ambre-fond:#fff4d9;
--rouge:#b4232b;--rouge-fond:#fdeaea}
*{box-sizing:border-box}
body{margin:0;font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,
Helvetica,Arial,sans-serif;color:var(--encre);background:var(--fond)}
.enveloppe{max-width:1360px;margin:0 auto;padding:28px 26px 60px}
header{margin-bottom:22px}
.sur{font-size:11.5px;letter-spacing:.15em;text-transform:uppercase;
color:var(--gris-clair);margin:0 0 5px}
h1{font-size:25px;margin:0 0 6px;letter-spacing:-.015em}
.hypo{font-size:13px;color:var(--gris);margin:0}
.hypo code{background:var(--blanc);border:1px solid var(--trait);border-radius:4px;
padding:1px 6px;font-size:12.5px}
.avert{background:var(--ambre-fond);border-left:3px solid var(--ambre);color:#6b4400;
padding:10px 14px;margin:16px 0 0;font-size:13px;border-radius:0 5px 5px 0}
.cartes{display:grid;grid-template-columns:repeat(auto-fit,minmax(178px,1fr));
gap:11px;margin:20px 0 22px}
.carte{background:var(--blanc);border:1px solid var(--trait);border-radius:9px;padding:14px 16px}
.carte .v{font-size:26px;font-weight:640;letter-spacing:-.02em;line-height:1.15}
.carte .l{font-size:12px;color:var(--gris);margin-top:4px}
.barre{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:14px}
.puce{border:1px solid var(--trait);background:var(--blanc);border-radius:20px;
padding:5px 13px;font-size:12.5px;color:var(--gris);cursor:pointer;
font-family:inherit;transition:.12s}
.puce:hover{border-color:var(--gris-clair);color:var(--encre)}
.puce[aria-pressed=true]{background:var(--encre);border-color:var(--encre);color:#fff}
.puce .n{opacity:.6;margin-left:5px;font-variant-numeric:tabular-nums}
input[type=search]{flex:1;min-width:180px;padding:7px 12px;border:1px solid var(--trait);
border-radius:20px;font:inherit;font-size:13px;background:var(--blanc);color:var(--encre)}
input[type=search]:focus{outline:2px solid var(--accent-fond);border-color:var(--accent)}
.cadre{background:var(--blanc);border:1px solid var(--trait);border-radius:10px;
overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th{position:sticky;top:0;background:var(--blanc);text-align:left;font-size:11px;
letter-spacing:.04em;text-transform:uppercase;color:var(--gris);font-weight:600;
padding:11px 10px;border-bottom:1px solid var(--trait);white-space:nowrap;
cursor:pointer;user-select:none}
th:hover{color:var(--encre)}
th .fl{opacity:0;font-size:9px;margin-left:3px}
th[data-sens] .fl{opacity:.85}
td{padding:9px 10px;border-bottom:1px solid var(--trait);white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover{background:#fafbfc}
tr.ecarte td{color:var(--gris-clair)}
.num{text-align:right;font-variant-numeric:tabular-nums}
.dep{font-weight:600;font-variant-numeric:tabular-nums}
.nom{font-weight:530}
.reg{color:var(--gris-clair);font-size:12px}
.score{display:flex;align-items:center;gap:8px;justify-content:flex-end}
.score .j{width:52px;height:5px;background:var(--trait);border-radius:3px;overflow:hidden}
.score .j i{display:block;height:100%;background:var(--accent);border-radius:3px}
.score b{font-variant-numeric:tabular-nums;font-weight:620;min-width:34px;text-align:right}
.et{display:inline-block;font-size:11px;padding:2px 8px;border-radius:20px;
border:1px solid;white-space:nowrap}
.et.prioritaire{background:var(--vert-fond);border-color:#a8dcbc;color:var(--vert)}
.et.a_tester{background:var(--accent-fond);border-color:#b9d3fb;color:var(--accent)}
.et.marge_insuffisante,.et.vivier_insuffisant,.et.marche_trop_petit,
.et.donnees_absentes{background:var(--rouge-fond);border-color:#f2c2c2;color:var(--rouge)}
.motif{font-size:11.5px;color:var(--gris-clair);max-width:280px;overflow:hidden;
text-overflow:ellipsis;white-space:nowrap}
.vide{padding:36px;text-align:center;color:var(--gris-clair)}
.pied{margin-top:20px;font-size:11.5px;color:var(--gris-clair);line-height:1.65}
.pied p{margin:0 0 5px}
@media print{body{background:#fff}.enveloppe{max-width:none;padding:0}
 .barre,.puce{display:none}.cadre{border:none}th{position:static}
 td,th{white-space:normal}}
"""

_JS = """
(function(){
 var lignes=Array.prototype.slice.call(document.querySelectorAll('tbody tr'));
 var puces=Array.prototype.slice.call(document.querySelectorAll('.puce'));
 var recherche=document.getElementById('recherche');
 var vide=document.getElementById('vide');
 var filtre='tous';

 function appliquer(){
  var q=(recherche.value||'').toLowerCase().trim(), visibles=0;
  lignes.forEach(function(tr){
   var okF = filtre==='tous'
     || (filtre==='retenus' && tr.dataset.retenu==='1')
     || tr.dataset.verdict===filtre;
   var okQ = !q || tr.dataset.recherche.indexOf(q)!==-1;
   var ok = okF && okQ;
   tr.hidden = !ok;
   if(ok) visibles++;
  });
  vide.hidden = visibles>0;
 }

 puces.forEach(function(p){
  p.addEventListener('click',function(){
   puces.forEach(function(o){o.setAttribute('aria-pressed', o===p?'true':'false');});
   filtre=p.dataset.filtre; appliquer();
  });
 });
 recherche.addEventListener('input',appliquer);

 var corps=document.querySelector('tbody');
 Array.prototype.slice.call(document.querySelectorAll('th[data-cle]')).forEach(function(th){
  th.addEventListener('click',function(){
   var cle=th.dataset.cle;
   var sens = th.getAttribute('data-sens')==='asc' ? 'desc' : 'asc';
   document.querySelectorAll('th[data-sens]').forEach(function(o){o.removeAttribute('data-sens');});
   th.setAttribute('data-sens',sens);
   th.querySelector('.fl').textContent = sens==='asc' ? '\\u25B2' : '\\u25BC';
   var signe = sens==='asc' ? 1 : -1;
   lignes.sort(function(a,b){
    var x=a.dataset[cle], y=b.dataset[cle];
    var nx=parseFloat(x), ny=parseFloat(y);
    if(!isNaN(nx)&&!isNaN(ny)) return signe*(nx-ny);
    return signe*String(x).localeCompare(String(y),'fr');
   });
   lignes.forEach(function(tr){corps.appendChild(tr);});
  });
 });
})();
"""


def _n(v, suffixe="", decimales=0):
    if v is None:
        return "—"
    s = ("{:,.%df}" % decimales).format(v).replace(",", " ").replace(".", ",")
    return s + suffixe


def _e(t):
    return html.escape(str(t), quote=True)


def rendre_tableau(scores: List[ScoreDepartement], metier: Metier,
                   hypotheses: Hypotheses, donnees_fictives: bool = False,
                   date: Optional[datetime.date] = None) -> str:
    date = date or datetime.date.today()
    retenus = [s for s in scores if s.verdict not in VERDICTS_ELIMINATOIRES]
    marge_totale = sum(s.marge_mensuelle_eur or 0 for s in retenus)
    entreprises = sum(s.entree.nb_etablissements or 0 for s in retenus)
    meilleur = retenus[0] if retenus else None

    compte = {}
    for s in scores:
        compte[s.verdict] = compte.get(s.verdict, 0) + 1

    avert = ""
    if donnees_fictives:
        avert = ('<div class="avert"><strong>Données synthétiques.</strong> '
                 "Ce classement démontre le fonctionnement du moteur, il ne "
                 "décrit aucun marché réel.</div>")

    cartes = [
        ("{} / {}".format(len(retenus), len(scores)), "départements retenus"),
        (_n(marge_totale, " €"), "marge mensuelle potentielle cumulée"),
        (_n(entreprises), "entreprises à démarcher sur ces départements"),
    ]
    if meilleur:
        cartes.append(("{} · {}".format(meilleur.departement.code_insee,
                                        meilleur.departement.nom),
                       "tête de classement"))

    puces = [("tous", "Tous", len(scores)), ("retenus", "Retenus", len(retenus))]
    for cle in ("prioritaire", "a_tester", "vivier_insuffisant",
                "marge_insuffisante", "marche_trop_petit", "donnees_absentes"):
        if compte.get(cle):
            puces.append((cle, LIBELLES_VERDICT[cle], compte[cle]))

    colonnes = [
        ("rang", "#", "num"), ("code", "Dép.", ""), ("nom", "Département", ""),
        ("region", "Région", ""), ("volume", "Vol. transac.", "num"),
        ("cpc", "CPC", "num"), ("cpl", "€ / lead", "num"),
        ("marge", "Marge / lead", "num"), ("leads", "Leads / mois", "num"),
        ("margemois", "Marge / mois", "num"), ("entreprises", "Entreprises", "num"),
        ("score", "Score", "num"), ("verdict", "Verdict", ""),
    ]

    rangs = []
    for rang, s in enumerate(scores, 1):
        e = s.entree
        ecarte = s.verdict in VERDICTS_ELIMINATOIRES
        cherchable = " ".join([e.departement.code_insee, e.departement.nom,
                               e.departement.region,
                               LIBELLES_VERDICT.get(s.verdict, s.verdict)]).lower()
        data = {
            "rang": rang, "code": e.departement.code_insee, "nom": e.departement.nom,
            "region": e.departement.region, "volume": e.volume_transactionnel,
            "cpc": e.cpc_eur or 0, "cpl": s.cout_par_lead_eur or 0,
            "marge": s.marge_par_lead_eur or 0, "leads": s.leads_potentiels_mois or 0,
            "margemois": s.marge_mensuelle_eur or 0,
            "entreprises": e.nb_etablissements or 0, "score": s.score,
            "verdict": s.verdict,
        }
        attrs = " ".join('data-{}="{}"'.format(k, _e(v)) for k, v in data.items())
        rangs.append(
            '<tr {attrs} data-retenu="{ret}" data-recherche="{rech}" class="{cl}">'
            '<td class="num">{rang}</td>'
            '<td class="dep">{code}</td>'
            '<td class="nom">{nom}</td>'
            '<td class="reg">{region}</td>'
            '<td class="num">{vol}</td>'
            '<td class="num">{cpc}</td>'
            '<td class="num">{cpl}</td>'
            '<td class="num">{marge}</td>'
            '<td class="num">{leads}</td>'
            '<td class="num">{margemois}</td>'
            '<td class="num">{ent}</td>'
            '<td class="num"><span class="score"><span class="j">'
            '<i style="width:{barre:.0f}%"></i></span><b>{score}</b></span></td>'
            '<td><span class="et {vcl}">{vlib}</span>'
            '{motif}</td></tr>'.format(
                attrs=attrs, ret="0" if ecarte else "1", rech=_e(cherchable),
                cl="ecarte" if ecarte else "", rang=rang,
                code=_e(e.departement.code_insee), nom=_e(e.departement.nom),
                region=_e(e.departement.region), vol=_n(e.volume_transactionnel),
                cpc=_n(e.cpc_eur, " €", 2), cpl=_n(s.cout_par_lead_eur, " €"),
                marge=_n(s.marge_par_lead_eur, " €"),
                leads=_n(s.leads_potentiels_mois, "", 1),
                margemois=_n(s.marge_mensuelle_eur, " €"),
                ent=_n(e.nb_etablissements), barre=min(100.0, s.score),
                score=_n(s.score, "", 1), vcl=_e(s.verdict),
                vlib=_e(LIBELLES_VERDICT.get(s.verdict, s.verdict)),
                motif='<div class="motif" title="{0}">{0}</div>'.format(_e(s.motif))
                if s.motif else ""))

    return """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Radar {metier} — classement des départements</title>
<style>{css}</style></head><body><div class="enveloppe">
<header>
  <p class="sur">Radar d'opportunité Google Ads — Celexia</p>
  <h1>{metier} · classement des 96 départements</h1>
  <p class="hypo">Hypothèses : conversion <code>{conv:.0%}</code> ·
     lead revendu <code>{prix:.0f} €</code> ·
     part de clics captée <code>{part:.0%}</code> ·
     vivier minimum <code>{minart}</code> ·
     marge mensuelle plancher <code>{seuil:.0f} €</code></p>
  {avert}
</header>
<div class="cartes">{cartes}</div>
<div class="barre">{puces}
  <input type="search" id="recherche" placeholder="Filtrer par département ou région…"
         aria-label="Filtrer">
</div>
<div class="cadre">
<table><thead><tr>{entetes}</tr></thead><tbody>{rangs}</tbody></table>
<div class="vide" id="vide" hidden>Aucun département ne correspond.</div>
</div>
<div class="pied">
  <p>Généré le {date}. Cliquer un en-tête pour trier.</p>
  <p>Les colonnes CPC proviennent des enchères haut de page recommandées par
     Google, pas de coûts par clic réellement payés : le classement est donc
     prudent plutôt qu'optimiste.</p>
  <p>Les estimations du Keyword Planner sont directionnelles. Elles servent à
     comparer des départements entre eux, pas à budgéter au centime : la
     validation passe par quelques centaines d'euros dépensés sur les deux ou
     trois premiers du classement.</p>
  <p>Les Local Service Ads sont un angle mort : elles se facturent au lead et
     n'apparaissent ni dans le Keyword Planner ni dans l'API Google Ads.</p>
</div>
</div><script>{js}</script></body></html>""".format(
        css=_CSS, js=_JS, metier=_e(metier.libelle),
        conv=hypotheses.taux_conversion, prix=hypotheses.prix_revente_lead_eur,
        part=hypotheses.part_clics_captee, minart=hypotheses.min_artisans,
        seuil=hypotheses.marge_mensuelle_minimale_eur, avert=avert,
        date=date.strftime("%d/%m/%Y"),
        cartes="".join('<div class="carte"><div class="v">{}</div>'
                       '<div class="l">{}</div></div>'.format(_e(v), _e(l))
                       for v, l in cartes),
        puces="".join('<button class="puce" data-filtre="{}" aria-pressed="{}">{}'
                      '<span class="n">{}</span></button>'.format(
                          _e(c), "true" if c == "tous" else "false", _e(lib), n)
                      for c, lib, n in puces),
        entetes="".join('<th data-cle="{}" class="{}">{}<span class="fl"></span></th>'
                        .format(_e(cle), cls, _e(lib)) for cle, lib, cls in colonnes),
        rangs="".join(rangs))
