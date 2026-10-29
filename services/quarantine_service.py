"""
services/quarantine_service.py
================================
Logique de catégorisation et d'action sur les emails.
Utilise les seuils configurables depuis config_mailguard.json.
"""

import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Seuils appris par le modèle de fusion (au plus 2 % / 0,5 % de vrais mails accusés).
SEUIL_SUSPECT_DEFAUT = 0.825
SEUIL_FRAUDULEUX_DEFAUT = 0.928


def seuils_defaut():
    """Seuils du modèle de fusion (relus dans fusion_modele/parametres.json s'il est chargé)."""
    try:
        import mailguard_core as mg
        return float(mg.SEUIL_SUSPECT), float(mg.SEUIL_FRAUDULEUX)
    except Exception:
        return SEUIL_SUSPECT_DEFAUT, SEUIL_FRAUDULEUX_DEFAUT


def migrer_seuils(seuil_suspect, seuil_dangereux):
    """Les anciens seuils (0,25 / 0,50) n'ont plus de sens avec le nouveau score :
    toute valeur sous 0,6 est remplacée par les seuils de la fusion."""
    defaut_s, defaut_d = seuils_defaut()
    if seuil_suspect is None or seuil_suspect < 0.6:
        seuil_suspect = defaut_s
    if seuil_dangereux is None or seuil_dangereux < 0.6 or seuil_dangereux < seuil_suspect:
        seuil_dangereux = max(defaut_d, seuil_suspect)
    return seuil_suspect, seuil_dangereux


def get_seuils():
    """Charge les seuils depuis la session (préférences de l'utilisateur) ou ceux de la fusion."""
    try:
        import streamlit as st
        seuil_suspect = st.session_state.get("seuil_suspect")
        seuil_dangereux = st.session_state.get("seuil_dangereux")
    except Exception:
        seuil_suspect = seuil_dangereux = None
    return migrer_seuils(seuil_suspect, seuil_dangereux)


def categoriser_email(score: float, resultat: dict = None) -> str:
    """
    Retourne 'LÉGITIME', 'SUSPECT' ou 'DANGEREUX' (affiché « FRAUDULEUX »).

    Si le résultat du moteur est fourni, une décision prise par une liste ou une
    règle sûre est respectée telle quelle (elle ne dépend pas du score).
    """
    if resultat:
        etape = resultat.get("etape_decision", "")
        if etape.startswith(("0.", "1.")):
            return {"FRAUDULEUX": "DANGEREUX", "SUSPECT": "SUSPECT"}.get(resultat.get("categorie"), "LÉGITIME")
    seuil_suspect, seuil_dangereux = get_seuils()
    if score >= seuil_dangereux:
        return "DANGEREUX"
    elif score >= seuil_suspect:
        return "SUSPECT"
    else:
        return "LÉGITIME"


def get_badge_info(categorie: str) -> dict:
    """Retourne icône, couleur CSS et label pour une catégorie."""
    mapping = {
        "LÉGITIME": {
            "icone": "🟢",
            "couleur": "#166534",
            "fond": "#DCFCE7",
            "bordure": "#22C55E",
            "label": "LÉGITIME",
        },
        "SUSPECT": {
            "icone": "🟡",
            "couleur": "#854D0E",
            "fond": "#FEF9C3",
            "bordure": "#EAB308",
            "label": "SUSPECT",
        },
        "DANGEREUX": {
            "icone": "🔴",
            "couleur": "#991B1B",
            "fond": "#FEE2E2",
            "bordure": "#EF4444",
            "label": "FRAUDULEUX",
        },
    }
    return mapping.get(categorie, mapping["SUSPECT"])


def get_action_recommandee(categorie: str, action_config: str = "quarantaine") -> str:
    """
    Retourne l'action à appliquer selon la catégorie et la configuration.
    action_config: 'rien', 'marquer', 'suspects', 'quarantaine'
    """
    if categorie == "LÉGITIME":
        return "Conserver dans la boîte de réception"
    elif categorie == "SUSPECT":
        if action_config in ("suspects", "quarantaine"):
            return "Déplacer vers MailGuard/Suspects"
        elif action_config == "marquer":
            return "Marquer comme suspect"
        else:
            return "Conserver avec avertissement"
    else:  # DANGEREUX
        if action_config == "quarantaine":
            return "Déplacer vers MailGuard/Quarantaine"
        elif action_config == "suspects":
            return "Déplacer vers MailGuard/Suspects"
        elif action_config == "marquer":
            return "Marquer comme frauduleux"
        else:
            return "Conserver avec alerte"


def formater_age(valeur) -> str:
    """CORRECTIF 1 : l'ancien code appliquait le format ':.0f' a la chaine '?'
    quand le signal d'identite etait muet, ce qui levait une erreur et faisait planter
    l'affichage du resultat."""
    try:
        return f"{float(valeur):.0f} jours"
    except (TypeError, ValueError):
        return "inconnu"


