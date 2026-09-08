# -*- coding: utf-8 -*-
"""Client Google Ads pour la planification de mots-clés (API v25).

⚠️ NON VALIDÉ CONTRE L'API RÉELLE. Ce module est écrit d'après les exemples
officiels du dépôt googleads/google-ads-python et la documentation v25, mais il
n'a pas pu être exécuté : il exige un developer token de niveau Basic Access,
en attente d'approbation. Le premier appel réel peut donc révéler des écarts.
`verifier()` est là pour ça — le lancer avant tout balayage complet.

Trois méthodes du KeywordPlanIdeaService, à ne pas confondre :

- `GenerateKeywordHistoricalMetrics` — métriques d'une liste *fermée* de
  mots-clés, avec le volume mois par mois. C'est ce qu'il faut pour la fiche de
  closing : on connaît déjà les mots-clés.
- `GenerateKeywordIdeas` — *découverte* de mots-clés à partir de semences.
  C'est ce qu'il faut pour le radar, quand on cherche ce qu'on ne connaît pas.
- `GenerateKeywordForecastMetrics` — prévision de clics/coût pour un budget et
  une enchère donnés. Le CPC qui en sort est en grande partie une conséquence de
  l'enchère fournie en entrée : ce n'est pas une mesure du marché.
"""

import os
from typing import Dict, List, NamedTuple, Optional

VERSION_API = os.environ.get("GOOGLE_ADS_API_VERSION", "v25")

# Identifiant de langue « French ». Voir
# https://developers.google.com/google-ads/api/data/codes-formats#languages
LANGUE_FRANCAIS = "1002"

MICROS = 1_000_000

# MonthOfYearEnum commence à JANUARY = 2 (0 et 1 sont UNSPECIFIED et UNKNOWN).
# On passe par le nom plutôt que par la valeur, qui est un piège classique.
_MOIS = {"JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4, "MAY": 5, "JUNE": 6,
         "JULY": 7, "AUGUST": 8, "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11,
         "DECEMBER": 12}


class ErreurGoogleAds(RuntimeError):
    pass


class VolumeMensuel(NamedTuple):
    annee: int
    mois: int
    volume: int


class MetriquesMotCle(NamedTuple):
    mot_cle: str
    volume_mensuel_moyen: int
    concurrence: str                                  # LOW / MEDIUM / HIGH / UNKNOWN
    concurrence_indice: Optional[int]                 # 0-100
    # Enchères recommandées haut de page (20e / 80e percentile). CE NE SONT PAS
    # DES CPC : Google recommande une enchère, il ne facture pas ce montant.
    enchere_haut_page_basse_eur: Optional[float]
    enchere_haut_page_haute_eur: Optional[float]
    volumes_mensuels: List[VolumeMensuel]


class Prevision(NamedTuple):
    """Sortie de GenerateKeywordForecastMetrics — conditionnelle aux entrées."""
    impressions: float
    clics: float
    cout_eur: float
    cpc_moyen_eur: Optional[float]
    hypotheses: str


def _euros(micros: Optional[int]) -> Optional[float]:
    return round(micros / MICROS, 2) if micros else None


