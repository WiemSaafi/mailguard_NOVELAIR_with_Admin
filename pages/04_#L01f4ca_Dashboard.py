"""
pages/04_📊_Dashboard.py
==========================
Vue d'ensemble des analyses : volumes, répartition, évolution des scores,
causes de détection et coût réel de l'analyse.

La logique de chargement et d'agrégation est celle d'origine. Seule la
présentation a été refaite.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from services.history_service import charger_historique, get_stats, moyenne_par_signal
from services.quarantine_service import categoriser_email
from utils.auth_ui import exiger_connexion, id_utilisateur
from utils.ui_helpers import (
    COULEURS,
    PALETTE_DECISION,
    appliquer_signature,
    appliquer_theme,
    entete_page,
    mise_en_page_plotly,
    titre_section,
)

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=10000, key="rafraichissement_tableau")
except ImportError:
    pass

appliquer_theme()
appliquer_signature()
exiger_connexion()

entete_page(
    titre="Ce que MailGuard a vu passer",
    sous_titre="Les chiffres se mettent à jour toutes les dix secondes pendant une "
               "surveillance active.",
    surtitre="Tableau de bord",
    mot_accent="a vu passer",
)

# ─── Chargement ───────────────────────────────────────────────────────────────
historique = charger_historique(id_utilisateur())
stats = get_stats(id_utilisateur())

if not historique:
    st.markdown(
        '<div class="mg-carte" style="max-width:640px;">'
        '<h4>Rien à afficher pour le moment</h4>'
        '<p>Passez par « Test Manuel » pour analyser un message précis, ou lancez la '
        'surveillance de la boîte. Les graphiques se construisent au fil des analyses.'
        '</p></div>',
        unsafe_allow_html=True,
    )
    st.stop()

df = pd.DataFrame(historique)
if "categorie" not in df.columns:
    df["categorie"] = df["score_final"].apply(lambda v: categoriser_email(v))
if "timestamp" in df.columns:
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

seuil_suspect = st.session_state.get("seuil_suspect", 0.825)
seuil_dangereux = st.session_state.get("seuil_dangereux", 0.928)

# ─── Chiffres clés ────────────────────────────────────────────────────────────
total = max(stats["total"], 1)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Messages analysés", stats["total"])
c2.metric("Frauduleux", stats["dangereux"], delta=f"{stats['dangereux'] / total * 100:.0f} %",
          delta_color="inverse")
c3.metric("Suspects", stats["suspects"], delta=f"{stats['suspects'] / total * 100:.0f} %",
          delta_color="off")
c4.metric("Légitimes", stats["legitimes"], delta=f"{stats['legitimes'] / total * 100:.0f} %")
c5.metric("Score moyen", f"{stats['score_moyen']:.3f}")

# ─── Où la décision a été prise ───────────────────────────────────────────────
# etage = 1 : décidé par les listes ou une règle sûre ; etage = 2 : décidé par le score de la fusion
if "etage" in df.columns:
    part1 = (df["etage"] == 1).mean() * 100
    n1, n2 = int((df["etage"] == 1).sum()), int((df["etage"] == 2).sum())

    titre_section("Où la décision a été prise")
    st.markdown(
        f'<div class="mg-carte">'
        f'<div style="display:flex;align-items:baseline;gap:1.4rem;flex-wrap:wrap;">'
        f'<div class="mg-mono" style="font-size:3.6rem;font-weight:700;'
        f'letter-spacing:-.06em;color:{COULEURS["violet"]};line-height:1;">'
        f'{part1:.0f} %</div>'
        f'<div style="flex:1;min-width:280px;">'
        f'<b style="font-size:1.05rem;">des messages sont décidés par les listes ou une règle sûre</b>'
        f'<p style="margin-top:.4rem;">Liste noire, liste blanche avec domaine prouvé, usurpation '
        f'd\'un domaine Nouvelair ou imitation d\'une marque. Les autres sont décidés par le '
        f'score de la fusion des cinq signaux.</p></div></div>'
        f'<div style="display:flex;gap:4px;margin-top:1.4rem;">'
        f'<div style="flex:{max(part1, 1):.0f};height:10px;border-radius:99px;'
        f'background:{COULEURS["violet"]};"></div>'
        f'<div style="flex:{max(100 - part1, 1):.0f};height:10px;border-radius:99px;'
        f'background:{COULEURS["filet"]};"></div></div>'
        f'<p style="margin-top:.7rem;font-size:.85rem;">{n1} par les listes ou les règles sûres, '
        f'{n2} par le score de la fusion.</p></div>',
        unsafe_allow_html=True,
    )

# ─── Répartition et évolution ─────────────────────────────────────────────────
titre_section("Répartition et évolution")
gauche, droite = st.columns(2, gap="large")

with gauche:
    st.markdown("**Décisions rendues**")
    figure = px.pie(df, names="categorie", hole=0.62, color="categorie",
                    color_discrete_map=PALETTE_DECISION)
    figure.update_traces(textposition="outside", textinfo="percent+label",
                         marker=dict(line=dict(color="#FFFFFF", width=3)))
    st.plotly_chart(mise_en_page_plotly(figure, 330, legende=False), width="stretch")

