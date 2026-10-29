"""
pages/07_🔐_Security_Center.py
================================
Security Center — Tableau de bord global pour les administrateurs.
Accès réservé aux admins.
"""
import streamlit as st
from services import auth_service as auth
from services.database import (CATEGORIES_FRAUDE, Utilisateur, Analyse, Administrateur, DomainConfiance,
                               DomainFrauduleux, EtatAlerte, libelle_categorie, session as db_session)
from utils.auth_ui import exiger_admin, est_admin
from utils.ui_helpers import appliquer_theme, appliquer_signature, entete_page, titre_section, COULEURS
from sqlalchemy import func

exiger_admin()

entete_page(
    titre="MailGuard Security Center",
    sous_titre="Tableau de bord de sécurité et supervision globale",
)

# ── KPIs ──────────────────────────────────────────────────────────────────
titre_section("Indicateurs Clés de Sécurité (KPIs)")

with db_session() as s:
    nb_users = s.query(Utilisateur).count()
    nb_actifs = s.query(Utilisateur).filter(Utilisateur.statut == "active").count()
    nb_pending = s.query(Utilisateur).filter(Utilisateur.statut == "pending").count()
    nb_analyses = s.query(Analyse).count()
    nb_legitimes = s.query(Analyse).filter(Analyse.categorie == "LÉGITIME").count()
    nb_suspects = s.query(Analyse).filter(Analyse.categorie == "SUSPECT").count()
    nb_dangereux = s.query(Analyse).filter(Analyse.categorie.in_(CATEGORIES_FRAUDE)).count()
    score_moyen = s.query(func.avg(Analyse.score_final)).scalar() or 0.0
    nb_trusted = s.query(DomainConfiance).filter(DomainConfiance.statut == "approved").count()
    nb_fraud = s.query(DomainFrauduleux).filter(DomainFrauduleux.statut == "active").count()
    # Alertes actives : analyses suspectes ou frauduleuses non encore résolues
    resolues = {e.analyse_id for e in s.query(EtatAlerte).filter(EtatAlerte.statut == "resolue")}
    ids_alertes = [i for (i,) in s.query(Analyse.id)
                   .filter(Analyse.categorie.in_(CATEGORIES_FRAUDE + ("SUSPECT",)))]
    nb_alertes = sum(1 for i in ids_alertes if i not in resolues)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Utilisateurs", nb_users)
c2.metric("Comptes Actifs", nb_actifs)
c3.metric("Admins en Attente", nb_pending)
c4.metric("Alertes Actives", nb_alertes)

c5, c6, c7, c8 = st.columns(4)
c5.metric("Emails Analysés", nb_analyses)
c6.metric("Légitimes", nb_legitimes)
c7.metric("Suspects", nb_suspects)
c8.metric("Frauduleux", nb_dangereux,
          delta_color="inverse" if nb_dangereux > 0 else "normal")

c9, c10, c11 = st.columns(3)
c9.metric("Domaines de Confiance", nb_trusted)
c10.metric("Domaines Frauduleux", nb_fraud)
c11.metric("Score de Risque Moyen", f"{score_moyen:.3f}")

st.divider()

# ── Comptes en attente de validation ──────────────────────────────────────
titre_section("Comptes en attente de validation")

utilisateurs_pending = auth.lister_utilisateurs(statut_filtre="pending")

if not utilisateurs_pending:
    st.info("✅ Aucun compte en attente de validation.")
else:
    st.warning(f"⚠️ {len(utilisateurs_pending)} compte(s) à valider.")
    for u in utilisateurs_pending:
        with st.expander(f"📧 {u['nom']} — {u['email']}  (créé le {u['cree_le']})"):
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("✅ Activer", key=f"act_{u['id']}", type="primary"):
                    ok, msg = auth.activer_compte(u["email"])
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
            with col2:
                if st.button("🗑️ Supprimer", key=f"del_{u['id']}"):
                    ok, msg = auth.supprimer_compte_admin(u["email"])
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

st.divider()

# ── Dernières analyses ─────────────────────────────────────────────────────
titre_section("Dernières analyses (tous utilisateurs)")

with db_session() as s:
    dernieres = (s.query(Analyse, Utilisateur)
                 .join(Utilisateur, Analyse.utilisateur_id == Utilisateur.id, isouter=True)
                 .order_by(Analyse.horodatage.desc())
                 .limit(10).all())

if not dernieres:
    st.info("Aucune analyse enregistrée.")
else:
    for analyse, user in dernieres:
        categorie = libelle_categorie(analyse.categorie)
        couleur = {"FRAUDULEUX": "#FF4757", "SUSPECT": "#FFA502", "LÉGITIME": "#2ED573"}.get(
            categorie, "#ccc")
        user_label = user.nom if user else "?"
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:.8rem;padding:.5rem .8rem;'
            f'border-left:4px solid {couleur};background:#F8F9FA;border-radius:0 8px 8px 0;'
            f'margin-bottom:.4rem;">'
            f'<span style="font-weight:700;color:{couleur};">{categorie}</span>'
            f'<span style="font-family:monospace;">{analyse.domaine_expediteur}</span>'
            f'<span style="color:#666;">Score: {analyse.score_final:.3f}</span>'
            f'<span style="color:#999;font-size:.8rem;">{user_label} · {analyse.horodatage.strftime("%Y-%m-%d %H:%M") if analyse.horodatage else ""}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
