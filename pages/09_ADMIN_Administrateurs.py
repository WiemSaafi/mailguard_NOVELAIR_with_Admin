"""
pages/09_🛡️_Administrateurs.py
================================
Gestion des administrateurs MailGuard.
Réservé aux administrateurs connectés.
"""
import streamlit as st
from services import auth_service as auth
from utils.auth_ui import exiger_admin, utilisateur_actuel
from utils.ui_helpers import appliquer_theme, appliquer_signature, entete_page

exiger_admin()

admin_courant = utilisateur_actuel()

entete_page(
    titre="Administrator Management",
    sous_titre="Administrateurs",
)

# ── Créer un nouvel admin ──────────────────────────────────────────────────
with st.expander("➕ + New Administrator"):
    with st.form("nouveau_admin"):
        col1, col2 = st.columns(2)
        with col1:
            new_email = st.text_input("Email", placeholder="admin@nouvelair.com")
            new_nom = st.text_input("Nom", placeholder="Prénom Nom")
        with col2:
            new_mdp = st.text_input("Mot de passe", type="password",
                                     help="Au moins 8 caractères, une lettre et un chiffre.")
            new_mdp2 = st.text_input("Confirmer le mot de passe", type="password")
        submit = st.form_submit_button("Créer l'administrateur", type="primary")

    if submit:
        if not new_email or not new_mdp:
            st.error("Email et mot de passe sont requis.")
        elif new_mdp != new_mdp2:
            st.error("Les mots de passe ne correspondent pas.")
        else:
            ok, msg = auth.creer_admin(new_email, new_mdp, new_nom)
            st.success(msg) if ok else st.error(msg)
            if ok:
                st.rerun()

# ── Filtre ─────────────────────────────────────────────────────────────────
statut_filtre = st.selectbox("Status Filter", ["All", "active", "suspended"],
                              format_func=lambda x: x.capitalize() if x != "All" else "All")
map_f = {"All": "all", "active": "active", "suspended": "suspended"}
admins = auth.lister_admins(statut_filtre=map_f[statut_filtre])

st.markdown(f"**{len(admins)} administrateur(s) trouvé(s)**")

# ── Liste des admins ───────────────────────────────────────────────────────
for a in admins:
    badge = "🟢" if a["statut"] == "active" else "🔴"
    est_moi = a["email"] == admin_courant["email"]
    label = f"{a['nom']} ({a['email']}) - Status: {a['statut']}"
    if est_moi:
        label += "  ← vous"

    with st.expander(f"{badge} {label}"):
        c1, c2 = st.columns(2)
        c1.write(f"**Email :** {a['email']}")
        c1.write(f"**Nom :** {a['nom']}")
        c1.write(f"**Statut :** {a['statut']}")
        c2.write(f"**Créé le :** {a['cree_le']}")
        c2.write(f"**Dernière connexion :** {a['derniere_connexion']}")

        if not est_moi:
            st.markdown("---")
            col_a, col_b = st.columns(2)
            with col_a:
                if a["statut"] == "active":
                    if st.button("⏸️ Suspendre", key=f"sus_a_{a['id']}"):
                        ok, msg = auth.changer_statut_admin(a["email"], "suspended")
                        st.success(msg) if ok else st.error(msg)
                        st.rerun()
                else:
                    if st.button("▶️ Réactiver", key=f"act_a_{a['id']}"):
                        ok, msg = auth.changer_statut_admin(a["email"], "active")
                        st.success(msg) if ok else st.error(msg)
                        st.rerun()
            with col_b:
                if st.button("🗑️ Supprimer", key=f"del_a_{a['id']}"):
                    ok, msg = auth.supprimer_admin(a["email"], admin_courant["email"])
                    st.success(msg) if ok else st.error(msg)
                    st.rerun()
        else:
            st.info("C'est votre propre compte. Vous ne pouvez pas le modifier ici.")