class ClientGoogleAds:
    def __init__(self, chemin_config: Optional[str] = None,
                 customer_id: Optional[str] = None,
                 version: str = VERSION_API):
        try:
            from google.ads.googleads.client import GoogleAdsClient
        except ImportError as err:
            raise ErreurGoogleAds(
                "Bibliothèque absente : pip install google-ads==31.4.1"
            ) from err

        chemin = chemin_config or os.environ.get(
            "GOOGLE_ADS_CONFIGURATION_FILE_PATH", "google-ads.yaml")
        if not os.path.exists(chemin):
            raise ErreurGoogleAds(
                "Configuration introuvable : {}. Copie google-ads.yaml.example "
                "et renseigne developer_token, client_id, client_secret, "
                "refresh_token et login_customer_id.".format(chemin))

        self.version = version
        self.client = GoogleAdsClient.load_from_storage(path=chemin, version=version)
        self.customer_id = (customer_id
                            or os.environ.get("GOOGLE_ADS_CUSTOMER_ID", "")).replace("-", "")
        if not self.customer_id:
            raise ErreurGoogleAds(
                "customer_id manquant : export GOOGLE_ADS_CUSTOMER_ID=1234567890 "
                "(le compte qui a de l'historique de dépense, pas le MCC).")
        self._service = self.client.get_service("KeywordPlanIdeaService")
        self._ads = self.client.get_service("GoogleAdsService")

    # -- métriques historiques (fiche de closing) --------------------------

    def metriques_historiques(self, mots_cles: List[str],
                              geo_target: str) -> List[MetriquesMotCle]:
        """Volumes et enchères d'une liste fermée de mots-clés sur une zone.

        `geo_target` : resource name, ex. "geoTargetConstants/9040828".
        Un seul appel par zone, quel que soit le nombre de mots-clés.
        """
        requete = self.client.get_type("GenerateKeywordHistoricalMetricsRequest")
        requete.customer_id = self.customer_id
        requete.keywords.extend(mots_cles)
        requete.geo_target_constants.append(geo_target)
        requete.language = self._ads.language_constant_path(LANGUE_FRANCAIS)
        # Search uniquement : inclure le Display polluerait les estimations.
        requete.keyword_plan_network = (
            self.client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH)

        reponse = self._appeler(
            lambda: self._service.generate_keyword_historical_metrics(request=requete))
        return [self._convertir(r.text, r.keyword_metrics) for r in reponse.results]

    # -- découverte de mots-clés (radar) -----------------------------------

    def idees_mots_cles(self, racines: List[str], geo_target: str,
                        limite: int = 500) -> List[MetriquesMotCle]:
        """Étend des semences en idées de mots-clés, avec leurs métriques."""
        requete = self.client.get_type("GenerateKeywordIdeasRequest")
        requete.customer_id = self.customer_id
        requete.language = self._ads.language_constant_path(LANGUE_FRANCAIS)
        requete.geo_target_constants.append(geo_target)
        requete.include_adult_keywords = False
        requete.keyword_plan_network = (
            self.client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH)
        requete.keyword_seed.keywords.extend(racines)

        reponse = self._appeler(
            lambda: self._service.generate_keyword_ideas(request=requete))
        resultats = []
        for i, idee in enumerate(reponse):
            if i >= limite:
                break
            resultats.append(self._convertir(idee.text, idee.keyword_idea_metrics))
        return resultats

    # -- prévision (à manier avec précaution) ------------------------------

    def prevision(self, mots_cles: List[str], geo_target: str,
                  enchere_max_eur: float = 8.0) -> Prevision:
        """Prévision de campagne. Le CPC obtenu dépend des entrées ci-dessus.

        À ne jamais présenter comme un « CPC du marché » : c'est la réponse à la
        question « que se passerait-il si j'enchérissais X avec un budget Y ».
        """
        campagne = self.client.get_type("CampaignToForecast")
        campagne.bidding_strategy.manual_cpc_bidding_strategy.max_cpc_bid_micros = int(
            enchere_max_eur * MICROS)
        campagne.geo_target_constants.append(geo_target)
        campagne.language_constants.append(
            self._ads.language_constant_path(LANGUE_FRANCAIS))
        # Search uniquement. Le champ n'existe pas sur toutes les versions
        # de CampaignToForecast : on ne le force que s'il est présent.
        try:
            campagne.keyword_plan_network = (
                self.client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH)
        except AttributeError:
            pass

        groupe = self.client.get_type("ForecastAdGroup")
        for texte in mots_cles:
            mot_cle = self.client.get_type("KeywordInfo")
            mot_cle.text = texte
            mot_cle.match_type = self.client.enums.KeywordMatchTypeEnum.PHRASE
            groupe.keywords.append(mot_cle)
        campagne.ad_groups.append(groupe)

        requete = self.client.get_type("GenerateKeywordForecastMetricsRequest")
        requete.customer_id = self.customer_id
        requete.campaign = campagne

        reponse = self._appeler(
            lambda: self._service.generate_keyword_forecast_metrics(request=requete))
        m = reponse.campaign_forecast_metrics
        cout = _euros(m.cost_micros) or 0.0
        return Prevision(
            impressions=m.impressions, clics=m.clicks, cout_eur=cout,
            cpc_moyen_eur=_euros(getattr(m, "average_cpc_micros", None))
            or (round(cout / m.clicks, 2) if m.clicks else None),
            # Le budget n'est pas un paramètre de GenerateKeywordForecastMetrics :
            # ne pas le mentionner ici reviendrait à inventer une hypothèse.
            hypotheses="enchère max {:.2f} € en CPC manuel, réseau Search, "
                       "correspondance d'expression".format(enchere_max_eur),
        )

    # -- utilitaires -------------------------------------------------------

    def _convertir(self, texte: str, m) -> MetriquesMotCle:
        volumes = []
        for v in getattr(m, "monthly_search_volumes", []) or []:
            mois = _MOIS.get(getattr(v.month, "name", str(v.month)))
            if mois:
                volumes.append(VolumeMensuel(int(v.year), mois, int(v.monthly_searches)))
        volumes.sort(key=lambda x: (x.annee, x.mois))
        return MetriquesMotCle(
            mot_cle=texte,
            volume_mensuel_moyen=int(getattr(m, "avg_monthly_searches", 0) or 0),
            concurrence=getattr(m.competition, "name", str(m.competition)),
            concurrence_indice=(int(m.competition_index)
                                if getattr(m, "competition_index", None) else None),
            enchere_haut_page_basse_eur=_euros(
                getattr(m, "low_top_of_page_bid_micros", None)),
            enchere_haut_page_haute_eur=_euros(
                getattr(m, "high_top_of_page_bid_micros", None)),
            volumes_mensuels=volumes,
        )

    def _appeler(self, action):
        try:
            from google.ads.googleads.errors import GoogleAdsException
        except ImportError:  # pragma: no cover
            return action()
        try:
            return action()
        except GoogleAdsException as err:
            details = []
            for erreur in err.failure.errors:
                details.append("{} : {}".format(
                    erreur.error_code, erreur.message))
                if "DEVELOPER_TOKEN" in str(erreur.error_code):
                    details.append(
                        "→ Le niveau Explorer bloque KeywordPlanIdeaService. "
                        "Il faut Basic Access avec le permissible use "
                        "« Researching keywords and recommendations ».")
            raise ErreurGoogleAds("\n".join(details) or str(err))

    def verifier(self, geo_target: str) -> Dict[str, object]:
        """Contrôle minimal : l'auth passe et les données ne sont pas vides.

        Un compte sans historique de dépense renvoie des volumes très arrondis,
        voire nuls. Ce contrôle le rend visible avant tout balayage.
        """
        metriques = self.metriques_historiques(["couvreur", "devis toiture"], geo_target)
        volumes = [m.volume_mensuel_moyen for m in metriques]
        mois = max((len(m.volumes_mensuels) for m in metriques), default=0)
        return {
            "version_api": self.version,
            "mots_cles_repondus": len(metriques),
            "volumes": volumes,
            "mois_historises": mois,
            "donnees_exploitables": bool(volumes) and max(volumes or [0]) > 0 and mois >= 10,
        }
