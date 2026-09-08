"""Comptage d'établissements actifs par département via l'API Sirene de l'INSEE.

Sert à mesurer le vivier d'artisans recrutables dans chaque département : générer
des demandes de devis là où l'on n'a personne pour les absorber ne vaut rien.

Accès
-----
Nouveau portail : https://portail-api.insee.fr (l'ancien api.insee.fr en OAuth a
fermé en septembre 2025 ; les consumer key/secret ne fonctionnent plus).
Authentification par clé statique dans l'en-tête `X-INSEE-Api-Key-Integration`,
à placer dans la variable d'environnement INSEE_API_KEY.

Stratégie de comptage
---------------------
On ne pagine pas. Une requête avec `nombre=1` renvoie un en-tête `header.total`
qui porte le compte complet : 96 requêtes suffisent pour toute la France, bien en
dessous du plafond de 30 requêtes/minute.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, NamedTuple, Optional

from .geo import Departement

BASE_URL = os.environ.get("INSEE_BASE_URL", "https://api.insee.fr/api-sirene/3.11")
EN_TETE_CLE = "X-INSEE-Api-Key-Integration"

# Plafond documenté : 30 requêtes/minute. On vise 25 pour garder de la marge.
INTERVALLE_MINIMAL_S = 60.0 / 25.0


class ErreurInsee(RuntimeError):
    pass


class CleManquante(ErreurInsee):
    pass


class ComptageDepartement(NamedTuple):
    code_insee: str
    nom: str
    nb_etablissements: int
    requete: str  # la requête Sirene exacte, pour pouvoir rejouer/auditer


def _prefixe_commune(code_departement: str) -> str:
    """Préfixe de code commune INSEE correspondant à un département.

    Les codes commune métropolitains sont sur 5 caractères et commencent par le
    code du département : 31555 = Toulouse (31), 2A004 = Ajaccio (2A).
    """
    return code_departement


class ClientSirene:
    def __init__(self, cle_api: Optional[str] = None, verbeux: bool = False):
        self.cle_api = cle_api or os.environ.get("INSEE_API_KEY")
        if not self.cle_api:
            raise CleManquante(
                "Clé API INSEE absente. Crée-la sur https://portail-api.insee.fr "
                "puis exporte-la : export INSEE_API_KEY=..."
            )
        self.verbeux = verbeux
        self._dernier_appel = 0.0

    # -- transport ---------------------------------------------------------

    def _attendre(self) -> None:
        ecoule = time.time() - self._dernier_appel
        if ecoule < INTERVALLE_MINIMAL_S:
            time.sleep(INTERVALLE_MINIMAL_S - ecoule)

    def _get(self, chemin: str, params: Dict[str, str], tentatives: int = 4) -> Optional[dict]:
        """Appelle l'API. Renvoie None si l'INSEE répond « aucun élément trouvé ».

        L'API Sirene renvoie un 404 — et non une liste vide — quand la requête ne
        matche rien. Un département sans aucun artisan du métier est un résultat
        valide à 0, pas une erreur : on le traduit ici.
        """
        url = "{}/{}?{}".format(BASE_URL, chemin.lstrip("/"), urllib.parse.urlencode(params))
        for tentative in range(tentatives):
            self._attendre()
            requete = urllib.request.Request(
                url, headers={EN_TETE_CLE: self.cle_api, "Accept": "application/json"}
            )
            try:
                with urllib.request.urlopen(requete, timeout=60) as reponse:
                    self._dernier_appel = time.time()
                    return json.loads(reponse.read().decode("utf-8"))
            except urllib.error.HTTPError as err:
                self._dernier_appel = time.time()
                corps = err.read().decode("utf-8", "replace")[:400]
                if err.code == 404:
                    return None
                if err.code == 429:
                    attente = 5 * (tentative + 1)
                    if self.verbeux:
                        print("  429 reçu, pause {} s".format(attente))
                    time.sleep(attente)
                    continue
                if err.code in (401, 403):
                    raise ErreurInsee(
                        "Authentification refusée ({}). Vérifie INSEE_API_KEY et que "
                        "l'API Sirene est bien souscrite sur ton compte portail-api.insee.fr.\n{}"
                        .format(err.code, corps)
                    )
                if err.code >= 500 and tentative < tentatives - 1:
                    time.sleep(3 * (tentative + 1))
                    continue
                raise ErreurInsee("HTTP {} sur {}\n{}".format(err.code, url, corps))
            except urllib.error.URLError as err:
                if tentative < tentatives - 1:
                    time.sleep(3 * (tentative + 1))
                    continue
                raise ErreurInsee("Erreur réseau sur {} : {}".format(url, err))
        raise ErreurInsee("Échec après {} tentatives : {}".format(tentatives, url))

    # -- requêtes ----------------------------------------------------------

    @staticmethod
    def construire_requete(codes_naf: List[str], code_departement: Optional[str] = None) -> str:
        """Construit la requête Sirene.

        `activitePrincipaleEtablissement` et `etatAdministratifEtablissement` sont
        des variables *historisées* : interrogées hors de `periode(...)`, elles
        matchent aussi les valeurs passées. On compterait alors des établissements
        qui ont été couvreurs il y a dix ans, ou qui sont fermés depuis. Le
        `periode(...)` restreint à la période en cours.
        """
        naf = " OR ".join("activitePrincipaleEtablissement:{}".format(c) for c in codes_naf)
        requete = "periode(({}) AND etatAdministratifEtablissement:A)".format(naf)
        if code_departement:
            requete += " AND codeCommuneEtablissement:{}*".format(
                _prefixe_commune(code_departement))
        return requete

    def compter(self, codes_naf: List[str], code_departement: Optional[str] = None) -> int:
        """Nombre d'établissements actifs pour ces codes NAF, éventuellement sur un département."""
        requete = self.construire_requete(codes_naf, code_departement)
        donnees = self._get("siret", {"q": requete, "nombre": "1", "champs": "siret"})
        if donnees is None:
            return 0
        return int(donnees["header"]["total"])

    def compter_par_departement(
        self, codes_naf: List[str], departements: List[Departement]
    ) -> List[ComptageDepartement]:
        """Boucle sur les départements. ~4 minutes pour la France entière."""
        resultats = []
        for i, dep in enumerate(departements, 1):
            requete = self.construire_requete(codes_naf, dep.code_insee)
            donnees = self._get("siret", {"q": requete, "nombre": "1", "champs": "siret"})
            total = 0 if donnees is None else int(donnees["header"]["total"])
            if self.verbeux:
                print("  [{:>2}/{}] {} {} : {}".format(
                    i, len(departements), dep.code_insee, dep.nom.ljust(24), total))
            resultats.append(ComptageDepartement(dep.code_insee, dep.nom, total, requete))
        return resultats

    # -- validation --------------------------------------------------------

    def verifier(self, codes_naf: List[str]) -> Dict[str, object]:
        """Contrôle de cohérence à lancer une fois, avant tout balayage complet.

        Vérifie trois choses qui n'ont pas pu être validées sans clé :
        1. l'authentification passe ;
        2. le filtre départemental par `codeCommuneEtablissement:XX*` fonctionne ;
        3. la somme de quelques départements est cohérente avec le total national.
        """
        national = self.compter(codes_naf)
        echantillon = {code: self.compter(codes_naf, code)
                       for code in ("75", "31", "59", "2A")}
        somme = sum(echantillon.values())
        return {
            "national": national,
            "echantillon": echantillon,
            "filtre_departemental_operant": 0 < somme < national,
            "corse_operante": echantillon["2A"] > 0,
        }
