"""
pages/16_⚔️_Attack_Campaigns.py
Détection et gestion des campagnes d'attaques groupées — admin.
"""
import streamlit as st
from collections import Counter
import json
from services.database import CATEGORIES_FRAUDE, Analyse, session as db_session
from utils.auth_ui import exiger_admin
from utils.ui_helpers import appliquer_theme, appliquer_signature, entete_page, titre_section

exiger_admin()

entete_page(
    titre="Attack Campaigns",
    sous_titre="Detect and manage grouped phishing/typosquatting attacks",
)

if st.button("🔍 Detect Campaigns", type="primary"):
    with st.spinner("Analyse des campagnes en cours…"):
        with db_session() as s:
            # Regrouper les domaines frauduleux par similarité (préfixe)
            fraudes = (s.query(Analyse.domaine_expediteur, Analyse.score_final,
                               Analyse.horodatage, Analyse.details_json)
                       .filter(Analyse.categorie.in_(CATEGORIES_FRAUDE + ("SUSPECT",)))
                       .order_by(Analyse.horodatage.desc())
                       .all())

        if not fraudes:
            st.info("Aucune détection frauduleuse trouvée pour analyser les campagnes.")
            st.session_state["campaigns"] = []
        else:
            # Une campagne = des messages qui visent la MÊME marque (imitation détectée par
            # CANINE sur l'expéditeur ou sur un lien) ; sinon, le même domaine enregistré.
            def cle_campagne(domaine, details_json):
                try:
                    d = json.loads(details_json or "{}")
                except ValueError:
                    d = {}
                s1 = d.get("domaine_bert", {}) or {}
                if s1.get("marque") and s1.get("score", 0) >= s1.get("seuil", 0.44):
                    return f"imite « {s1['marque']} »"
                for lien in d.get("liens", []) or []:
                    for r in lien.get("raisons", []):
                        if r.startswith("imite la marque "):
                            return f"imite « {r.split()[3]} »"
                parties = (domaine or "").lower().split(".")
                return ".".join(parties[-2:]) if len(parties) >= 2 else (domaine or "inconnu")

            groupes = {}
            for dom, score, ts, details in fraudes:
                groupes.setdefault(cle_campagne(dom, details), []).append(
                    {"domaine": dom, "score": score, "ts": ts.strftime("%Y-%m-%d %H:%M") if ts else ""})

            campagnes = [
                {"racine": r, "nb": len(lst), "domaines": lst,
                 "score_max": max(d["score"] for d in lst)}
                for r, lst in groupes.items()
            ]
            campagnes.sort(key=lambda x: x["nb"], reverse=True)
            st.session_state["campaigns"] = campagnes
            st.success(f"{len(campagnes)} groupe(s) de campagne détecté(s).")

campagnes = st.session_state.get("campaigns", None)

if campagnes is None:
    st.markdown(
        '<div style="color:#888;margin-top:2rem;">Cliquez sur '
        '« Detect Campaigns » pour lancer l\'analyse.</div>',
        unsafe_allow_html=True,
    )
elif not campagnes:
    st.info("Aucune campagne détectée.")
else:
    titre_section(f"{len(campagnes)} Campagne(s) détectée(s)")
    for camp in campagnes:
        risque = "🔴 ÉLEVÉ" if camp["score_max"] >= 0.928 else "🟡 MODÉRÉ"
        nb_dom = len({d["domaine"] for d in camp["domaines"]})
        with st.expander(f"{risque} {camp['racine']} — {camp['nb']} message(s), {nb_dom} domaine(s) — "
                         f"score max {camp['score_max']:.3f}"):
            for d in camp["domaines"]:
                st.markdown(
                    f'<div style="display:flex;gap:1rem;padding:.3rem 0;border-bottom:1px solid #eee;">'
                    f'<code style="flex:1;">{d["domaine"]}</code>'
                    f'<span style="color:#FF4757;font-weight:600;">Score: {d["score"]:.3f}</span>'
                    f'<span style="color:#888;font-size:.85rem;">{d["ts"]}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
