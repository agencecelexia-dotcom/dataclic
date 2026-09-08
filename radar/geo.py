"""Chargement des geo target constants Google Ads pour les départements français.

Google publie un CSV de tous ses geo targets. On en extrait les départements
métropolitains et on les rattache à leur code INSEE, ce qui permet ensuite de
joindre les données Google Ads avec celles de l'INSEE (densité d'artisans).
"""

import csv
import io
import os
from typing import Dict, List, NamedTuple, Optional

from .insee_departements import DEPARTEMENTS, FAUX_DEPARTEMENTS
from .texte import normalise as _normalise

# Page de référence : https://developers.google.com/google-ads/api/data/geotargets
# Google republie ce fichier sous un nouveau nom daté à chaque mise à jour ;
# la date est donc surchargeable sans toucher au code.
GEOTARGETS_URL = os.environ.get(
    "GEOTARGETS_URL",
    "https://developers.google.com/static/google-ads/api/data/geo/geotargets-2026-08-12.csv",
)

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Cache du CSV brut de Google : 23 Mo, non versionné, re-téléchargeable.
CACHE_PATH = os.path.join(_RACINE, "data", "geotargets_raw.csv")

# Référentiel dérivé : 96 lignes, quelques kilo-octets, versionné. C'est lui que
# lit l'outil au quotidien. Le CSV brut n'est nécessaire que pour le régénérer,
# ce qui évite un téléchargement de 23 Mo au démarrage — impossible en
# environnement serverless, dont le système de fichiers est en lecture seule.
REFERENTIEL_PATH = os.path.join(_RACINE, "data", "departements_geotargets.csv")


class Departement(NamedTuple):
    code_insee: str          # "01", "2A", "75"...
    nom: str                 # nom officiel INSEE, accentué
    criteria_id: str         # geo target constant Google Ads, ex "9040847"
    region: str              # tel que Google le nomme (non normalisé INSEE)

    @property
    def geo_target_resource_name(self) -> str:
        """Resource name attendu par l'API Google Ads."""
        return "geoTargetConstants/{}".format(self.criteria_id)


def telecharger_geotargets(force: bool = False) -> str:
    """Télécharge le CSV des geo targets (23 Mo) et le met en cache sur disque."""
    if os.path.exists(CACHE_PATH) and not force:
        return CACHE_PATH
    import urllib.request

    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with urllib.request.urlopen(GEOTARGETS_URL, timeout=120) as resp:
        contenu = resp.read()
    with open(CACHE_PATH, "wb") as f:
        f.write(contenu)
    return CACHE_PATH


def charger_departements(chemin: Optional[str] = None) -> List[Departement]:
    """Renvoie les 96 départements métropolitains avec leur geo target Google.

    Lit le référentiel dérivé versionné. S'il est absent, le reconstruit depuis
    le CSV brut de Google, qu'il télécharge au besoin.
    """
    if chemin is None and os.path.exists(REFERENTIEL_PATH):
        return _lire_referentiel()
    return regenerer(chemin)


def _lire_referentiel() -> List[Departement]:
    with io.open(REFERENTIEL_PATH, newline="", encoding="utf-8") as f:
        departements = [Departement(l["code_insee"], l["nom"], l["criteria_id"],
                                    l["region"])
                        for l in csv.DictReader(f)]
    if len(departements) != len(DEPARTEMENTS):
        raise RuntimeError(
            "Référentiel corrompu : {} lignes au lieu de {}. "
            "Régénérer avec radar.geo.regenerer().".format(
                len(departements), len(DEPARTEMENTS)))
    return departements


def regenerer(chemin: Optional[str] = None, ecrire: bool = True) -> List[Departement]:
    """Reconstruit le référentiel depuis le CSV brut de Google.

    Lève une erreur si le compte n'est pas exactement 96 : cela signifierait que
    Google a modifié sa nomenclature et que le reste du pipeline est à revalider.
    À relancer quand Google publie un nouveau CSV daté (voir GEOTARGETS_URL).
    """
    chemin = chemin or telecharger_geotargets()

    par_nom_normalise = {_normalise(nom): code for code, nom in DEPARTEMENTS.items()}
    trouves: Dict[str, Departement] = {}
    inconnus: List[str] = []

    with io.open(chemin, newline="", encoding="utf-8") as f:
        for ligne in csv.DictReader(f):
            if ligne["Country Code"] != "FR":
                continue
            if ligne["Target Type"] != "Department" or ligne["Status"] != "Active":
                continue
            if ligne["Criteria ID"] in FAUX_DEPARTEMENTS:
                continue

            code = par_nom_normalise.get(_normalise(ligne["Name"]))
            if code is None:
                inconnus.append(ligne["Name"])
                continue

            morceaux = ligne["Canonical Name"].split(",")
            trouves[code] = Departement(
                code_insee=code,
                nom=DEPARTEMENTS[code],
                criteria_id=ligne["Criteria ID"],
                region=morceaux[1].strip() if len(morceaux) > 1 else "",
            )

    if inconnus:
        raise RuntimeError(
            "Départements Google non rattachés à un code INSEE : {}. "
            "Google a probablement modifié sa nomenclature.".format(inconnus)
        )
    manquants = sorted(set(DEPARTEMENTS) - set(trouves))
    if manquants:
        raise RuntimeError(
            "Départements INSEE absents du CSV Google : {}".format(manquants)
        )

    departements = [trouves[code] for code in sorted(trouves, key=_ordre_departement)]
    if ecrire:
        os.makedirs(os.path.dirname(REFERENTIEL_PATH), exist_ok=True)
        with io.open(REFERENTIEL_PATH, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["code_insee", "nom", "criteria_id", "region"])
            for d in departements:
                w.writerow([d.code_insee, d.nom, d.criteria_id, d.region])
    return departements


def _ordre_departement(code: str) -> tuple:
    """Ordre administratif français : ... 19, 2A, 2B, 21 ... et non 29, 2A, 2B."""
    if code in ("2A", "2B"):
        return (20, code)
    return (int(code), "")