with droite:
    st.markdown("**Scores dans le temps**")
    ordonne = df.sort_values("timestamp") if "timestamp" in df.columns else df
    figure = px.scatter(
        ordonne, x="timestamp" if "timestamp" in df.columns else ordonne.index,
        y="score_final", color="categorie", color_discrete_map=PALETTE_DECISION,
    )
    figure.update_traces(marker=dict(size=12, line=dict(width=1.5, color="#FFFFFF")))
    figure.add_hrect(y0=seuil_dangereux, y1=1, fillcolor=COULEURS["menace"],
                     opacity=0.06, line_width=0)
    figure.add_hrect(y0=seuil_suspect, y1=seuil_dangereux, fillcolor=COULEURS["veille"],
                     opacity=0.08, line_width=0)
    figure.update_yaxes(range=[0, 1], title="Score de risque")
    figure.update_xaxes(title="")
    st.plotly_chart(mise_en_page_plotly(figure, 330), width="stretch")

# ─── Causes et expéditeurs ────────────────────────────────────────────────────
titre_section("Ce qui déclenche les détections")
gauche, droite = st.columns(2, gap="large")

with gauche:
    st.markdown("**Signaux ayant franchi le seuil**")
    libelles = {
        "domaine_bert": "Domaine trop proche d'un domaine réel",
        "contenu": "Texte reconnu comme du phishing",
        "authentification": "Authentification en défaut",
        "liens": "Lien trompeur",
        "domaine_randomforest": "Domaine douteux au registre",
    }
    comptes = {libelle: 0 for libelle in libelles.values()}
    for entree in historique:
        scores_d = entree.get("scores_detail", {})
        if isinstance(scores_d, dict):
            for cle, libelle in libelles.items():
                valeur = scores_d.get(cle)
                if valeur is not None and valeur >= 0.5:
                    comptes[libelle] += 1

    causes = (pd.DataFrame({"Cause": list(comptes), "Messages": list(comptes.values())})
              .sort_values("Messages"))
    figure = px.bar(causes, x="Messages", y="Cause", orientation="h")
    figure.update_traces(marker_color=COULEURS["violet"], marker_line_width=0, width=0.6)
    figure.update_yaxes(title="")
    st.plotly_chart(mise_en_page_plotly(figure, 330, legende=False), width="stretch")

with droite:
    st.markdown("**Expéditeurs les plus fréquents**")
    top = df["domaine_expediteur"].value_counts().head(8).reset_index()
    top.columns = ["Domaine", "Messages"]
    top["Décision dominante"] = top["Domaine"].map(
        lambda d: df.loc[df["domaine_expediteur"] == d, "categorie"].mode()[0]
    )
    figure = px.bar(top.sort_values("Messages"), x="Messages", y="Domaine",
                    orientation="h", color="Décision dominante",
                    color_discrete_map=PALETTE_DECISION)
    figure.update_traces(marker_line_width=0, width=0.6)
    figure.update_yaxes(title="")
    st.plotly_chart(mise_en_page_plotly(figure, 330), width="stretch")

# ─── Moyennes par signal ──────────────────────────────────────────────────────
titre_section("Score moyen de chaque signal",
              "Un signal dont la moyenne est élevée pèse lourd sur l'ensemble du trafic.")

etiquettes = {
    "domaine_bert": "S1 Domaine (CANINE)", "domaine_randomforest": "S2 Identité",
    "liens": "S3 Liens", "contenu": "S4 Contenu (e5)",
    "authentification": "S5 Authentification",
}
# Calcule par la base en une seule requete agregee, au lieu de parcourir
# tout l'historique en Python.
brutes = moyenne_par_signal(id_utilisateur())
moyennes = {libelle: brutes[cle] for cle, libelle in etiquettes.items()
            if cle in brutes}

if moyennes:
    for colonne, (libelle, valeur) in zip(st.columns(len(moyennes)), moyennes.items()):
        couleur = (COULEURS["menace"] if valeur >= 0.5
                   else COULEURS["veille"] if valeur >= 0.3 else COULEURS["sur"])
        with colonne:
            st.markdown(
                f'<div class="mg-signal"><div class="mg-signal-titre">{libelle}</div>'
                f'<div class="mg-signal-valeur" style="color:{couleur};">{valeur:.3f}</div>'
                f'<div class="mg-signal-piste"><div class="mg-signal-jauge" '
                f'style="width:{max(valeur * 100, 2):.1f}%;background:{couleur};"></div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )

# ─── Dernières menaces ────────────────────────────────────────────────────────
titre_section("Dernières menaces écartées")
menaces = [e for e in historique if e.get("categorie") == "DANGEREUX"]

if not menaces:
    st.markdown('<div class="mg-alert mg-alert-ok">Aucune menace enregistrée jusqu\'ici.</div>',
                unsafe_allow_html=True)
else:
    for menace in reversed(menaces[-5:]):
        horodatage = str(menace.get("timestamp", "")).replace("T", " ")[:16]
        st.markdown(
            f'<div class="mg-alert mg-alert-danger">'
            f'<b class="mg-mono">{menace.get("domaine_expediteur", "inconnu")}</b> — '
            f'score <span class="mg-mono">{menace.get("score_final", 0):.3f}</span> — '
            f'{horodatage}<br>{str(menace.get("sujet", "(sans objet)"))[:80]}<br>'
            f'{menace.get("action_appliquee", "aucune action")}</div>',
            unsafe_allow_html=True,
        )
