"""
pages/12_ADMIN_Review_Detections.py
Revue des détections (« human in the loop ») — admin uniquement.

L'administrateur donne son avis sur chaque analyse. Les avis sont enregistrés en
base (table qualifications) : ils mesurent les erreurs du filtre en exploitation
(faux positifs et faux négatifs) et serviront à réentraîner les modèles.
"""
from datetime import datetime

import pandas as pd
import streamlit as st

from services.audit_service import acteur_courant, journaliser
from services.database import (CATEGORIES_FRAUDE, Analyse, QualificationAnalyse,
                               libelle_categorie, session as db_session)
from utils.auth_ui import exiger_admin
from utils.ui_helpers import entete_page, titre_section

exiger_admin()

entete_page(
    titre="Revue des détections (human in the loop)",
    sous_titre="Validation par un humain des décisions du filtre : chaque avis est enregistré",
)

ICONES = {"FRAUDULEUX": "🔴", "SUSPECT": "🟡", "LÉGITIME": "🟢"}


def qualifier(analyse_id: int, qualification: str, domaine: str, decision: str):
    with db_session() as s:
        q = s.query(QualificationAnalyse).filter_by(analyse_id=analyse_id).first()
        if q is None:
            q = QualificationAnalyse(analyse_id=analyse_id)
            s.add(q)
        q.qualification, q.admin, q.qualifie_le = qualification, acteur_courant(), datetime.now()
        s.commit()
    journaliser("QUALIFICATION", "analyse", str(analyse_id),
                f"{domaine} : décision du filtre {decision}, avis de l'administrateur {qualification}")


# ── Filtres ────────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns([1, 1, 2])
with c1:
    categorie_filtre = st.selectbox("Décision du filtre", ["Toutes", "FRAUDULEUX", "SUSPECT", "LÉGITIME"],
                                    key="rev_cat")
with c2:
    etat_filtre = st.selectbox("Avis", ["Tous", "À qualifier", "Qualifiées"], key="rev_etat")
with c3:
    recherche_dom = st.text_input("Rechercher par domaine expéditeur", key="rev_dom")

# ── Chargement ─────────────────────────────────────────────────────────────
with db_session() as s:
    q = s.query(Analyse).order_by(Analyse.horodatage.desc())
    if categorie_filtre == "FRAUDULEUX":
        q = q.filter(Analyse.categorie.in_(CATEGORIES_FRAUDE))
    elif categorie_filtre != "Toutes":
        q = q.filter(Analyse.categorie == categorie_filtre)
    if recherche_dom:
        q = q.filter(Analyse.domaine_expediteur.ilike(f"%{recherche_dom}%"))
    analyses = q.limit(100).all()
    avis = {x.analyse_id: x for x in s.query(QualificationAnalyse)
            .filter(QualificationAnalyse.analyse_id.in_([a.id for a in analyses])).all()}
    data = [{
        "id": a.id, "domaine": a.domaine_expediteur, "score": a.score_final,
        "categorie": libelle_categorie(a.categorie),
        "horodatage": a.horodatage.strftime("%Y-%m-%d %H:%M") if a.horodatage else "",
        "sujet": a.sujet, "texte_apercu": a.texte_apercu, "nb_liens": a.nb_liens,
        "action_appliquee": a.action_appliquee, "explication": a.explication,
        "avis": avis[a.id].qualification if a.id in avis else "",
        "avis_par": avis[a.id].admin if a.id in avis else "",
        "avis_le": avis[a.id].qualifie_le.strftime("%Y-%m-%d %H:%M") if a.id in avis else "",
    } for a in analyses]
    # Bilan sur toutes les analyses qualifiées (pas seulement celles affichées)
    toutes = (s.query(Analyse.categorie, QualificationAnalyse.qualification)
              .join(QualificationAnalyse, QualificationAnalyse.analyse_id == Analyse.id).all())

if etat_filtre == "À qualifier":
    data = [d for d in data if not d["avis"]]
elif etat_filtre == "Qualifiées":
    data = [d for d in data if d["avis"]]

# ── Bilan : le filtre a-t-il eu raison ? ───────────────────────────────────
titre_section("Accord entre le filtre et l'administrateur")
if toutes:
    paires = [(libelle_categorie(c), q) for c, q in toutes]
    accord = sum(1 for c, q in paires if c == q)
    fp = sum(1 for c, q in paires if c != "LÉGITIME" and q == "LÉGITIME")
    fn = sum(1 for c, q in paires if c == "LÉGITIME" and q != "LÉGITIME")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Analyses qualifiées", len(paires))
    k2.metric("Accord", f"{accord / len(paires) * 100:.0f} %")
    k3.metric("Faux positifs", fp, help="Accusé par le filtre, légitime selon l'administrateur.")
    k4.metric("Faux négatifs", fn, help="Laissé passer par le filtre, dangereux selon l'administrateur.")
    st.dataframe(pd.crosstab(pd.Series([c for c, _ in paires], name="Décision du filtre"),
                             pd.Series([q for _, q in paires], name="Avis de l'administrateur")),
                 width="stretch")
else:
    st.info("Aucune analyse qualifiée pour l'instant.")

# ── Liste ──────────────────────────────────────────────────────────────────
titre_section("Analyses")
if not data:
    st.info("Aucune analyse ne correspond aux critères.")
for item in data:
    titre = (f"{ICONES.get(item['categorie'], '⚪')} {item['domaine']} — score {item['score']:.3f} "
             f"({item['categorie']}) — {item['horodatage']}"
             + (f"  ✔ avis : {item['avis']}" if item["avis"] else "  · à qualifier"))
    with st.expander(titre):
        c_info, c_action = st.columns([2, 1])
        with c_info:
            st.write(f"**Objet :** {item['sujet'] or '(non renseigné)'}")
            st.write(f"**Score :** {item['score']:.4f}  |  **Décision du filtre :** {item['categorie']}")
            st.write(f"**Liens :** {item['nb_liens']}  |  **Action appliquée :** {item['action_appliquee']}")
            if item["explication"]:
                st.info(item["explication"])
            if item["texte_apercu"]:
                st.caption(item["texte_apercu"][:400])
        with c_action:
            st.markdown("**Avis de l'administrateur**")
            b1, b2, b3 = st.columns(3)
            for colonne, (libelle, valeur) in zip((b1, b2, b3), [("✅ Légitime", "LÉGITIME"),
                                                                 ("⚠️ Suspect", "SUSPECT"),
                                                                 ("🚨 Fraude", "FRAUDULEUX")]):
                with colonne:
                    if st.button(libelle, key=f"q_{valeur}_{item['id']}"):
                        qualifier(item["id"], valeur, item["domaine"], item["categorie"])
                        st.rerun()
            if item["avis"]:
                ok = item["avis"] == item["categorie"]
                accord = "d'accord avec le filtre" if ok else "désaccord avec le filtre"
                (st.success if ok else st.warning)(
                    f"Avis : {item['avis']} ({accord}) — par {item['avis_par']}, le {item['avis_le']}")
