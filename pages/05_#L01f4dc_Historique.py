"""
pages/05_📜_Historique.py
===========================
Toutes les analyses conservées, avec filtres et réouverture du détail.

Correctif : la suppression passe par un indicateur de session au lieu d'un
popover imbriqué dans un bouton. L'ancienne construction disparaissait au
rechargement de la page, ce qui rendait la confirmation inatteignable.
"""

import pandas as pd
import streamlit as st

from services.history_service import charger_historique, effacer_historique
from services.quarantine_service import categoriser_email
from utils.display_result import afficher_resultat_complet
from utils.auth_ui import exiger_connexion, id_utilisateur
from utils.ui_helpers import (
    COULEURS,
    appliquer_signature,
    appliquer_theme,
    entete_page,
    titre_section,
)

appliquer_theme()
appliquer_signature()
exiger_connexion()

entete_page(
    titre="Toutes les décisions, rouvrables à tout moment",
    sous_titre="Chaque analyse est conservée avec son score, ses signaux et l'action "
               "appliquée. Le détail complet se rouvre en un clic.",
    surtitre="Historique",
    mot_accent="rouvrables à tout moment",
)

historique = charger_historique(id_utilisateur())

if not historique:
    st.markdown(
        '<div class="mg-carte"><h4>L\'historique est vide</h4>'
        '<p>Les analyses s\'y ajoutent automatiquement, qu\'elles viennent de la '
        'surveillance de la boîte ou d\'une saisie manuelle.</p></div>',
        unsafe_allow_html=True,
    )
    st.stop()

df = pd.DataFrame(historique)
if "categorie" not in df.columns:
    df["categorie"] = df["score_final"].apply(categoriser_email)
if "timestamp" in df.columns:
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["Date"] = df["timestamp"].dt.strftime("%d/%m %H:%M")

# ── Filtres ──────────────────────────────────────────────────────────────
f1, f2, f3, f4 = st.columns([1, 1, 1, 1.4])

decision = f1.selectbox("Décision", ["Toutes", "DANGEREUX", "SUSPECT", "LÉGITIME"],
                         format_func=lambda v: "FRAUDULEUX" if v == "DANGEREUX" else v)
domaines = ["Tous"] + sorted(df["domaine_expediteur"].dropna().unique().tolist())
domaine = f2.selectbox("Expéditeur", domaines)
sources = ["Toutes"] + sorted(df.get("source", pd.Series(dtype=str)).dropna().unique().tolist())
source = f3.selectbox("Origine", sources)
recherche = f4.text_input("Rechercher", placeholder="un domaine ou un objet")

filtre = df.copy()
if decision != "Toutes":
    filtre = filtre[filtre["categorie"] == decision]
if domaine != "Tous":
    filtre = filtre[filtre["domaine_expediteur"] == domaine]
if source != "Toutes" and "source" in filtre.columns:
    filtre = filtre[filtre["source"] == source]
if recherche:
    motif = recherche.lower()
    filtre = filtre[
        filtre["domaine_expediteur"].astype(str).str.lower().str.contains(motif)
        | filtre.get("sujet", pd.Series("", index=filtre.index)).astype(str).str.lower().str.contains(motif)
    ]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Analyses retenues", len(filtre))
c2.metric("Frauduleux", int((filtre["categorie"] == "DANGEREUX").sum()))
c3.metric("À surveiller", int((filtre["categorie"] == "SUSPECT").sum()))
c4.metric("Sans risque", int((filtre["categorie"] == "LÉGITIME").sum()))

# ── Tableau ──────────────────────────────────────────────────────────────
st.write("")
if filtre.empty:
    st.markdown(
        '<div class="mg-carte"><p>Aucune analyse ne correspond à ces filtres. '
        'Élargissez la recherche pour voir des résultats.</p></div>',
        unsafe_allow_html=True,
    )
    st.stop()

colonnes = [c for c in ["Date", "domaine_expediteur", "sujet", "score_final",
                        "categorie", "etage", "duree_analyse_ms",
                        "action_appliquee", "source"] if c in filtre.columns]
filtre = filtre.copy()
if "etage" in filtre.columns:
    filtre["etage"] = filtre["etage"].map({1: "listes / règle sûre", 2: "fusion"}).fillna("—")
if "categorie" in filtre.columns:
    filtre["categorie"] = filtre["categorie"].replace({"DANGEREUX": "FRAUDULEUX"})
tableau = filtre[colonnes].rename(columns={
    "domaine_expediteur": "Expéditeur", "sujet": "Objet", "score_final": "Score",
    "categorie": "Décision", "etage": "Décidé par", "duree_analyse_ms": "Durée (ms)",
    "action_appliquee": "Action", "source": "Origine",
}).sort_index(ascending=False)

TEINTES = {
    "DANGEREUX": f"background-color:{COULEURS['menace_clair']};color:#8E1F23;font-weight:700;",
    "FRAUDULEUX": f"background-color:{COULEURS['menace_clair']};color:#8E1F23;font-weight:700;",
    "SUSPECT": f"background-color:{COULEURS['veille_clair']};color:#8A5D07;font-weight:700;",
    "LÉGITIME": f"background-color:{COULEURS['sur_clair']};color:#0A6647;",
}

style = tableau.style
if "Décision" in tableau.columns:
    style = style.map(lambda v: TEINTES.get(str(v), ""), subset=["Décision"])
if "Score" in tableau.columns:
    seuil_s = st.session_state.get("seuil_suspect", 0.825)
    seuil_d = st.session_state.get("seuil_dangereux", 0.928)
    style = style.map(
        lambda v: f"color:{COULEURS['menace'] if v >= seuil_d else COULEURS['veille'] if v >= seuil_s else COULEURS['sur']};font-weight:700;",
        subset=["Score"],
    ).format({"Score": "{:.3f}"})

st.dataframe(style, width="stretch", height=380, hide_index=True)

# ── Réouverture d'une analyse ────────────────────────────────────────────
st.write("")
titre_section("Rouvrir une analyse")


def resumer(index):
    ligne = df.loc[index]
    marques = {"LÉGITIME": "sans risque", "SUSPECT": "à surveiller", "DANGEREUX": "menace"}
    return (f"{ligne.get('Date', '')} — {ligne.get('domaine_expediteur', '?')} — "
            f"{str(ligne.get('sujet', '(sans objet)'))[:40]} — "
            f"{marques.get(ligne.get('categorie'), '?')} {ligne.get('score_final', 0):.3f}")


choix = st.selectbox("Analyse", options=filtre.index.tolist(), format_func=resumer)

if choix is not None:
    entree = df.loc[choix].to_dict()
    if entree.get("texte_apercu"):
        with st.expander("Extrait du message"):
            st.text(str(entree["texte_apercu"])[:500])

    if isinstance(entree.get("scores_detail"), dict):
        afficher_resultat_complet(
            resultat=entree,
            domaine=entree.get("domaine_expediteur", ""),
            sujet=entree.get("sujet", ""),
            seuil_suspect=st.session_state.get("seuil_suspect", 0.825),
            seuil_dangereux=st.session_state.get("seuil_dangereux", 0.928),
            prefix=f"histo_{choix}",
            action=entree.get("action_appliquee", ""),
        )
    else:
        st.warning("Cette analyse a été enregistrée dans un format antérieur : "
                   "le détail des signaux n'est pas disponible.")

# ── Effacement ───────────────────────────────────────────────────────────
st.write("")
st.session_state.setdefault("confirmer_effacement", False)

if not st.session_state["confirmer_effacement"]:
    if st.button("Effacer tout l'historique"):
        st.session_state["confirmer_effacement"] = True
        st.rerun()
else:
    st.markdown(
        f'<div class="mg-alert mg-alert-warn">Les {len(historique)} analyses '
        f'enregistrées vont être supprimées définitivement.</div>',
        unsafe_allow_html=True,
    )
    oui, non = st.columns([1, 1])
    if oui.button("Supprimer définitivement", type="primary", width="stretch"):
        effacer_historique(id_utilisateur())
        st.session_state["confirmer_effacement"] = False
        st.rerun()
    if non.button("Annuler", width="stretch"):
        st.session_state["confirmer_effacement"] = False
        st.rerun()
