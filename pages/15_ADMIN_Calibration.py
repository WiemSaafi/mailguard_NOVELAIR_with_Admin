"""
pages/15_ADMIN_Calibration.py
Seuils de décision de la fusion — admin uniquement.

Les seuils ont été choisis sur la VALIDATION (notebook de la fusion) :
le plus petit seuil qui garde au plus 2 % de vrais mails accusés (suspect)
et au plus 0,5 % (frauduleux). On ne les recalibre PAS ici sur les décisions
de l'application elle-même : ce serait circulaire (le modèle se noterait
avec ses propres réponses).
"""
import json
import os
from datetime import datetime

import pandas as pd
import streamlit as st
from sqlalchemy import func

import mailguard_core as mg
from services.database import Analyse, session as db_session
from utils.auth_ui import exiger_admin
from utils.ui_helpers import COULEURS, entete_page, titre_section

exiger_admin()

entete_page(
    titre="Calibration des seuils",
    sous_titre="Seuils appris par la fusion, et réglage manuel si l'entreprise le demande",
)

chemin_config = mg.CHEMIN_CONFIG


def lire_config():
    if os.path.exists(chemin_config):
        with open(chemin_config, encoding="utf-8") as f:
            return json.load(f)
    return {}


def ecrire_config(cfg):
    with open(chemin_config, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


config = lire_config()
appris = mg._SEUILS_APPRIS or {"suspect": 0.825, "frauduleux": 0.928}

# ── Seuils actuels ─────────────────────────────────────────────────────────
titre_section("Seuils en service")
c1, c2, c3 = st.columns(3)
c1.metric("Seuil suspect", f"{mg.SEUIL_SUSPECT:.3f}",
          help="Au plus 2 % de vrais mails accusés sur la validation.")
c2.metric("Seuil frauduleux", f"{mg.SEUIL_FRAUDULEUX:.3f}",
          help="Au plus 0,5 % de vrais mails accusés sur la validation.")
c3.metric("Origine", "réglage manuel" if config.get("methode_calibration") == "manuel" else "appris")

st.markdown(
    f'<div class="mg-carte"><h4>Comment ces seuils ont été choisis</h4>'
    f'<p>Sur le jeu de validation (découpé par expéditeur, GroupKFold, pour éviter la fuite '
    f'de données), on prend le <b>plus petit seuil</b> qui accuse au plus 2 % des vrais mails : '
    f'c\'est le seuil suspect ({appris["suspect"]:.3f}). Même règle avec 0,5 % pour le seuil '
    f'frauduleux ({appris["frauduleux"]:.3f}). Un seuil plus bas attrape plus de phishing '
    f'(rappel ↑) mais accuse plus de vrais mails (faux positifs ↑).</p></div>',
    unsafe_allow_html=True,
)

st.markdown("**Seuils propres à chaque signal (fixes, choisis à l'entraînement)**")
st.dataframe(pd.DataFrame([
    {"Signal": "S1 Domaine (CANINE)", "Seuil": "0,44", "Effet": "imitation → règle sûre (frauduleux)"},
    {"Signal": "S2 Identité (Gradient Boosting)", "Seuil": "0,74", "Effet": "alerte, ou domaine < 30 jours"},
    {"Signal": "S3 Chemin des liens (Gradient Boosting)", "Seuil": "0,894", "Effet": "lien au chemin suspect"},
    {"Signal": "S4 Contenu (e5 + LR)", "Seuil": "0,391", "Effet": "texte de phishing"},
    {"Signal": "S5 Authentification", "Seuil": "veto", "Effet": "DMARC échoue sur un domaine Nouvelair"},
]), hide_index=True, width="stretch")

st.divider()

# ── Répartition des scores observés ────────────────────────────────────────
titre_section("Scores observés dans l'application",
              "Pour voir combien de messages changeraient de catégorie avec d'autres seuils.")
with db_session() as s:
    scores = [v for (v,) in s.query(Analyse.score_final).filter(Analyse.etage == 2).all()]
if scores:
    serie = pd.Series(scores)
    st.bar_chart(pd.cut(serie, bins=[i / 20 for i in range(21)], include_lowest=True)
                 .value_counts(sort=False).rename(lambda iv: f"{iv.left:.2f}").rename("messages"))
    st.caption(f"{len(scores)} messages décidés par la fusion. Au-dessus de {mg.SEUIL_SUSPECT:.3f} : "
               f"{(serie >= mg.SEUIL_SUSPECT).sum()} · au-dessus de {mg.SEUIL_FRAUDULEUX:.3f} : "
               f"{(serie >= mg.SEUIL_FRAUDULEUX).sum()}.")
else:
    st.info("Pas encore de message décidé par la fusion.")

st.divider()

# ── Réglage manuel ─────────────────────────────────────────────────────────
titre_section("Réglage manuel (à justifier)")
with st.form("seuils_manuels"):
    col1, col2 = st.columns(2)
    nouveau_s = col1.number_input("Seuil suspect", 0.50, 0.99, float(mg.SEUIL_SUSPECT), 0.005, format="%.3f")
    nouveau_f = col2.number_input("Seuil frauduleux", 0.50, 1.00, float(mg.SEUIL_FRAUDULEUX), 0.005, format="%.3f")
    raison = st.text_input("Raison de la modification")
    appliquer = st.form_submit_button("💾 Appliquer", type="primary")
    revenir = st.form_submit_button("↩ Revenir aux seuils appris")

if appliquer:
    if not raison:
        st.warning("Indiquez une raison avant d'appliquer.")
    elif nouveau_f < nouveau_s:
        st.error("Le seuil frauduleux doit rester au-dessus du seuil suspect.")
    else:
        cfg = lire_config()
        cfg.update({"SEUIL_SUSPECT_FUSION": round(nouveau_s, 4), "SEUIL_FRAUDULEUX_FUSION": round(nouveau_f, 4),
                    "SEUIL_DECISION": round(nouveau_f, 4), "methode_calibration": "manuel",
                    "date_derniere_modif": datetime.now().strftime("%Y-%m-%d %H:%M"), "raison_modif": raison})
        ecrire_config(cfg)
        mg.changer_seuils_fusion(nouveau_s, nouveau_f)
        from services.audit_service import journaliser
        journaliser("THRESHOLD_CHANGE", "seuil", "fusion",
                    f"suspect {nouveau_s:.3f}, frauduleux {nouveau_f:.3f} — raison : {raison}")
        st.success(f"Seuils appliqués : suspect {nouveau_s:.3f} · frauduleux {nouveau_f:.3f}.")
        st.rerun()

if revenir:
    cfg = lire_config()
    cfg.update({"SEUIL_SUSPECT_FUSION": appris["suspect"], "SEUIL_FRAUDULEUX_FUSION": appris["frauduleux"],
                "SEUIL_DECISION": appris["frauduleux"],
                "methode_calibration": "validation (notebook de la fusion)",
                "date_derniere_modif": datetime.now().strftime("%Y-%m-%d %H:%M")})
    ecrire_config(cfg)
    mg.changer_seuils_fusion(None, None)
    from services.audit_service import journaliser
    journaliser("THRESHOLD_CHANGE", "seuil", "fusion",
                f"retour aux seuils appris ({appris['suspect']:.3f} / {appris['frauduleux']:.3f})")
    st.success("Seuils appris rétablis.")
    st.rerun()

st.markdown(
    f'<p style="font-size:.84rem;color:{COULEURS["faible"]};">Les préférences de chaque '
    f'utilisateur (page Paramètres) peuvent encore déplacer ses propres seuils d\'affichage ; '
    f'les seuils ci-dessus sont ceux du moteur.</p>',
    unsafe_allow_html=True,
)
