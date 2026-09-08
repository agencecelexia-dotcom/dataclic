"""Classification des mots-clés par intention de recherche.

Tout le volume ne se vaut pas : « couvreur urgence fuite » est un lead chaud,
« prix réfection toiture » de la documentation, « formation couvreur » du bruit.
Seul le volume à forte intention transactionnelle doit peser dans le scoring.

Chaque intention porte un `poids` dans [0, 1] appliqué au volume de recherche
pour produire un *volume transactionnel pondéré*. Les poids sont des hypothèses
métier assumées, pas des mesures : ils sont regroupés ici pour être discutés et
ajustés à un seul endroit, et ils devront être recalés sur tes taux de
conversion réels dès que tu auras assez de données.
"""

import re
from typing import Dict, List, NamedTuple, Optional, Tuple

from .texte import normalise


class Intention(NamedTuple):
    cle: str
    libelle: str
    poids: float
    negatif: bool  # à verser dans la liste de mots-clés à exclure


URGENCE = Intention("urgence", "Urgence / dépannage", 1.00, False)
DEVIS = Intention("devis", "Demande de devis / recherche de pro", 1.00, False)
PRIX = Intention("prix", "Recherche de prix / budget", 0.35, False)
INFORMATION = Intention("information", "Information / documentation", 0.05, False)
DIY = Intention("diy", "Faire soi-même", 0.00, True)
EMPLOI = Intention("emploi_formation", "Emploi / formation / métier", 0.00, True)
GENERIQUE = Intention("generique", "Générique métier (intention mixte)", 0.55, False)

INTENTIONS = [URGENCE, DEVIS, PRIX, INFORMATION, DIY, EMPLOI, GENERIQUE]

# L'ordre compte : première règle qui matche, elle gagne. Les intentions
# disqualifiantes (emploi, DIY) passent avant les autres, sinon « formation
# devis couvreur » serait compté comme une demande de devis.
REGLES: List[Tuple[Intention, List[str]]] = [
    (EMPLOI, [
        r"\bemploi\b", r"\boffre[s]? d emploi\b", r"\brecrutement\b", r"\brecrute\b",
        r"\bformation[s]?\b", r"\bse former\b", # Diplômes : ancrés en début de requête. « cap couvreur » est une
        # recherche de formation, « couvreur cap ferret » une recherche locale.
        r"^(cap|bep|bp|bts|bac pro)\b", r"\bdiplome\b",
        r"\balternance\b", r"\bapprenti(ssage)?\b", r"\bstage\b",
        r"\bsalaire\b", r"\bremuneration\b", r"\bfiche metier\b", r"\bmetier de\b",
        r"\bdevenir\b", r"\bauto ?entrepreneur\b", r"\bmicro entreprise\b",
        r"\bstatut\b", r"\bconvention collective\b", r"\bcode ape\b", r"\bcode naf\b",
        r"\bassurance decennale\b", r"\bkbis\b", r"\bsiret\b",
        r"\boutillage\b", r"\bmateriel\b", r"\bfournisseur\b", r"\bgrossiste\b",
        r"\blogiciel\b", r"\bcv\b", r"\bpole emploi\b", r"\bfrance travail\b",
    ]),
    (DIY, [
        r"\bcomment\b", r"\bsoi meme\b", r"\bsoi-meme\b", r"\bdiy\b",
        r"\btuto(riel)?\b", r"\bvideo\b", r"\betape[s]? par etape\b",
        r"\bbricolage\b", r"\bleroy merlin\b", r"\bcastorama\b", r"\bbrico ?depot\b",
        r"\bpoint p\b", r"\bfabriquer\b", r"\bconstruire soi\b",
    ]),
    (URGENCE, [
        r"\burgence\b", r"\burgent\b", r"\bdepannage\b", r"\bdepanneur\b",
        r"\ben urgence\b", r"\b24h\b", r"\b24 24\b", r"\bnuit\b", r"\bweek ?end\b",
        r"\bfuite\b", r"\binfiltration\b", r"\bdegat des eaux\b", r"\bsinistre\b",
        r"\btempete\b", r"\bintemperies\b", r"\bcasse\b", r"\bs affaisse\b",
        r"\bbache\b", r"\bmise hors d eau\b", r"\brapide(ment)?\b", r"\bimmediat\b",
        r"\bintervention\b", r"\baujourd hui\b",
    ]),
    (DEVIS, [
        r"\bdevis\b", r"\bestimation\b", r"\bchiffrage\b", r"\bdemande de devis\b",
        r"\bartisan\b", r"\bentreprise\b", r"\bsociete\b", r"\bprofessionnel\b",
        r"\bpro\b", r"\bpres de (chez )?moi\b", r"\ba proximite\b", r"\bautour de moi\b",
        r"\bmeilleur\b", r"\bavis\b", r"\bcomparer\b", r"\bcomparatif\b",
        r"\bcontacter\b", r"\btelephone\b", r"\bnumero\b", r"\brdv\b",
        r"\brendez ?vous\b", r"\brecommande\b", r"\bqualifie\b", r"\brge\b",
    ]),
    (PRIX, [
        r"\bprix\b", r"\btarif[s]?\b", r"\bcout\b", r"\bcombien\b", r"\bbudget\b",
        r"\bm2\b", r"\bau metre carre\b", r"\bpas cher\b", r"\bmoins cher\b",
        r"\beconomique\b", r"\bsubvention\b", r"\baide[s]?\b", r"\bprime\b",
        r"\bcredit d impot\b", r"\bma prime renov\b", r"\bfinancement\b",
    ]),
    (INFORMATION, [
        r"\bdefinition\b", r"\bc est quoi\b", r"\bqu est ce que\b", r"\bsignification\b",
        r"\bnorme[s]?\b", r"\bdtu\b", r"\breglementation\b", r"\bloi\b", r"\bpermis\b",
        r"\bdeclaration prealable\b", r"\bduree de vie\b", r"\bavantage[s]?\b",
        r"\binconvenient[s]?\b", r"\bdifference\b", r"\btype[s]? de\b", r"\bmodele[s]?\b",
        r"\bschema\b", r"\bplan\b", r"\bforum\b", r"\bwikipedia\b", r"\bhistoire\b",
    ]),
]

_REGLES_COMPILEES = [
    (intention, [re.compile(m) for m in motifs]) for intention, motifs in REGLES
]


class Classification(NamedTuple):
    intention: Intention
    motif: Optional[str]  # le motif déclencheur, pour pouvoir auditer une décision

    @property
    def poids(self) -> float:
        return self.intention.poids


def classer(mot_cle: str) -> Classification:
    """Classe un mot-clé par intention. Première règle qui matche, elle gagne."""
    texte = normalise(mot_cle)
    for intention, motifs in _REGLES_COMPILEES:
        for motif in motifs:
            if motif.search(texte):
                return Classification(intention, motif.pattern)
    return Classification(GENERIQUE, None)


def volume_transactionnel(mot_cle: str, volume: float) -> float:
    """Volume de recherche pondéré par l'intention. C'est cette valeur qui alimente le scoring."""
    return volume * classer(mot_cle).poids


def mots_cles_negatifs(mots_cles: List[str]) -> Dict[str, List[str]]:
    """Extrait de la liste les mots-clés à exclure, groupés par intention.

    Sortie directement exploitable comme liste de mots-clés à exclure de campagne.
    """
    negatifs: Dict[str, List[str]] = {}
    for mot_cle in mots_cles:
        c = classer(mot_cle)
        if c.intention.negatif:
            negatifs.setdefault(c.intention.cle, []).append(mot_cle)
    return negatifs
