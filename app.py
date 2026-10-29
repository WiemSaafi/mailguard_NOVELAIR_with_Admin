"""
app.py
=======
Point d'entrée de MailGuard.

    streamlit run app.py

Navigation basée sur les rôles :
  - Utilisateur : pages 01 à 06 uniquement
  - Admin       : pages 01 à 06 + toutes les pages ADMIN_*
"""

import streamlit as st

st.set_page_config(
    page_title="MailGuard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "MailGuard — détection de phishing et de domaines frauduleux."},
)

from utils.auth_ui import (
    barre_utilisateur,
    ecran_authentification,
    est_connecte,
    est_admin,
    id_utilisateur,
    utilisateur_actuel,
)
from utils.ui_helpers import (
    COULEURS,
    appliquer_signature,
    appliquer_theme,
    entete_page,
    pastille,
    titre_section,
)
from services import auth_service as auth
from services.history_service import get_stats

# Initialiser les listes de domaines (whitelist/blacklist) si la DB est vide
try:
    auth.initialiser_listes_domaines()
except Exception:
    pass

appliquer_theme()
appliquer_signature()

# ── Verrou : si non connecté, afficher l'écran d'auth ─────────────────────
if not est_connecte():
    ecran_authentification()

# ── Valeurs par défaut partagées ───────────────────────────────────────────
for cle, valeur in {
    "seuil_suspect": 0.825,
    "seuil_dangereux": 0.928,
    "action_config": "quarantaine",
    "gmail_connecte": False,
    "surveillance_active": False,
    "derniere_alerte": None,
}.items():
    st.session_state.setdefault(cle, valeur)

# ── Navigation selon le rôle ───────────────────────────────────────────────
# Pages disponibles pour TOUS les utilisateurs connectés
PAGES_USER = [
    st.Page("pages/01_#L01f3e0_Accueil.py",            title="Accueil",            icon="🏠"),
    st.Page("pages/02_#L01f4e5_Surveillance_Gmail.py",  title="Surveillance Gmail", icon="📬"),
    st.Page("pages/03_#L01f9ea_Test_Manuel.py",         title="Test Manuel",        icon="🧪"),
    st.Page("pages/04_#L01f4ca_Dashboard.py",           title="Dashboard",          icon="📊"),
    st.Page("pages/05_#L01f4dc_Historique.py",          title="Historique",         icon="📋"),
    st.Page("pages/06_#U2699#Ufe0f_Param#U00e8tres.py", title="Paramètres",        icon="⚙️"),
]

# Pages réservées aux admins
PAGES_ADMIN = [
    st.Page("pages/07_ADMIN_Security_Center.py",    title="Security Center",    icon="🔐"),
    st.Page("pages/08_ADMIN_Utilisateurs.py",       title="Utilisateurs",       icon="👥"),
    st.Page("pages/09_ADMIN_Administrateurs.py",    title="Administrateurs",    icon="🛡️"),
    st.Page("pages/10_ADMIN_Trusted_Domains.py",    title="Trusted Domains",    icon="🌐"),
    st.Page("pages/11_ADMIN_Fraudulent_Domains.py", title="Fraudulent Domains", icon="🚫"),
    st.Page("pages/12_ADMIN_Review_Detections.py",  title="Review Detections",  icon="🔍"),
    st.Page("pages/13_ADMIN_Explain_Detection.py",  title="Explain Detection",  icon="🧠"),
    st.Page("pages/14_ADMIN_Model_Monitoring.py",   title="Model Monitoring",   icon="📈"),
    st.Page("pages/15_ADMIN_Calibration.py",        title="Calibration",        icon="⚖️"),
    st.Page("pages/16_ADMIN_Attack_Campaigns.py",   title="Attack Campaigns",   icon="⚔️"),
    st.Page("pages/17_ADMIN_Security_Alerts.py",    title="Security Alerts",    icon="🚨"),
    st.Page("pages/18_ADMIN_Reports.py",            title="Reports",            icon="📄"),
    st.Page("pages/19_ADMIN_Audit_Logs.py",         title="Audit Logs",         icon="📋"),
]

# Construire la navigation selon le rôle
if est_admin():
    nav = st.navigation({
        "app": PAGES_USER,
        "Security Center": PAGES_ADMIN,
    })
else:
    nav = st.navigation({"app": PAGES_USER})

# ── Barre latérale ─────────────────────────────────────────────────────────
barre_utilisateur()

with st.sidebar:
    s1 = st.session_state["seuil_suspect"]
    s2 = st.session_state["seuil_dangereux"]
    if not est_admin():
        st.markdown(
            f'<div style="font-size:.82rem;color:{COULEURS["faible"]};line-height:2;">'
            f'Seuil à surveiller '
            f'<b class="mg-mono" style="color:{COULEURS["veille"]};">{s1:.2f}</b><br>'
            f'Seuil frauduleux '
            f'<b class="mg-mono" style="color:{COULEURS["menace"]};">{s2:.2f}</b></div>',
            unsafe_allow_html=True,
        )
        if st.session_state.get("surveillance_active"):
            st.markdown(pastille("Surveillance en cours", "violet"), unsafe_allow_html=True)

        alerte = st.session_state.get("derniere_alerte")
        if alerte:
            st.divider()
            st.markdown(
                f'<div class="mg-alert mg-alert-danger" style="font-size:.84rem;'
                f'padding:.9rem 1rem;">Dernier frauduleux<br>'
                f'<span class="mg-mono">{alerte["domaine"]}</span><br>'
                f'score {alerte["score"]:.3f}</div>',
                unsafe_allow_html=True,
            )

# ── Lancer la page active ──────────────────────────────────────────────────
nav.run()
