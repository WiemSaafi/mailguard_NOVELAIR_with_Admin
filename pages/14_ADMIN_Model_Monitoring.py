"""
pages/14_ADMIN_Model_Monitoring.py
Vue d'ensemble des modèles MailGuard (5 signaux + fusion) — admin uniquement.
"""
import pandas as pd
import streamlit as st
from sqlalchemy import func

import mailguard_core as mg
from services.database import Analyse, ScoreSignal, session as db_session
from utils.auth_ui import exiger_admin
from utils.ui_helpers import COULEURS, entete_page, titre_section

exiger_admin()

entete_page(
    titre="Model Monitoring",
    sous_titre="Les cinq signaux, la fusion et leur état sur ce serveur",
)

# ── État du moteur ─────────────────────────────────────────────────────────
etat = mg.etat_modeles()
if etat.get("charges"):
    st.markdown(
        f'<div class="mg-alert mg-alert-ok">✅ <b>Moteur MailGuard chargé</b> en '
        f'{etat["duree_chargement_s"]} s sur <b>{etat["device"]}</b> '
        f'(processus {etat["pid"]}). Liste blanche : {etat["liste_blanche"]} entrées · '
        f'liste noire : {etat["liste_noire"]} entrées.</div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f'<div class="mg-alert mg-alert-danger">Moteur non chargé : '
        f'{etat.get("erreur") or "dossier des modèles absent"}<br>'
        f'Dossier attendu : <span class="mg-mono">{etat.get("dossier")}</span></div>',
        unsafe_allow_html=True,
    )

# ── Les cinq signaux ───────────────────────────────────────────────────────
titre_section("Les cinq signaux et la fusion",
              "Chaque signal a le modèle adapté à sa donnée et son propre seuil.")

SIGNAUX = [
    ("S1", "Domaine", "CANINE (caractères)", "0,44", "imitation d'une marque → règle sûre"),
    ("S2", "Identité", "Gradient Boosting monotone", "0,74", "+ règle « moins de 30 jours »"),
    ("S3", "Liens", "règles + GB du chemin", "0,894", "S1 et S2 appliqués au domaine du lien"),
    ("S4", "Contenu", "multilingual-e5 + LR", "0,391", "texte français, anglais, arabe"),
    ("S5", "Authentification", "GB sur 17 indices", "veto", "DMARC échoue sur Nouvelair → frauduleux"),
]
for col, (code, nom, modele, seuil, note) in zip(st.columns(5), SIGNAUX):
    with col:
        st.markdown(
            f'<div class="mg-carte" style="text-align:center;border-top:3px solid {COULEURS["violet"]};">'
            f'<div style="font-weight:800;font-size:1.3rem;">{code}</div>'
            f'<div style="font-weight:700;margin:.2rem 0;">{nom}</div>'
            f'<div style="font-size:.82rem;color:{COULEURS["attenue"]};">{modele}</div>'
            f'<div class="mg-mono" style="margin:.4rem 0;font-weight:700;">seuil {seuil}</div>'
            f'<div style="font-size:.76rem;color:{COULEURS["faible"]};">{note}</div></div>',
            unsafe_allow_html=True,
        )

st.write("")
st.markdown(
    f'<p style="font-size:.86rem;color:{COULEURS["attenue"]};">'
    f'<b>Cascade :</b> liste noire → liste blanche (seulement si le domaine est prouvé) → '
    f'règles sûres (S5 veto, S1 imitation) → score de la fusion → raisons. '
    f'<b>Seuils de la fusion :</b> suspect ≥ {mg.SEUIL_SUSPECT:.3f} · frauduleux ≥ {mg.SEUIL_FRAUDULEUX:.3f}.</p>',
    unsafe_allow_html=True,
)

# ── Poids appris ───────────────────────────────────────────────────────────
titre_section("Poids appris par la fusion (régression logistique)")
poids = mg.poids_fusion()
if poids:
    constante = poids.pop("constante", None)
    tableau = (pd.DataFrame([{"Indice": k, "Poids": v} for k, v in poids.items()])
               .sort_values("Poids", ascending=False))
    st.bar_chart(tableau.set_index("Indice"), horizontal=True, height=320)
    st.caption(f"Constante (intercept) : {constante}. Un poids négatif fait baisser le score : "
               "l'indice « lien imite une marque » est déjà couvert par les règles sûres.")
else:
    st.info("Les poids s'affichent quand le moteur est chargé.")

st.divider()

# ── Statistiques d'analyse ─────────────────────────────────────────────────
titre_section("Statistiques des analyses")

with db_session() as s:
    total = s.query(func.count(Analyse.id)).scalar() or 0
    score_moy = s.query(func.avg(Analyse.score_final)).scalar() or 0.0
    par_cat = s.query(Analyse.categorie, func.count(Analyse.id)).group_by(Analyse.categorie).all()
    duree_moy = s.query(func.avg(Analyse.duree_analyse_ms)).scalar() or 0.0
    par_etage = dict(s.query(Analyse.etage, func.count(Analyse.id)).group_by(Analyse.etage).all())
    moyennes = s.query(ScoreSignal.signal, func.avg(ScoreSignal.valeur)).group_by(ScoreSignal.signal).all()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total analyses", total)
c2.metric("Score moyen", f"{score_moy:.3f}")
c3.metric("Durée moy. (ms)", f"{duree_moy:.0f}")
c4.metric("Décidés par listes / règles", par_etage.get(1, 0),
          help="Les autres sont décidés par le score de la fusion.")

LIBELLES = {"DANGEREUX": "FRAUDULEUX"}
for cat, nb in par_cat:
    pct = (nb / total * 100) if total else 0
    st.progress(pct / 100, text=f"{LIBELLES.get(cat, cat)} : {nb} ({pct:.1f} %)")

if moyennes:
    st.markdown("**Score moyen par signal**")
    noms = mg.NOMS_SIGNAUX
    st.dataframe(pd.DataFrame([{"Signal": noms.get(k, k), "Moyenne": round(v or 0, 3)}
                               for k, v in moyennes]), hide_index=True, width="stretch")
