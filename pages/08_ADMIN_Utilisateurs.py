"""
pages/08_👥_Utilisateurs.py
============================
Gestion des utilisateurs — réservé aux administrateurs.
"""
import streamlit as st
from services import auth_service as auth
from utils.auth_ui import exiger_admin
from utils.ui_helpers import appliquer_theme, appliquer_signature, entete_page, titre_section

exiger_admin()

entete_page(
    titre="Gestion des Utilisateurs",
    sous_titre="Supervision des comptes utilisateurs et volumétrie d'analyse",
)

# ── Filtres ────────────────────────────────────────────────────────────────
col_f1, col_f2 = st.columns([1, 2])
with col_f1:
    statut_filtre = st.selectbox("Statut", ["Tous", "En attente", "Actifs", "Suspendus"],
                                  key="filtre_statut_users")
with col_f2:
    recherche = st.text_input("Rechercher un utilisateur (email / nom)", key="recherche_user")

map_statut = {"Tous": "all", "En attente": "pending", "Actifs": "active", "Suspendus": "suspended"}
utilisateurs = auth.lister_utilisateurs(statut_filtre=map_statut[statut_filtre])

if recherche:
    r = recherche.lower()
    utilisateurs = [u for u in utilisateurs if r in u["email"].lower() or r in u["nom"].lower()]

# ── Tableau ────────────────────────────────────────────────────────────────
import pandas as pd

if utilisateurs:
    df = pd.DataFrame(utilisateurs)[["id", "nom", "email", "cree_le", "derniere_connexion", "nb_analyses"]]
    df.columns = ["ID", "Nom", "Email", "Date création", "Dernière connexion", "Analyses"]
    st.dataframe(df, width="stretch", hide_index=True)
else:
    st.info("Aucun utilisateur trouvé.")

st.divider()

# ── Fiches détaillées ──────────────────────────────────────────────────────
titre_section("Fiches Détaillées")

for u in utilisateurs:
    badge_statut = {
        "active": "🟢 Actif",
        "pending": "🟡 En attente",
        "suspended": "🔴 Suspendu",
    }.get(u["statut"], u["statut"])

    with st.expander(f"👤 {u['nom']} — {u['email']}  ({u['nb_analyses']} analyses)"):
        c1, c2, c3 = st.columns(3)
        c1.write(f"**ID :** {u['id']}")
        c1.write(f"**Email :** {u['email']}")
        c1.write(f"**Nom :** {u['nom']}")
        c2.write(f"**Statut :** {badge_statut}")
        c2.write(f"**Créé le :** {u['cree_le']}")
        c2.write(f"**Dernière connexion :** {u['derniere_connexion']}")
        c3.write(f"**Analyses :** {u['nb_analyses']}")

        st.markdown("---")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            if u["statut"] == "pending":
                if st.button("✅ Activer", key=f"act_{u['id']}"):
                    ok, msg = auth.activer_compte(u["email"])
                    st.success(msg) if ok else st.error(msg)
                    st.rerun()
        with col_b:
            if u["statut"] == "active":
                if st.button("⏸️ Suspendre", key=f"sus_{u['id']}"):
                    ok, msg = auth.suspendre_compte(u["email"])
                    st.success(msg) if ok else st.error(msg)
                    st.rerun()
            elif u["statut"] == "suspended":
                if st.button("▶️ Réactiver", key=f"react_{u['id']}"):
                    ok, msg = auth.activer_compte(u["email"])
                    st.success(msg) if ok else st.error(msg)
                    st.rerun()
        with col_c:
            if st.button("🗑️ Supprimer", key=f"del_{u['id']}"):
                ok, msg = auth.supprimer_compte_admin(u["email"])
                st.success(msg) if ok else st.error(msg)
                st.rerun()
