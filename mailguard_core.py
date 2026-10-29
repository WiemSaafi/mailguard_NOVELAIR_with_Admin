"""
mailguard_core.py  (version 2 : nouveaux modèles)
=================================================
Pont entre l'application web et le moteur MailGuard (mailguard.py).

L'application garde EXACTEMENT les mêmes appels qu'avant :
    mg.analyser_email_complet(...)   mg.extraire_corps_html(...)   mg.extraire_liens(...)
    mg.analyser_domaine(...)         mg.analyser_domaine_bert(...) mg.etat_modeles()
    mg.SEUIL_DECISION  mg.POIDS  mg.POIDS_RAPIDE  mg.BASE_DIR  mg._MODELES  mg._recharger_si_absent()

Mais à l'intérieur, ce sont les NOUVEAUX modèles qui décident :
    S1 domaine          CANINE (lit les caractères)                     seuil 0,44
    S2 identité         Gradient Boosting + règle « < 30 jours »        seuil 0,74
    S3 liens            règles + signaux 1-2 + Gradient Boosting chemin seuil 0,894
    S4 contenu          multilingual-e5 + régression logistique         seuil 0,391
    S5 authentification Gradient Boosting (SPF/DKIM/DMARC) + veto Nouvelair
    Fusion              régression logistique (poids appris)            0,825 suspect · 0,928 frauduleux
    Cascade             liste noire → liste blanche authentifiée → règles sûres → score → raisons

Les anciens modèles (Sentence-BERT, forêt aléatoire, DistilBERT) ne sont plus chargés.

Les fichiers des modèles sont dans le dossier `modeles_mailguard/` (à côté de ce fichier) :
    modeles_mailguard/
      marques_protegees.csv  whitelist_propre.csv  blacklist_propre.csv
      modeles/CANINE/...                       (signal 1)
      modeles_signal2_v2.joblib  modeles_signal3_final.joblib  tranco_top1m.csv   (signaux 2 et 3)
      s4_modele_final/...                      (signal 4)
      s5_modele_final/...                      (signal 5)
      fusion_modele/fusion.joblib + parametres.json
L'encodeur e5 (≈ 1,1 Go) est téléchargé depuis Hugging Face au premier lancement, puis gardé en cache.
On peut aussi indiquer un dossier local avec la variable MAILGUARD_E5 dans le fichier .env.
"""

import os
import re
import threading
import time
from datetime import datetime
from urllib.parse import urlparse

from bs4 import BeautifulSoup

try:
    from langdetect import detect, DetectorFactory
    DetectorFactory.seed = 0
except Exception:          # langdetect est facultatif
    detect = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
try:                                   # lit MAILGUARD_MODELES / MAILGUARD_E5 dans le fichier .env
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"))
except Exception:
    pass
DOSSIER_MODELES = os.getenv("MAILGUARD_MODELES", os.path.join(BASE_DIR, "modeles_mailguard"))
E5 = os.getenv("MAILGUARD_E5", "intfloat/multilingual-e5-base")
INTERNET = os.getenv("MAILGUARD_INTERNET", "1") != "0"     # signal 2 : RDAP et crt.sh

# ---------------------------------------------------------------------
# Seuils (les valeurs réelles sont relues dans fusion_modele/parametres.json au chargement)
# ---------------------------------------------------------------------
SEUIL_SUSPECT = 0.825        # au plus 2 % de vrais mails accusés
SEUIL_FRAUDULEUX = 0.928     # au plus 0,5 % de vrais mails accusés
SEUIL_DECISION = SEUIL_FRAUDULEUX   # ancien nom : « score ≥ SEUIL_DECISION → frauduleux »

# Poids appris par la régression logistique de la fusion, regroupés par signal
# et ramenés à une somme de 1 (pour les écrans qui affichent l'importance des signaux).
_POIDS_APPRIS = {"authentification": 5.55, "contenu": 4.81,
                 "liens": 1.64 + 1.23 + 0.15 + 0.12,      # chemin, domaine du lien jeune, raccourcisseur, règle forte
                 "domaine_randomforest": 1.61,            # ancien nom gardé : c'est maintenant le signal 2 (identité)
                 "domaine_bert": 0.24}                    # ancien nom gardé : c'est maintenant CANINE (signal 1)
