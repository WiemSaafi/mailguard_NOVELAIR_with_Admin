"""
pages/17_ADMIN_Security_Alerts.py
Alertes de sécurité — admin.

Une alerte = une analyse classée suspecte ou frauduleuse. Son suivi (vue,
résolue) est enregistré en base (table etats_alertes) : il survit à un
rafraîchissement de la page et il est partagé entre administrateurs.
"""
from datetime import datetime

import streamlit as st

from services.audit_service import acteur_courant, journaliser
from services.database import (CATEGORIES_FRAUDE, Analyse, EtatAlerte, libelle_categorie,
                               session as db_session)
from utils.auth_ui import exiger_admin
from utils.ui_helpers import entete_page

exiger_admin()

entete_page(
    titre="Alertes de sécurité",
    sous_titre="Suivi des messages suspects et frauduleux : nouvelle, vue, résolue",
)


def changer_etat(analyse_id: int, statut, domaine: str):
    """statut : « vue », « resolue », ou None pour rouvrir l'alerte."""
    with db_session() as s:
        e = s.query(EtatAlerte).filter_by(analyse_id=analyse_id).first()
        if statut is None:
            if e:
                s.delete(e)
        else:
            if e is None:
                e = EtatAlerte(analyse_id=analyse_id)
                s.add(e)
            e.statut, e.admin, e.maj_le = statut, acteur_courant(), datetime.now()
        s.commit()
    action = {"vue": "ALERT_VIEW", "resolue": "ALERT_RESOLVE", None: "ALERT_REOPEN"}[statut]
    journaliser(action, "alerte", str(analyse_id), domaine)


with db_session() as s:
    lignes = (s.query(Analyse)
              .filter(Analyse.categorie.in_(CATEGORIES_FRAUDE + ("SUSPECT",)))
              .order_by(Analyse.horodatage.desc()).limit(200).all())
    etats = {e.analyse_id: e for e in s.query(EtatAlerte)
             .filter(EtatAlerte.analyse_id.in_([a.id for a in lignes])).all()}
    alertes = [{
        "id": a.id, "domaine": a.domaine_expediteur, "score": a.score_final,
        "categorie": libelle_categorie(a.categorie),
        "horodatage": a.horodatage.strftime("%Y-%m-%d %H:%M") if a.horodatage else "",
        "sujet": a.sujet, "raisons": a.explication,
        # sévérité = décision du filtre (et non un ancien seuil fixe)
        "severite": "critique" if a.categorie in CATEGORIES_FRAUDE else "à surveiller",
        "statut": {"vue": "Vue", "resolue": "Résolue"}.get(etats[a.id].statut, "Nouvelle") if a.id in etats else "Nouvelle",
        "par": f"{etats[a.id].admin}, {etats[a.id].maj_le:%Y-%m-%d %H:%M}" if a.id in etats else "",
    } for a in lignes]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Alertes", len(alertes))
c2.metric("Nouvelles", sum(a["statut"] == "Nouvelle" for a in alertes))
c3.metric("Vues", sum(a["statut"] == "Vue" for a in alertes))
c4.metric("Résolues", sum(a["statut"] == "Résolue" for a in alertes))

cf1, cf2 = st.columns(2)
with cf1:
    filtre_statut = st.selectbox("Statut", ["Tous", "Nouvelle", "Vue", "Résolue"])
with cf2:
    filtre_sev = st.selectbox("Sévérité", ["Toutes", "critique", "à surveiller"])

filtrees = [a for a in alertes
            if (filtre_statut == "Tous" or a["statut"] == filtre_statut)
            and (filtre_sev == "Toutes" or a["severite"] == filtre_sev)]

if not filtrees:
    st.info("Aucune alerte ne correspond aux critères.")
for a in filtrees:
    icone = "🔴" if a["severite"] == "critique" else "🟡"
    with st.expander(f"{icone} {a['domaine']} — {a['categorie']} (score {a['score']:.3f}) — "
                     f"{a['statut']} — {a['horodatage']}"):
        st.write(f"**Objet :** {a['sujet'] or '(non renseigné)'}")
        if a["raisons"]:
            st.caption(a["raisons"])
        if a["par"]:
            st.caption(f"Dernière action : {a['par']}")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            if a["statut"] == "Nouvelle" and st.button("👁️ Marquer comme vue", key=f"vu_{a['id']}"):
                changer_etat(a["id"], "vue", a["domaine"])
                st.rerun()
        with col_b:
            if a["statut"] != "Résolue" and st.button("✅ Résoudre", key=f"res_{a['id']}"):
                changer_etat(a["id"], "resolue", a["domaine"])
                st.rerun()
        with col_c:
            if a["statut"] == "Résolue" and st.button("↩️ Rouvrir", key=f"reopen_{a['id']}"):
                changer_etat(a["id"], None, a["domaine"])
                st.rerun()