def construire_explication(resultat: dict) -> list:
    """
    Liste des facteurs qui ont influencé la décision (nouveaux signaux S1 à S5).
    ✗ = indice suspect, ✓ = indice rassurant, – = signal muet.
    """
    scores = resultat.get("scores_detail", {}) or {}
    details = resultat.get("details", {}) or {}
    facteurs = []

    etape = resultat.get("etape_decision", "")
    if etape:
        facteurs.append(f"→ Étape qui a décidé : {etape}")
    if etape.startswith("0."):
        facteurs += [f"✗ {r}" if resultat.get("categorie") != "LÉGITIME" else f"✓ {r}"
                     for r in resultat.get("raisons", [])]
        return facteurs

    # S1 : le nom du domaine imite-t-il une marque ? (CANINE)
    d = details.get("domaine_bert", {})
    if d:
        if "FRAUDULEUX" in d.get("verdict", ""):
            facteurs.append(f"✗ S1 : le domaine imite la marque {d.get('marque')} "
                            f"(score CANINE {d.get('score', 0):.2f} ≥ {d.get('seuil', 0.44):.2f})")
        else:
            facteurs.append(f"✓ S1 : le domaine n'imite aucune marque protégée (score CANINE {d.get('score', 0):.2f})")

    # S2 : identité du domaine (âge, certificats)
    rf = details.get("domaine_randomforest", {})
    if scores.get("domaine_randomforest") is not None:
        age = formater_age(rf.get("age_jours"))
        if rf.get("alerte"):
            facteurs.append(f"✗ S2 : domaine jeune ou identité douteuse (âge : {age})")
        else:
            facteurs.append(f"✓ S2 : identité du domaine normale (âge : {age})")
    else:
        facteurs.append("– S2 : signal muet (domaine connu, messagerie gratuite ou registres injoignables)")

    # S3 : liens
    liens = details.get("liens", [])
    suspects_liens = [l for l in liens if l.get("suspect")]
    if suspects_liens:
        facteurs.append(f"✗ S3 : {len(suspects_liens)} lien(s) suspect(s) sur {len(liens)}")
    elif liens:
        facteurs.append(f"✓ S3 : {len(liens)} lien(s) analysé(s), aucun suspect")
    else:
        facteurs.append("– S3 : aucun lien dans ce message")

    # S4 : contenu (multilingual-e5)
    c = details.get("contenu", {})
    prob = c.get("probabilite")
    if prob is None:
        facteurs.append(f"– S4 : {c.get('note') or 'contenu non analysé'}")
    elif c.get("suspect"):
        facteurs.append(f"✗ S4 : le texte ressemble à du phishing ({prob * 100:.0f} %, seuil {c.get('seuil', 0.391):.3f})")
    else:
        facteurs.append(f"✓ S4 : le texte ne ressemble pas à du phishing ({prob * 100:.0f} %)")

    # S5 : authentification
    a = details.get("authentification", {})
    resume = f"SPF={a.get('spf', 'absent').upper()}, DKIM={a.get('dkim', 'absent').upper()}, DMARC={a.get('dmarc', 'absent').upper()}"
    if a.get("decision") == "frauduleux":
        facteurs.append(f"✗ S5 : usurpation d'un domaine Nouvelair ({resume})")
    elif a.get("decision") == "suspect" or scores.get("authentification", 0) >= 0.5:
        facteurs.append(f"✗ S5 : authentification faible ({resume})")
    else:
        facteurs.append(f"✓ S5 : {resume}")

    fusion = details.get("fusion", {})
    if fusion:
        facteurs.append(f"→ Score de la fusion : {fusion.get('score', 0):.3f} "
                        f"(suspect ≥ {fusion.get('seuil_suspect', 0.825):.3f}, "
                        f"frauduleux ≥ {fusion.get('seuil_frauduleux', 0.928):.3f})")
    return facteurs


def construire_tableau_signaux(resultat: dict) -> list:
    """Tableau d'explication : une ligne par signal (S1 à S5)."""
    scores = resultat.get("scores_detail", {}) or {}
    details = resultat.get("details", {}) or {}
    lignes = []

    d = details.get("domaine_bert", {})
    lignes.append({"Signal": "🔎 S1 · Domaine (CANINE)", "Score": scores.get("domaine_bert") or 0.0,
                   "Interprétation": d.get("verdict", "non calculé (décision par les listes)")})

    rf = details.get("domaine_randomforest", {})
    v2 = scores.get("domaine_randomforest")
    lignes.append({"Signal": "🪪 S2 · Identité du domaine", "Score": v2 if v2 is not None else 0.0,
                   "Interprétation": (f"Âge : {formater_age(rf.get('age_jours'))} · "
                                      f"{'alerte' if rf.get('alerte') else 'normal'}") if v2 is not None
                   else "signal muet (vaut 0)"})

    liens = details.get("liens", [])
    nb_suspects = sum(1 for l in liens if l.get("suspect"))
    lignes.append({"Signal": "🔗 S3 · Liens", "Score": scores.get("liens") or 0.0,
                   "Interprétation": f"{len(liens)} lien(s), {nb_suspects} suspect(s)"})

    c = details.get("contenu", {})
    prob = c.get("probabilite")
    lignes.append({"Signal": "✉️ S4 · Contenu (e5)", "Score": scores.get("contenu") or 0.0,
                   "Interprétation": (f"Phishing : {prob * 100:.0f} % — {'suspect' if c.get('suspect') else 'sain'}"
                                      if prob is not None else c.get("note") or "non analysé")})

    a = details.get("authentification", {})
    lignes.append({"Signal": "🔐 S5 · Authentification", "Score": scores.get("authentification") or 0.0,
                   "Interprétation": f"SPF={a.get('spf', '?').upper()} · DKIM={a.get('dkim', '?').upper()} · "
                                     f"DMARC={a.get('dmarc', '?').upper()}"})
    return lignes