_total = sum(_POIDS_APPRIS.values())
POIDS = {k: round(v / _total, 3) for k, v in _POIDS_APPRIS.items()}
_t = sum(v for k, v in POIDS.items() if k != "domaine_randomforest")
POIDS_RAPIDE = {k: round(v / _t, 3) for k, v in POIDS.items() if k != "domaine_randomforest"}

NOMS_SIGNAUX = {"domaine_bert": "S1 · Domaine (CANINE)", "domaine_randomforest": "S2 · Identité du domaine",
                "liens": "S3 · Liens", "contenu": "S4 · Contenu (e5)", "authentification": "S5 · Authentification"}

# =====================================================================
# 1. CHARGEMENT UNIQUE DU MOTEUR (une seule fois pour tout le serveur)
# =====================================================================
_VERROU_MODELES = threading.Lock()
_MODELES = {}
_ERREUR_CHARGEMENT = None


def charger_modeles():
    """Charge le moteur MailGuard une seule fois (≈ 1 à 2 min sur processeur)."""
    global _ERREUR_CHARGEMENT, SEUIL_SUSPECT, SEUIL_FRAUDULEUX, SEUIL_DECISION
    if _MODELES:
        return _MODELES
    with _VERROU_MODELES:
        if _MODELES:
            return _MODELES
        if not os.path.isdir(DOSSIER_MODELES):
            raise FileNotFoundError(
                f"Dossier des modèles introuvable : {DOSSIER_MODELES}\n"
                "Copiez le dossier modeles_mailguard (téléchargé depuis le Drive) à la racine du projet.")
        import torch
        from mailguard import MailGuard
        depart = time.time()
        moteur = MailGuard(racine=DOSSIER_MODELES, internet=INTERNET, e5=E5)
        _SEUILS_APPRIS.update({"suspect": moteur.seuil_suspect, "frauduleux": moteur.seuil_fraude})
        _appliquer_config(moteur)
        SEUIL_SUSPECT, SEUIL_FRAUDULEUX = moteur.seuil_suspect, moteur.seuil_fraude
        SEUIL_DECISION = SEUIL_FRAUDULEUX
        _MODELES.update({
            "moteur": moteur,
            # anciens noms, gardés pour services/auth_service.py (ils ne sont plus des modèles BERT)
            "bert": moteur,
            "embeddings_confiance": True,
            "duree_chargement_s": round(time.time() - depart, 1),
            "charge_le": datetime.now().isoformat(timespec="seconds"),
            "device": "cuda" if torch.cuda.is_available() else "cpu",
            "pid": os.getpid(),
        })
        _BASE_LISTES.update({"blanche": set(moteur.blanche_dom), "noire": set(moteur.noire_dom)})
        _ERREUR_CHARGEMENT = None
    return _MODELES


# ---------------------------------------------------------------------
# Listes de domaines gérées par l'administrateur (pages Trusted / Fraudulent Domains)
# ---------------------------------------------------------------------
_BASE_LISTES = {}            # listes des fichiers CSV (whitelist_propre / blacklist_propre)
_DERNIERE_SYNCHRO = [0.0]


def synchroniser_listes(forcer=False):
    """Ajoute aux listes du moteur les domaines saisis par l'administrateur dans la base.

    Liste blanche = CSV + domaines « approved » ; liste noire = CSV + domaines « active ».
    Relu au plus une fois par minute (ou tout de suite avec forcer=True).
    Rappel : un domaine de la liste blanche n'est accepté que s'il est PROUVÉ (DKIM ou SPF aligné).
    """
    m = _MODELES.get("moteur")
    if m is None or (not forcer and time.time() - _DERNIERE_SYNCHRO[0] < 60):
        return
    _DERNIERE_SYNCHRO[0] = time.time()
    try:
        from services.database import session, DomainConfiance, DomainFrauduleux
        with session() as s:
            blanche = {d.domaine.strip().lower() for d in s.query(DomainConfiance).filter_by(statut="approved")}
            noire = {d.domaine.strip().lower() for d in s.query(DomainFrauduleux).filter_by(statut="active")}
    except Exception:
        return                # pas de base (tests, notebook) : on garde les listes des CSV
    m.blanche_dom = _BASE_LISTES.get("blanche", set()) | blanche
    m.noire_dom = _BASE_LISTES.get("noire", set()) | noire


