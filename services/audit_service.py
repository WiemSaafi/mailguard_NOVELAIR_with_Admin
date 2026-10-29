"""
services/audit_service.py
=========================
Journal d'audit persistant (table journal_audit).

    journaliser("DOMAIN_ADD", "domaine", "exemple.com", "ajouté en liste noire")

L'auteur est l'utilisateur connecté dans Streamlit ; hors de l'application
(tests, scripts), c'est « système ». Une erreur d'écriture du journal ne doit
jamais bloquer l'action elle-même : elle est simplement ignorée.
"""

from datetime import datetime

from services.database import JournalAudit, session

ACTIONS = ["LOGIN", "LOGIN_FAILED", "LOGOUT", "ACTIVATE_USER", "SUSPEND_USER", "DELETE_USER",
           "CREATE_ADMIN", "SUSPEND_ADMIN", "ACTIVATE_ADMIN", "DELETE_ADMIN",
           "DOMAIN_ADD", "DOMAIN_VALIDATE", "DOMAIN_REMOVE", "THRESHOLD_CHANGE",
           "QUALIFICATION", "ALERT_VIEW", "ALERT_RESOLVE", "ALERT_REOPEN", "NOTE"]
ENTITES = ["admin", "utilisateur", "domaine", "seuil", "analyse", "alerte"]


def acteur_courant() -> str:
    try:
        import streamlit as st
        u = st.session_state.get("utilisateur")
        if u and u.get("email"):
            return u["email"]
    except Exception:
        pass
    return "système"


def journaliser(action: str, entite_type: str = "", entite_id: str = "", details: str = "",
                acteur: str = None) -> None:
    try:
        with session() as s:
            s.add(JournalAudit(horodatage=datetime.now(), acteur=acteur or acteur_courant(),
                               action=action, entite_type=entite_type,
                               entite_id=str(entite_id or "")[:255], details=details or ""))
            s.commit()
    except Exception:
        pass


def lister_journal(action: str = None, entite_type: str = None, debut: datetime = None,
                   fin: datetime = None, recherche: str = "", limite: int = 100) -> list[dict]:
    with session() as s:
        q = s.query(JournalAudit)
        if action:
            q = q.filter(JournalAudit.action == action)
        if entite_type:
            q = q.filter(JournalAudit.entite_type == entite_type)
        if debut:
            q = q.filter(JournalAudit.horodatage >= debut)
        if fin:
            q = q.filter(JournalAudit.horodatage <= fin)
        if recherche:
            motif = f"%{recherche}%"
            q = q.filter((JournalAudit.entite_id.ilike(motif)) | (JournalAudit.acteur.ilike(motif))
                         | (JournalAudit.details.ilike(motif)))
        return [{"id": j.id, "horodatage": j.horodatage.strftime("%Y-%m-%d %H:%M:%S"),
                 "acteur": j.acteur, "action": j.action, "entite_type": j.entite_type,
                 "entite_id": j.entite_id, "details": j.details}
                for j in q.order_by(JournalAudit.horodatage.desc(), JournalAudit.id.desc())
                          .limit(int(limite)).all()]
