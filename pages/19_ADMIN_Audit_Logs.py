"""
pages/19_ADMIN_Audit_Logs.py
Journal d'audit — admin.

Lecture de la table journal_audit. Chaque ligne est écrite au moment où l'action
a lieu (connexion, comptes, administrateurs, listes de domaines, seuils,
qualifications, alertes). Rien n'est inventé ni modifié après coup.
"""
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from services.audit_service import ACTIONS, ENTITES, journaliser, lister_journal
from utils.auth_ui import exiger_admin
from utils.ui_helpers import entete_page

exiger_admin()

entete_page(
    titre="Journal d'audit",
    sous_titre="Traçabilité de toutes les actions d'administration, enregistrées en base",
)

COULEURS = {"LOGIN": "#2196F3", "LOGIN_FAILED": "#F44336", "LOGOUT": "#90A4AE",
            "ACTIVATE_USER": "#4CAF50", "SUSPEND_USER": "#FF9800", "DELETE_USER": "#F44336",
            "CREATE_ADMIN": "#3F51B5", "SUSPEND_ADMIN": "#FF9800", "ACTIVATE_ADMIN": "#4CAF50",
            "DELETE_ADMIN": "#F44336", "DOMAIN_ADD": "#009688", "DOMAIN_VALIDATE": "#009688",
            "DOMAIN_REMOVE": "#795548", "THRESHOLD_CHANGE": "#673AB7", "QUALIFICATION": "#9C27B0",
            "ALERT_VIEW": "#607D8B", "ALERT_RESOLVE": "#009688", "ALERT_REOPEN": "#FF9800"}

col1, col2, col3, col4 = st.columns(4)
with col1:
    filtre_action = st.selectbox("Action", ["Toutes"] + ACTIONS)
with col2:
    filtre_entite = st.selectbox("Type d'entité", ["Tous"] + ENTITES)
with col3:
    periode = st.date_input("Période", value=(date.today() - timedelta(days=30), date.today()))
with col4:
    limite = st.number_input("Nombre maximum", min_value=10, max_value=1000, value=100, step=10)
recherche = st.text_input("Rechercher (domaine, adresse, détail)", "")

debut = fin = None
if isinstance(periode, (list, tuple)) and len(periode) == 2:
    debut = datetime.combine(periode[0], datetime.min.time())
    fin = datetime.combine(periode[1], datetime.max.time())

logs = lister_journal(action=None if filtre_action == "Toutes" else filtre_action,
                      entite_type=None if filtre_entite == "Tous" else filtre_entite,
                      debut=debut, fin=fin, recherche=recherche.strip(), limite=limite)

if not logs:
    st.info("Aucune entrée pour ces critères. Les actions d'administration apparaîtront ici "
            "dès qu'elles seront effectuées.")
else:
    st.markdown(f"**{len(logs)} entrée(s)**")
    for log in logs:
        couleur = COULEURS.get(log["action"], "#607D8B")
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:1rem;padding:.5rem .8rem;'
            f'border-left:4px solid {couleur};background:#F8F9FA;'
            f'border-radius:0 8px 8px 0;margin-bottom:.35rem;font-size:.87rem;flex-wrap:wrap;">'
            f'<span style="font-family:monospace;color:#999;min-width:140px;">{log["horodatage"]}</span>'
            f'<span style="background:{couleur};color:#fff;border-radius:4px;padding:1px 7px;'
            f'font-size:.78rem;font-weight:700;min-width:120px;text-align:center;">{log["action"]}</span>'
            f'<span style="color:#666;">{log["entite_type"]}</span>'
            f'<code>{log["entite_id"]}</code>'
            f'<span style="color:#555;flex:1;">{log["details"]}</span>'
            f'<span style="color:#999;font-size:.78rem;">par {log["acteur"]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.download_button("⬇️ Exporter en CSV", pd.DataFrame(logs).to_csv(index=False).encode("utf-8"),
                       file_name=f"journal_audit_{date.today()}.csv", mime="text/csv")

st.divider()
with st.expander("📝 Ajouter une note au journal"):
    st.caption("Pour consigner une action faite hors de l'application (par exemple : "
               "« liste blanche vérifiée avec le service informatique »). L'auteur et l'heure "
               "sont enregistrés automatiquement.")
    with st.form("note_audit", clear_on_submit=True):
        note = st.text_input("Note")
        if st.form_submit_button("Enregistrer") and note.strip():
            journaliser("NOTE", "admin", "", note.strip())
            st.success("Note enregistrée.")
            st.rerun()
