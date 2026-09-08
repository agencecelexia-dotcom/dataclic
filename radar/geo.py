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

CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "geotargets_raw.csv",
)


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

    Lève une erreur si le compte n'est pas exactement 96 : cela signifierait que
    Google a modifié sa nomenclature et que le reste du pipeline est à revalider.
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

    return [trouves[code] for code in sorted(trouves, key=_ordre_departement)]


def _ordre_departement(code: str) -> tuple:
    """Ordre administratif français : ... 19, 2A, 2B, 21 ... et non 29, 2A, 2B."""
    if code in ("2A", "2B"):
        return (20, code)
    return (int(code), "")
