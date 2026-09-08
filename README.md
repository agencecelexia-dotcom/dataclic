# Radar d'opportunité Google Ads — marché artisans FR

Outil interne Celexia. Cartographie, département par département, le potentiel
d'acquisition Google Ads d'un métier artisanal, croisé avec la densité
d'entreprises concurrentes (INSEE) et l'intention de recherche.

Deux sorties : un **classement des 96 départements** pour savoir où ouvrir des
campagnes, et une **fiche de marché** à présenter en call de closing.

## Démarrer

Aucun accès n'est nécessaire pour voir tourner l'outil : `--demo` fabrique des
données synthétiques plausibles.

```bash
./radar.py classement --demo --ouvrir     # classement + tableau de bord HTML
./radar.py fiche 31 --demo --ouvrir       # fiche de marché d'un département
./radar.py motscles                       # intentions et mots-clés à exclure
./radar.py verifier                       # état des accès
./radar.py --help
```

| Commande | Rôle | Accès requis |
|---|---|---|
| `classement` | classe les 96 départements, CSV + tableau de bord HTML | Google Ads + INSEE |
| `fiche <dép>` | fiche de marché HTML pour un call | Google Ads + INSEE |
| `motscles` | intentions, poids, mots-clés à exclure | aucun |
| `artisans` | recensement INSEE par département | clé INSEE |
| `verifier` | diagnostic des accès | aucun |
| `site` | serveur web local | aucun |

Les sorties vont dans `out/`. Le tableau de bord et la fiche sont des fichiers
HTML **autonomes** : aucune ressource externe, graphiques en SVG inline, tri et
filtres en JavaScript inline. Ils s'ouvrent hors ligne, survivent à un envoi par
mail et s'impriment en PDF depuis le navigateur.

## Le site

```bash
pip install -r requirements.txt
./radar.py site                              # http://127.0.0.1:5000
RADAR_MOT_DE_PASSE=... ./radar.py site
```

Trois pages : choix du département (grille des 96, groupés par région, filtre
instantané), fiche de marché, classement. Les rendus sont ceux de
`radar/fiche.py` et `radar/tableau.py` — le site ne réimplémente rien, il ajoute
une navigation et un routage.

### Déploiement Vercel

`app.py` à la racine expose l'application WSGI ; Vercel le détecte
automatiquement, sans `vercel.json`. Variables d'environnement à définir dans le
projet Vercel :

| Variable | Rôle |
|---|---|
| `RADAR_MOT_DE_PASSE` | **obligatoire en ligne.** Authentification HTTP Basic |
| `INSEE_API_KEY` | bascule le site en données réelles |
| `GOOGLE_ADS_CUSTOMER_ID` | idem |
| `RADAR_TTL_CACHE` | durée du cache en secondes (défaut 3600) |
| `RADAR_FORCER_DEMO` | force le mode démonstration |

Sans `INSEE_API_KEY` **et** `google-ads.yaml`, le site tourne en mode
démonstration et l'affiche dans un bandeau sur chaque page : les chiffres sont
synthétiques et ne doivent pas être montrés à un artisan.

**Deux limites à connaître :**

- **Le cache est en mémoire.** Chaque instance serverless froide repart d'un
  cache vide. Il amortit les rechargements d'une même session, pas du trafic.
  Sans persistance — écartée à dessein — c'est le maximum possible.
- **`requirements.txt` ne contient que Flask.** Le paquet `google-ads` embarque
  le code généré des versions d'API v21 à v25 et pèse plusieurs centaines de
  mégaoctets décompressé, au-delà de la limite de taille d'une fonction
  serverless. Il est isolé dans `requirements-collecte.txt`, pour la ligne de
  commande. **La collecte de données réelles se fait donc en local, pas sur
  Vercel** ; le site sert ce que la collecte a produit.

## Ce que le scoring encode

Dans [radar/scoring.py](radar/scoring.py) :

- **Un CPC bas n'est jamais récompensé en soi.** Le score regarde la marge par
  lead (prix de revente − CPC ÷ taux de conversion), jamais le CPC seul.
- **Volume et vivier saturent** (racine carrée bornée). Sans cela le classement
  se réduirait au classement démographique des départements : ×8 de volume et
  ×7,5 de vivier n'apportent que +19 % de score.