_SEUILS_APPRIS = {}          # valeurs de fusion_modele/parametres.json
CHEMIN_CONFIG = os.path.join(BASE_DIR, "config_mailguard.json")


def _appliquer_config(moteur):
    """Seuils modifiés à la main par l'administrateur (page Calibration), s'il y en a."""
    import json
    try:
        with open(CHEMIN_CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return
    if cfg.get("methode_calibration") == "manuel":
        moteur.seuil_suspect = float(cfg.get("SEUIL_SUSPECT_FUSION", moteur.seuil_suspect))
        moteur.seuil_fraude = float(cfg.get("SEUIL_FRAUDULEUX_FUSION", moteur.seuil_fraude))


def changer_seuils_fusion(suspect=None, frauduleux=None):
    """Applique tout de suite de nouveaux seuils (None, None = revenir aux seuils appris)."""
    global SEUIL_SUSPECT, SEUIL_FRAUDULEUX, SEUIL_DECISION
    m = _MODELES.get("moteur")
    if m is None:
        return False
    m.seuil_suspect = float(suspect if suspect is not None else _SEUILS_APPRIS["suspect"])
    m.seuil_fraude = float(frauduleux if frauduleux is not None else _SEUILS_APPRIS["frauduleux"])
    SEUIL_SUSPECT, SEUIL_FRAUDULEUX = m.seuil_suspect, m.seuil_fraude
    SEUIL_DECISION = SEUIL_FRAUDULEUX
    return True


def poids_fusion():
    """Poids appris par la régression logistique de la fusion (lus dans le modèle chargé)."""
    m = _MODELES.get("moteur")
    if m is None:
        return {}
    poids = {nom: round(float(c), 3) for nom, c in zip(m.ind, m.lr.coef_[0])}
    poids["constante"] = round(float(m.lr.intercept_[0]), 3)
    return poids


def _moteur():
    if not _MODELES:
        _recharger_si_absent()
    return _MODELES.get("moteur")


def etat_modeles() -> dict:
    """Résumé affiché dans la page Paramètres."""
    if not _MODELES:
        return {"charges": False, "erreur": _ERREUR_CHARGEMENT, "dossier": DOSSIER_MODELES}
    m = _MODELES["moteur"]
    return {
        "charges": True,
        "duree_chargement_s": _MODELES["duree_chargement_s"],
        "charge_le": _MODELES["charge_le"],
        "device": _MODELES["device"],
        "pid": _MODELES["pid"],
        "modeles": {
            "S1 domaine": f"CANINE (seuil {m.seuil_s1:.2f})",
            "S2 identité": f"Gradient Boosting + règle 30 jours (seuil {m.seuil_s2:.2f})",
            "S3 liens": f"règles + Gradient Boosting du chemin (seuil {m.s3['seuil']:.3f})",
            "S4 contenu": f"multilingual-e5 + régression logistique (seuil {m.seuil_s4:.3f})",
            "S5 authentification": "Gradient Boosting + veto Nouvelair",
            "Fusion": f"régression logistique (suspect ≥ {m.seuil_suspect:.3f}, frauduleux ≥ {m.seuil_fraude:.3f})",
        },
        "liste_blanche": len(m.blanche_adr) + len(m.blanche_dom),
        "liste_noire": len(m.noire_adr) + len(m.noire_dom),
    }


def _recharger_si_absent():
    """Charge le moteur s'il ne l'est pas encore (par exemple si les modèles ont été copiés après le démarrage)."""
    global _ERREUR_CHARGEMENT
    if _MODELES.get("moteur") is not None:
        return True
    try:
        charger_modeles()
        return True
    except Exception as e:
        _ERREUR_CHARGEMENT = f"{type(e).__name__} : {e}"
        return False


try:
    print("MailGuard : chargement des modèles (une seule fois)...")
    charger_modeles()
    print(f"MailGuard prêt en {_MODELES['duree_chargement_s']} s ({_MODELES['device']})")
except Exception as _e:
    import warnings
    _ERREUR_CHARGEMENT = f"{type(_e).__name__} : {_e}"
    warnings.warn(f"[MailGuard] Moteur non chargé : {_ERREUR_CHARGEMENT}", RuntimeWarning, stacklevel=2)

# anciens noms de variables (certains tests les lisent encore)
model_bert = _MODELES.get("bert")
model_1000 = content_tokenizer = content_model = None


# =====================================================================
# 2. LECTURE DU MESSAGE (inchangé : utilisé par la surveillance Gmail)
# =====================================================================
def extraire_corps_html(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    return part.get_payload(decode=True).decode(errors="ignore")
                except Exception:
                    return ""
    else:
        if msg.get_content_type() == "text/html":
            return msg.get_payload(decode=True).decode(errors="ignore")
    return ""


def extraire_liens(html):
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    return [{"texte_affiche": a.get_text(strip=True), "url_reelle": a["href"]} for a in soup.find_all("a", href=True)]


def detecter_lien_trompeur(texte_affiche, url_reelle):
    """Le texte du lien annonce un domaine, mais le lien mène ailleurs (affiché comme raison)."""
    domaine_reel = urlparse(url_reelle).netloc.lower()
    m = re.search(r"([a-z0-9-]+\.(com|tn|net|org|fr))", (texte_affiche or "").lower())
    if m and m.group(1) not in domaine_reel:
        return {"suspect": True, "raison": f"le texte annonce '{m.group(1)}' mais le lien mène vers '{domaine_reel}'"}
    return {"suspect": False, "raison": ""}


def detecter_langue(texte):
    if detect is None:
        return "indéterminée"
    try:
        code = detect(texte)
        return {"fr": "français", "en": "anglais", "ar": "arabe", "de": "allemand", "ru": "russe"}.get(code, f"autre ({code})")
    except Exception:
        return "indéterminée"


def analyser_authentification(auth_results_header):
    """Lecture simple des trois verdicts (gardée pour l'affichage)."""
    if not auth_results_header:
        return {"spf": "absent", "dkim": "absent", "dmarc": "absent"}
    t = auth_results_header.lower()

    def statut(nom):
        m = re.search(rf"{nom}=(\w+)", t)
        return m.group(1) if m else "absent"
    return {"spf": statut("spf"), "dkim": statut("dkim"), "dmarc": statut("dmarc")}


# =====================================================================
# 3. ANALYSE D'UN DOMAINE SEUL (pages d'administration)
# =====================================================================
def analyser_domaine_bert(domaine_teste, seuil_haut=None):
    """Ancien nom gardé. Le domaine imite-t-il une marque protégée ? (signal 1 : CANINE)"""
    m = _moteur()
    if m is None:
        return {"domaine": domaine_teste, "distance": None, "plus_proche": None, "score": None,
                "verdict": "INDISPONIBLE (modèles non chargés)"}
    from mailguard import org
    d = (domaine_teste or "").strip().lower()
    d = d.split("@")[-1]
    d = d[4:] if d.startswith("www.") else d
    if org(d) in m.officiels:
        return {"domaine": domaine_teste, "distance": 0.0, "plus_proche": org(d), "score": 0.0, "marque": "",
                "verdict": "LÉGITIME (domaine officiel d'une marque protégée)"}
    s, marque = m._canine([d]).get(d, (0.0, ""))
    officiel = m.officiel_de(marque) if marque else None
    if s >= m.seuil_s1:
        verdict = f"FRAUDULEUX (imite la marque {marque}, score CANINE {s:.2f} ≥ {m.seuil_s1:.2f})"
    else:
        verdict = f"LÉGITIME (n'imite aucune marque protégée, score CANINE {s:.2f})"
    return {"domaine": domaine_teste, "score": round(float(s), 3), "marque": marque,
            "plus_proche": officiel, "distance": round(1 - float(s), 4), "seuil": m.seuil_s1, "verdict": verdict}


def analyser_domaine(domaine):
    """Signal 1 (nom) + signal 2 (identité au jour d'aujourd'hui) pour un domaine seul."""
    import pandas as pd
    r1 = analyser_domaine_bert(domaine)
    m = _moteur()
    r2 = None
    if m is not None:
        from mailguard import org
        d = org((domaine or "").split("@")[-1])
        r2 = m._signal2(d, pd.Timestamp.now(tz="UTC"))
    raisons = []
    if r1.get("score") is not None and "FRAUDULEUX" in r1["verdict"]:
        raisons.append(r1["verdict"])
    if r2 and r2.get("alerte"):
        raisons.append(f"domaine créé il y a {r2['age']:.0f} jours")
    return {**r1, "identite": r2, "age_jours": (round(r2["age"]) if r2 else None),
            "score_identite": (round(r2["score"], 3) if r2 else None),
            "frauduleux": bool(raisons), "raisons": raisons or ["aucun indice sur le nom ni sur l'identité du domaine"]}


# =====================================================================
# 4. ANALYSE D'UN MESSAGE (point d'entrée de toute l'application)
# =====================================================================
def _categorie(decision):
    return {"frauduleux": "FRAUDULEUX", "suspect": "SUSPECT"}.get(decision, "LÉGITIME")


def _niveau(decision):
    return {"frauduleux": "🔴 RISQUE ÉLEVÉ", "suspect": "🟡 RISQUE MODÉRÉ"}.get(decision, "🟢 RISQUE FAIBLE")


def analyser_email_complet(domaine_expediteur, texte_email="", liens=None, auth_header="", message=None, sujet=""):
    """Point d'entrée unique utilisé par le dashboard, la surveillance et le test manuel.

    - domaine_expediteur : adresse ou domaine de l'expéditeur
    - texte_email        : texte du message
    - liens              : liste de {"texte_affiche", "url_reelle"} (comme extraire_liens)
    - auth_header        : valeur de l'en-tête Authentication-Results
    - message            : (facultatif) le message complet (objet email ou octets). S'il est fourni,
                           tous les en-têtes sont lus (Return-Path, Reply-To, Message-ID...) : c'est plus précis.
    """
    liens = liens or []
    m = _moteur()
    if m is None:
        return {"scores_detail": {}, "details": {}, "score_final": 0.0, "categorie": "LÉGITIME",
                "niveau": "⚪ MODÈLES NON CHARGÉS", "etage": 0, "signaux_calcules": 0, "raisons": [],
                "explication": f"Le moteur MailGuard n'est pas chargé : {_ERREUR_CHARGEMENT}"}

    synchroniser_listes()
    if message is not None:
        brut = message if isinstance(message, (bytes, bytearray)) else message.as_bytes()
        r = m.analyser(bytes(brut))
    else:
        r = m.analyser_parties(domaine_expediteur, texte_email, liens, auth_header or "", sujet)

    D = r.get("details", {})
    sig = r.get("signaux", {})
    s1, s2, s4, s5 = D.get("s1"), D.get("s2"), D.get("s4"), D.get("auth_score")
    liens_det = D.get("liens", [])

    # liens : on garde le format attendu par l'affichage (suspect, raisons, url, texte_affiche)
    affiches = {l.get("url_reelle"): l.get("texte_affiche", "") for l in liens if isinstance(l, dict)}
    details_liens = []
    for dl in liens_det:
        texte = affiches.get(dl["url"], "")
        raisons = list(dl.get("raisons", []))
        trompeur = detecter_lien_trompeur(texte, dl["url"]) if texte else {"suspect": False}
        if trompeur["suspect"]:
            raisons.append(trompeur["raison"])
        details_liens.append({"url": dl["url"], "texte_affiche": texte, "suspect": dl["suspect"] or trompeur["suspect"],
                              "douteux": dl.get("douteux", False), "score_chemin": dl.get("chemin"),
                              "raisons": raisons or ["aucun indice"]})

    score_liens = 0.0
    if sig:
        score_liens = max(float(sig.get("S3_chemin", 0) or 0), 1.0 if sig.get("S3_regle") else 0.0,
                          1.0 if any(l["suspect"] for l in details_liens) else 0.0)

    auth = D.get("auth") or analyser_authentification(auth_header)
    scores = {}
    details = {}
    if s1 is not None:                         # le message n'a pas été tranché par une liste
        scores = {"domaine_bert": s1["score"], "liens": round(score_liens, 3),
                  "authentification": (round(float(s5), 3) if s5 is not None else 0.0),
                  "contenu": s4["score"], "domaine_randomforest": (round(s2["score"], 3) if s2 else None)}
        details["domaine_bert"] = {"domaine": s1["domaine"], "score": s1["score"], "marque": s1["marque"],
                                   "plus_proche": s1["domaine_officiel"] or None,
                                   "distance": (round(1 - s1["score"], 4) if s1["alerte"] else None),
                                   "seuil": s1["seuil"],
                                   "verdict": (f"FRAUDULEUX (imite la marque {s1['marque']}, score {s1['score']:.2f})"
                                               if s1["alerte"] else f"LÉGITIME (aucune imitation, score {s1['score']:.2f})")}
        details["contenu"] = {"suspect": s4["alerte"], "seuil": s4["seuil"],
                              "probabilite": (s4["score"] if s4["longueur"] >= 30 else None),
                              "langue_detectee": detecter_langue(texte_email) if texte_email else "indéterminée",
                              "note": ("Texte trop court : signal contenu ignoré" if s4["longueur"] < 30 else "")}
        if s2:
            details["domaine_randomforest"] = {"age_jours": round(s2["age"]), "whois_disponible": True,
                                               "ssl_disponible": True, "alerte": s2["alerte"], "seuil": s2["seuil"]}
        else:
            details["domaine_randomforest"] = {"disponible": False,
                                               "note": "domaine connu (classement Tranco), messagerie gratuite, ou registres injoignables : signal neutre"}
        details["fusion"] = D.get("fusion", {})
    details["liens"] = details_liens
    details["authentification"] = {"spf": auth.get("spf", "absent"), "dkim": auth.get("dkim", "absent"),
                                   "dmarc": auth.get("dmarc", "absent"), "decision": D.get("auth_decision"),
                                   "raisons": D.get("auth_raisons", [])}

    etape = r.get("etape", "")
    # Une règle sûre (usurpation Nouvelair, imitation d'une marque, lien piégé) :
    # - frauduleux → on affiche 1,0 ;
    # - suspect → on affiche au moins le seuil suspect, pour que la jauge soit cohérente.
    score_fusion = r["score"]
    if etape.startswith("1."):
        if r["decision"] == "frauduleux":
            score_final = 1.0
        else:
            score_final = max(score_fusion, SEUIL_SUSPECT)
    else:
        score_final = score_fusion
    nb = sum(1 for v in scores.values() if v is not None)
    return {
        "scores_detail": scores,
        "details": details,
        "score_final": score_final,
        "score_fusion": score_fusion,
        "categorie": _categorie(r["decision"]),
        "decision": r["decision"],
        "niveau": _niveau(r["decision"]),
        "etape_decision": etape,
        "etage": 1 if etape.startswith(("0.", "1.")) else 2,
        "signaux_calcules": nb,
        "raisons": r.get("raisons", []),
        "seuil_suspect": SEUIL_SUSPECT,
        "seuil_frauduleux": SEUIL_FRAUDULEUX,
        "duree_s": r.get("duree_s"),
        "texte_apercu": (texte_email or "")[:400],
        "explication": f"Étape de décision : {etape}. " + (" · ".join(r.get("raisons", [])) or "aucun indice suspect."),
    }


def calculer_score_cascade(domaine_expediteur, liens_email=None, auth_header=None, texte_email=None):
    """Ancien nom gardé (utilisé par certains tests)."""
    return analyser_email_complet(domaine_expediteur, texte_email or "", liens_email or [], auth_header or "")
