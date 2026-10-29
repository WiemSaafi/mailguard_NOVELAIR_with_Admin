"""
services/history_service.py
============================
Enregistrement et lecture des analyses, en base de données.

Les signatures des fonctions sont inchangées : les pages et les bancs d'essai
existants continuent de fonctionner sans modification. Seul le support a
change, du fichier JSON vers les tables `analyses` et `scores_signaux`.

L'argument `identifiant` designe un compte utilisateur. Sans lui, les
fonctions travaillent sur les analyses non rattachees a un compte, ce qui
correspond au comportement anterieur a l'authentification.
"""

import json
from datetime import datetime

from sqlalchemy import func

from services.database import Analyse, ScoreSignal, Utilisateur, charger_json, session

SIGNAUX = ["domaine_bert", "contenu", "liens", "authentification",
           "domaine_randomforest"]


# ─────────────────────────────────────────────────────────────────────────
# Conversions entre la base et le dictionnaire attendu par l'interface
# ─────────────────────────────────────────────────────────────────────────

def _identifiant_vers_id(s, identifiant):
    """Traduit l'identifiant public d'un compte en cle primaire."""
    if not identifiant:
        return None
    utilisateur = s.query(Utilisateur).filter_by(identifiant=identifiant).first()
    return utilisateur.id if utilisateur else None


def _vers_dictionnaire(analyse: Analyse) -> dict:
    """Reconstruit exactement la forme de dictionnaire attendue par l'interface."""
    scores = {score.signal: score.valeur for score in analyse.scores}
    return {
        "id": analyse.id,
        "uid": analyse.uid_imap,
        "timestamp": analyse.horodatage.isoformat(),
        "domaine_expediteur": analyse.domaine_expediteur,
        "sujet": analyse.sujet,
        "texte_apercu": analyse.texte_apercu,
        "nb_liens": analyse.nb_liens,
        "duree_analyse_ms": analyse.duree_analyse_ms,
        "action_appliquee": analyse.action_appliquee,
        "source": analyse.source,
        "categorie": analyse.categorie,
        "score_final": analyse.score_final,
        "etage": analyse.etage,
        "signaux_calcules": analyse.signaux_calcules,
        "scores_detail": scores,
        "details": charger_json(analyse.details_json, {}),
        "explication": analyse.explication,
    }


# ─────────────────────────────────────────────────────────────────────────
# Lecture
# ─────────────────────────────────────────────────────────────────────────

def charger_historique(identifiant: str = None) -> list:
    """Toutes les analyses d'un compte, de la plus ancienne a la plus recente."""
    with session() as s:
        utilisateur_id = _identifiant_vers_id(s, identifiant)
        requete = (s.query(Analyse)
                   .filter(Analyse.utilisateur_id == utilisateur_id)
                   .order_by(Analyse.horodatage, Analyse.id))
        return [_vers_dictionnaire(a) for a in requete.all()]


def get_stats(identifiant: str = None) -> dict:
    """Compteurs et score moyen, calcules par la base plutot qu'en Python."""
    with session() as s:
        utilisateur_id = _identifiant_vers_id(s, identifiant)
        base = s.query(Analyse).filter(Analyse.utilisateur_id == utilisateur_id)

        total = base.count()
        if not total:
            return {"total": 0, "dangereux": 0, "suspects": 0,
                    "legitimes": 0, "score_moyen": 0.0}

        comptes = dict(
            s.query(Analyse.categorie, func.count(Analyse.id))
            .filter(Analyse.utilisateur_id == utilisateur_id)
            .group_by(Analyse.categorie).all()
        )
        moyenne = (s.query(func.avg(Analyse.score_final))
                   .filter(Analyse.utilisateur_id == utilisateur_id).scalar()) or 0.0

        return {
            "total": total,
            "dangereux": comptes.get("DANGEREUX", 0),
            "suspects": comptes.get("SUSPECT", 0),
            "legitimes": comptes.get("LÉGITIME", 0),
            "score_moyen": round(float(moyenne), 3),
        }