- **Quatre verdicts éliminatoires** priment sur le score : `vivier_insuffisant`
  (personne pour absorber les leads), `marge_insuffisante`, `marche_trop_petit`
  (la marge mensuelle absolue ne paie pas le coût d'ouverture d'une campagne),
  `donnees_absentes` (aucune valeur n'est jamais devinée).

```bash
python3 scripts/verifier_scoring.py    # 9 cas construits, règles métier
```

Ces cas testent des convictions métier, pas du code. Si l'un tombe après un
réglage des pondérations, c'est le réglage qu'il faut revoir, pas le test.

### Le classement dépend d'hypothèses non mesurées

```bash
./radar.py classement --demo --sensibilite
```

Selon le taux de conversion et le prix de revente retenus, le nombre de
départements éligibles va de **0 à 91 sur 96**, et la tête du classement change
complètement. Le moteur est bon, les entrées ne le sont pas encore. Deux chiffres
à mesurer avant d'exploiter une sortie : le **taux de conversion réel** de la
landing page, et le **prix de revente réel** d'un lead.

## Accès

```bash
export INSEE_API_KEY=...
export GOOGLE_ADS_CUSTOMER_ID=1234567890
cp google-ads.yaml.example google-ads.yaml   # puis remplir
./radar.py verifier
```

**Google Ads API v25** (`google-ads` 31.4.1). Le developer token doit être au
niveau **Basic Access** avec le permissible use *« Researching keywords and
recommendations »* : le niveau Explorer bloque `KeywordPlanIdeaService` et
`KeywordPlanService` côté serveur, quel que soit le code. Le token s'obtient
uniquement depuis l'API Center d'un compte manager : <https://ads.google.com/aw/apicenter>.

**API Sirene INSEE** sur <https://portail-api.insee.fr>. L'ancien portail
`api.insee.fr` en OAuth a fermé en septembre 2025 : consumer key et secret ne
fonctionnent plus. La nouvelle authentification passe par une clé statique dans
l'en-tête `X-INSEE-Api-Key-Integration`, limitée à 30 requêtes/minute.

```bash
./radar.py artisans --verifier   # contrôle en 4 requêtes, avant tout balayage
```

Deux points du client Sirene n'ont pas pu être validés sans clé et c'est ce que
ce contrôle vérifie : le filtre départemental `codeCommuneEtablissement:XX*` et
le cas de la Corse (codes commune `2A###` / `2B###`). Si l'un des deux échoue, un
balayage complet produirait des comptages faux **sans lever d'erreur**.

## Pièges de lecture des données

- **Les fourchettes d'enchères haut de page ne sont pas des CPC.** Ce sont des
  enchères recommandées (20ᵉ et 80ᵉ percentile). Les champs sont nommés
  explicitement partout dans le code.
- **`GenerateKeywordForecastMetrics` ne mesure pas le marché.** On lui fournit une
  enchère max ; le CPC qui en ressort en est en grande partie la conséquence.
  C'est une simulation conditionnelle, pas une observation.
- **Google plancher-arrondit les petits volumes.** Sur une longue traîne dans un
  département rural, on obtient 0 par artefact statistique, pas par absence de
  demande. Le niveau géographique utilisé est tracé dans toutes les sorties.
- **Les Local Service Ads sont un angle mort.** Elles se facturent au lead et
  leurs prix n'apparaissent ni dans le Keyword Planner ni dans l'API Google Ads.
- **Google type deux arrondissements comme « Department »** dans son CSV de geo
  targets (Lyon, Palaiseau). Ils sont filtrés dans `radar/insee_departements.py`
  pour éviter des doublons silencieux dans le classement. Restent 96 départements
  métropolitains, aucun DOM.
- **43.91A n'est pas le code du couvreur.** 43.91A = « Travaux de charpente »,
  **43.91B** = « Travaux de couverture par éléments ». Le métier `couverture`
  compte les deux, beaucoup d'artisans exerçant les deux sous une seule
  immatriculation. À anticiper : la nomenclature **NAF 2025 (rév. 2.1)** entre en
  vigueur au 1ᵉʳ janvier 2027 et 43.91B y devient **4341H**, avec un redéploiement
  progressif des codes APE dès 2026.
- **L'API Sirene renvoie un 404, pas une liste vide,** quand une requête ne matche
  rien. Un département sans artisan est un 0 légitime, pas une erreur.
- **`activitePrincipaleEtablissement` et `etatAdministratifEtablissement` sont
  historisées.** Interrogées hors de `periode(...)`, elles matchent aussi les
  valeurs passées : on compterait des établissements fermés ou qui ont changé
  d'activité. Toutes les requêtes du client sont enveloppées dans `periode(...)`.
- **Les poids d'intention et les paramètres de scoring sont des hypothèses**, pas
  des mesures. Ils sont centralisés dans `radar/intention.py` et
  `radar/scoring.Hypotheses`, à recaler sur les chiffres réels.
- **Afficher ou non le coût par lead sur la fiche est un arbitrage commercial.**
  Le montrer prouve que l'acquisition coûte cher ; mais il ancre l'artisan sur le
  prix d'acquisition, ce qui peut jouer contre le prix de revente du lead.
  `./radar.py fiche 31 --demo --sans-cout` génère l'autre version.

## Architecture

```
radar.py                    point d'entrée ligne de commande
app.py                      point d'entrée WSGI (détecté par Vercel)
radar/
  web.py                    application Flask : routage, cache, mot de passe
  geo.py                    96 départements ↔ geo targets Google
  insee_departements.py     table de référence INSEE (figée)
  metiers.py                config par métier : mots-clés, codes NAF
  intention.py              classification des mots-clés, mots-clés négatifs
  google_ads.py             client API v25  ⚠ non validé contre l'API réelle
  insee.py                  client Sirene v3.11
  pipeline.py               collecte : relie Google Ads, INSEE et scoring
  scoring.py                classement des départements
  fiche.py                  fiche de marché HTML
  tableau.py                tableau de bord HTML
  demo.py                   données synthétiques
scripts/verifier_scoring.py règles métier du scoring
```

Chaque module est indépendant et testable séparément ; `pipeline.py` est la seule
couche qui connaît les deux sources à la fois.

**Pas de persistance.** L'outil écrit des CSV et du HTML, rien d'autre. Pas de
base, pas de service, pas d'historique : c'est un outil qu'on lance, pas une
infrastructure à maintenir.

## État

| Brique | État |
|---|---|
| Référentiel des 96 départements | fait, testé |
| Classification d'intention + mots-clés négatifs | fait, testé |
| Scoring et classement | fait, 9 règles métier vérifiées |
| Fiche de closing HTML | faite |
| Tableau de bord HTML | fait |
| Client Sirene INSEE | écrit, à valider avec la clé (`artisans --verifier`) |
| Site web + déploiement Vercel | fait |
| Client Google Ads | écrit, **non validé** — en attente de Basic Access |

## Environnement

Python 3.9 minimum. `google-ads` 31.4.1 accepte `>=3.9` mais émet un
`DeprecationWarning` en dessous de 3.11 ; migration recommandée. Le socle
(géo, intention, scoring, rendus HTML) n'a aucune dépendance externe.