def moyenne_par_signal(identifiant: str = None) -> dict:
    """Moyenne de chaque signal, en une seule requete agregee.

    C'est le gain concret du passage en base : cette statistique demandait
    auparavant de parcourir tout l'historique en Python.
    """
    with session() as s:
        utilisateur_id = _identifiant_vers_id(s, identifiant)
        lignes = (s.query(ScoreSignal.signal, func.avg(ScoreSignal.valeur))
                  .join(Analyse, Analyse.id == ScoreSignal.analyse_id)
                  .filter(Analyse.utilisateur_id == utilisateur_id,
                          ScoreSignal.valeur.isnot(None))
                  .group_by(ScoreSignal.signal).all())
        return {signal: round(float(moyenne), 3) for signal, moyenne in lignes}


# ─────────────────────────────────────────────────────────────────────────
# Ecriture
# ─────────────────────────────────────────────────────────────────────────

def ajouter_entree(
    domaine_expediteur: str,
    sujet: str,
    texte_apercu: str,
    nb_liens: int,
    resultat: dict,
    duree_ms: float,
    action_appliquee: str = "aucune",
    source: str = "manuel",
    uid: str = "",
    identifiant: str = None,
) -> dict:
    """Enregistre une analyse et ses cinq scores, puis renvoie l'entree creee."""
    from services.quarantine_service import categoriser_email

    score = resultat.get("score_final", 0)
    scores_detail = resultat.get("scores_detail", {}) or {}

    with session() as s:
        analyse = Analyse(
            utilisateur_id=_identifiant_vers_id(s, identifiant),
            horodatage=datetime.now(),
            domaine_expediteur=domaine_expediteur or "",
            sujet=(sujet or "")[:500],
            texte_apercu=(texte_apercu or "")[:300],
            nb_liens=nb_liens or 0,
            score_final=float(score),
            categorie=categoriser_email(score, resultat),
            etage=resultat.get("etage", 1),
            signaux_calcules=resultat.get("signaux_calcules", 4),
            duree_analyse_ms=float(duree_ms or 0),
            action_appliquee=action_appliquee or "aucune",
            source=source or "manuel",
            uid_imap=uid or "",
            details_json=json.dumps(resultat.get("details", {}),
                                    ensure_ascii=False, default=str),
            explication=resultat.get("explication", ""),
        )
        s.add(analyse)
        s.flush()

        for signal in SIGNAUX:
            if signal in scores_detail:
                valeur = scores_detail[signal]
                s.add(ScoreSignal(
                    analyse_id=analyse.id, signal=signal,
                    valeur=None if valeur is None else float(valeur),
                ))

        s.commit()
        s.refresh(analyse)
        return _vers_dictionnaire(analyse)


def effacer_historique(identifiant: str = None):
    """Supprime les analyses d'un compte. Les scores suivent en cascade."""
    with session() as s:
        utilisateur_id = _identifiant_vers_id(s, identifiant)
        for analyse in s.query(Analyse).filter(
                Analyse.utilisateur_id == utilisateur_id).all():
            s.delete(analyse)
        s.commit()


def sauvegarder_historique(historique: list, identifiant: str = None):
    """Remplace l'historique d'un compte par la liste fournie.

    Conservee pour compatibilite : l'interface n'ecrit plus directement, elle
    passe par ajouter_entree.
    """
    effacer_historique(identifiant)
    for entree in historique:
        ajouter_entree(
            domaine_expediteur=entree.get("domaine_expediteur", ""),
            sujet=entree.get("sujet", ""),
            texte_apercu=entree.get("texte_apercu", ""),
            nb_liens=entree.get("nb_liens", 0),
            resultat=entree,
            duree_ms=entree.get("duree_analyse_ms", 0),
            action_appliquee=entree.get("action_appliquee", "aucune"),
            source=entree.get("source", "manuel"),
            uid=entree.get("uid", ""),
            identifiant=identifiant,
        )
