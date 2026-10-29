"""
app_dashboard.py
=================
Dashboard MailGuard — vue temps réel.

Lancement :
    streamlit run app_dashboard.py

Fonctionne en tandem avec gmail_watcher.py (lancé séparément dans un
autre terminal) : le watcher écrit dans "historique_analyses.json",
ce dashboard le relit automatiquement et affiche tout en direct.
"""

import os
import json
import time
from datetime import datetime

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

import mailguard_core as mg  # nécessaire pour permettre les tests manuels

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_DISPONIBLE = True
except ImportError:
    AUTOREFRESH_DISPONIBLE = False

HISTORIQUE_PATH = os.path.join(mg.BASE_DIR, "historique_analyses.json")

st.set_page_config(page_title="MailGuard — Dashboard temps réel", page_icon="🛡️", layout="wide")

# ---------------------------------------------------------------------
# STYLE
# ---------------------------------------------------------------------
st.markdown("""
<style>
.big-badge {
    font-size: 1.4rem; font-weight: 700; padding: 0.6rem 1.2rem;
    border-radius: 0.6rem; display: inline-block; text-align: center;
}
.badge-faible  { background:#E4F8F0; color:#0A7551; }
.badge-modere  { background:#FEF4E4; color:#95610A; }
.badge-eleve   { background:#FFECEE; color:#A32029; }
.signal-card {
    background:#101436; border:1px solid #101436; border-radius:0.5rem;
    padding:0.8rem; text-align:center;
}
.signal-ok  { border-left: 5px solid #12B981; }
.signal-bad { border-left: 5px solid #FF4757; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------
# UTILITAIRES
# ---------------------------------------------------------------------
def charger_historique():
    if os.path.exists(HISTORIQUE_PATH):
        try:
            with open(HISTORIQUE_PATH, encoding="utf-8") as f:
                data = json.load(f)
            return pd.DataFrame(data) if data else pd.DataFrame()
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def badge_html(niveau):
    if "ÉLEVÉ" in niveau:
        classe = "badge-eleve"
    elif "MODÉRÉ" in niveau:
        classe = "badge-modere"
    else:
        classe = "badge-faible"
    return f'<div class="big-badge {classe}">{niveau}</div>'


def gauge_score(score, seuil_decision):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number={"valueformat": ".3f"},
        gauge={
            "axis": {"range": [0, 1]},
            "bar": {"color": "#E7EAF5"},
            "steps": [
                {"range": [0, seuil_decision * 0.5], "color": "#E4F8F0"},
                {"range": [seuil_decision * 0.5, seuil_decision], "color": "#FEF4E4"},
                {"range": [seuil_decision, 1], "color": "#FFECEE"},
            ],
            "threshold": {"line": {"color": "black", "width": 3}, "value": seuil_decision},
        },
    ))
    fig.update_layout(height=220, margin=dict(l=20, r=20, t=20, b=10))
    return fig


def afficher_pipeline(resultat, cle_prefix=""):
    """Affiche le détail signal par signal, façon 'sous le capot'."""
    scores = {k: v for k, v in (resultat.get("scores_detail") or {}).items() if v is not None}
    details = resultat.get("details", {})
    labels = {
        "domaine_bert": "🔎 S1 Domaine (CANINE)",
        "domaine_randomforest": "🪪 S2 Identité",
        "liens": "🔗 S3 Liens",
        "contenu": "✉️ S4 Contenu (e5)",
        "authentification": "🔐 S5 Auth (SPF/DKIM/DMARC)",
    }
    seuils = {"domaine_bert": 0.44, "domaine_randomforest": 0.74, "liens": 0.894,
              "contenu": 0.391, "authentification": 0.5}
    if scores:
        cols = st.columns(len(scores))
        for i, (signal, valeur) in enumerate(scores.items()):
            suspect = valeur >= seuils.get(signal, 0.5)
            classe = "signal-bad" if suspect else "signal-ok"
            icone = "🚩" if suspect else "✅"
            with cols[i]:
                st.markdown(
                    f'<div class="signal-card {classe}"><b>{labels.get(signal, signal)}</b><br>'
                    f'{icone} score = {valeur}</div>', unsafe_allow_html=True,
                )

    with st.expander("🔍 Voir le détail complet de chaque signal (comment le modèle a décidé)"):
        if "domaine_bert" in details:
            d = details["domaine_bert"]
            st.write(f"**S1 Domaine (CANINE)** — score d'imitation `{d.get('score')}`, "
                     f"marque la plus proche : `{d.get('marque') or '—'}` → {d.get('verdict')}")
        if "domaine_randomforest" in details:
            rf = details["domaine_randomforest"]
            if rf.get("age_jours") is not None:
                st.write(f"**S2 Identité** — âge du domaine : `{rf['age_jours']} jours`, "
                         f"alerte : `{rf.get('alerte')}`")
            else:
                st.write(f"**S2 Identité** — {rf.get('note', 'signal muet')}")
        if details.get("liens"):
            st.write("**S3 Liens analysés :**")
            for l in details["liens"]:
                st.write(f"- `{l['url']}` — {'🚩 suspect' if l['suspect'] else '✅ ok'} ({', '.join(l['raisons'])})")
        elif "liens" in details:
            st.write("**S3 Liens :** aucun lien dans cet email.")
        if "contenu" in details:
            c = details["contenu"]
            if c.get("probabilite") is not None:
                st.write(f"**S4 Contenu (e5)** — langue détectée : `{c.get('langue_detectee', '?')}`, "
                         f"probabilité de phishing = `{c['probabilite']}`")
            else:
                st.write(f"**S4 Contenu :** {c.get('note') or 'non analysé'}")
        if "authentification" in details:
            a = details["authentification"]
            st.write(f"**S5 Authentification :** SPF=`{a['spf']}` · DKIM=`{a['dkim']}` · DMARC=`{a['dmarc']}`")

    st.info(f"💡 **{resultat['explication']}** ({resultat.get('signaux_calcules', 0)} signaux calculés)")


# ---------------------------------------------------------------------
# EN-TÊTE
# ---------------------------------------------------------------------
st.title("🛡️ MailGuard — Détection de phishing en temps réel")
st.caption("Cascade : listes → règles sûres → fusion des 5 signaux (CANINE · identité · liens · e5 · authentification)")

if AUTOREFRESH_DISPONIBLE:
    st_autorefresh(interval=4000, key="refresh_dashboard")
else:
    st.warning("⚡ Installe `streamlit-autorefresh` (`pip install streamlit-autorefresh`) pour un rafraîchissement automatique fluide.")

df = charger_historique()

tab_live, tab_historique, tab_stats, tab_manuel = st.tabs(
    ["🔴 En direct", "📜 Historique", "📊 Statistiques", "🧪 Tester un email manuellement"]
)

# ---------------------------------------------------------------------
# ONGLET 1 — EN DIRECT
# ---------------------------------------------------------------------
with tab_live:
    if not os.path.exists(HISTORIQUE_PATH):
        st.info("⏳ En attente du premier email... Assure-toi que `gmail_watcher.py` tourne bien "
                "dans un autre terminal (`python gmail_watcher.py`).")
    elif df.empty:
        st.info("⏳ Aucun email analysé pour l'instant. Envoie-toi un email de test pour voir "
                "le pipeline s'activer en direct !")
    else:
        dernier = df.iloc[-1].to_dict()
        st.subheader(f"📩 Dernier email analysé — {dernier['domaine_expediteur']}")

        c1, c2 = st.columns([2, 1])
        with c1:
            st.write(f"**Sujet :** {dernier.get('sujet', '(sans sujet)')}")
            st.write(f"**Aperçu :** {dernier.get('texte_apercu', '')[:200]}...")
            st.write(f"**Reçu à :** {dernier['timestamp']}")
            st.write(f"**Temps d'analyse :** {dernier.get('duree_analyse_ms', '?')} ms")
            st.markdown(badge_html(dernier["niveau"]), unsafe_allow_html=True)
        with c2:
            st.plotly_chart(gauge_score(dernier["score_final"], mg.SEUIL_DECISION), use_container_width=True)

        st.divider()
        st.subheader("🔬 Ce qui se passe dans le modèle")
        afficher_pipeline(dernier)

        st.divider()
        st.caption(f"🕒 Dashboard actualisé automatiquement — {len(df)} email(s) analysé(s) au total.")

# ---------------------------------------------------------------------
# ONGLET 2 — HISTORIQUE
# ---------------------------------------------------------------------
with tab_historique:
    if df.empty:
        st.info("Aucun historique pour le moment.")
    else:
        colf1, colf2, colf3 = st.columns(3)
        with colf1:
            niveaux = ["Tous"] + sorted(df["niveau"].unique().tolist())
            filtre_niveau = st.selectbox("Filtrer par verdict", niveaux)
        with colf2:
            domaines = ["Tous"] + sorted(df["domaine_expediteur"].unique().tolist())
            filtre_domaine = st.selectbox("Filtrer par domaine", domaines)
        with colf3:
            recherche = st.text_input("Recherche dans le sujet")

        df_filtre = df.copy()
        if filtre_niveau != "Tous":
            df_filtre = df_filtre[df_filtre["niveau"] == filtre_niveau]
        if filtre_domaine != "Tous":
            df_filtre = df_filtre[df_filtre["domaine_expediteur"] == filtre_domaine]
        if recherche:
            df_filtre = df_filtre[df_filtre["sujet"].str.contains(recherche, case=False, na=False)]

        st.dataframe(
            df_filtre[["timestamp", "domaine_expediteur", "sujet", "score_final", "niveau", "etage", "duree_analyse_ms"]]
            .sort_values("timestamp", ascending=False),
            use_container_width=True, height=400,
        )

        st.subheader("🔍 Inspecter un email de l'historique")
        idx_choisi = st.selectbox(
            "Choisir un email", df_filtre.index[::-1],
            format_func=lambda i: f"{df.loc[i,'timestamp']} — {df.loc[i,'domaine_expediteur']} — {df.loc[i,'niveau']}",
        )
        if idx_choisi is not None:
            afficher_pipeline(df.loc[idx_choisi].to_dict(), cle_prefix=str(idx_choisi))

# ---------------------------------------------------------------------
# ONGLET 3 — STATISTIQUES
# ---------------------------------------------------------------------
with tab_stats:
    if df.empty:
        st.info("Pas encore assez de données pour des statistiques.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Emails analysés", len(df))
        c2.metric("🔴 Risque élevé", int((df["niveau"].str.contains("ÉLEVÉ")).sum()))
        c3.metric("Score moyen", f"{df['score_final'].mean():.3f}")
        pct_etage1 = (df["etage"] == 1).mean() * 100
        c4.metric("⚡ Décidés par listes / règles", f"{pct_etage1:.0f}%",
                   help="% de cas décidés par la liste noire, la liste blanche prouvée ou une règle sûre")

        colg1, colg2 = st.columns(2)
        with colg1:
            st.subheader("Répartition des verdicts")
            fig = px.pie(df, names="niveau", hole=0.4,
                         color="niveau",
                         color_discrete_map={"🟢 RISQUE FAIBLE": "#12B981",
                                              "🟡 RISQUE MODÉRÉ": "#F0A020",
                                              "🔴 RISQUE ÉLEVÉ": "#FF4757"})
            st.plotly_chart(fig, use_container_width=True)
        with colg2:
            st.subheader("Top domaines expéditeurs")
            top_domaines = df["domaine_expediteur"].value_counts().head(10).reset_index()
            top_domaines.columns = ["domaine", "nb_emails"]
            fig2 = px.bar(top_domaines, x="nb_emails", y="domaine", orientation="h")
            st.plotly_chart(fig2, use_container_width=True)

        st.subheader("Score de risque au fil du temps")
        df_sorted = df.sort_values("timestamp")
        fig3 = px.line(df_sorted, x="timestamp", y="score_final", markers=True)
        fig3.add_hline(y=mg.SEUIL_DECISION, line_dash="dash", line_color="red",
                        annotation_text="Seuil de décision")
        st.plotly_chart(fig3, use_container_width=True)

        st.subheader("⚡ Efficacité de la cascade (argument technique fort)")
        etage_counts = df["etage"].value_counts().reset_index()
        etage_counts.columns = ["étage", "nb_cas"]  # 1 = listes/règles, 2 = fusion
        etage_counts["étage"] = etage_counts["étage"].map({1: "Listes ou règle sûre", 2: "Score de la fusion"})
        fig4 = px.bar(etage_counts, x="étage", y="nb_cas", color="étage")
        st.plotly_chart(fig4, use_container_width=True)
        st.caption("Plus la cascade résout de cas à l'étage 1, plus le système est rapide et économe "
                   "en ressources réseau — un argument clé pour la scalabilité de MailGuard.")

# ---------------------------------------------------------------------
# ONGLET 4 — TEST MANUEL
# ---------------------------------------------------------------------
with tab_manuel:
    st.subheader("🧪 Tester un email manuellement (sans passer par Gmail)")
    with st.form("form_test_manuel"):
        domaine = st.text_input("Domaine expéditeur", placeholder="ex: nouveiair.com")
        sujet = st.text_input("Sujet (optionnel)")
        texte = st.text_area("Texte de l'email", height=150,
                              placeholder="Votre compte a été suspendu, cliquez ici...")
        url_lien = st.text_input("URL d'un lien contenu dans l'email (optionnel)")
        texte_lien = st.text_input("Texte affiché pour ce lien (optionnel)")
        auth_header = st.text_input("Header Authentication-Results (optionnel)",
                                     placeholder="spf=fail dkim=fail dmarc=fail")
        submit = st.form_submit_button("🔬 Analyser", type="primary")

    if submit and domaine:
        liens = [{"texte_affiche": texte_lien or url_lien, "url_reelle": url_lien}] if url_lien else []
        with st.spinner("Analyse en cours..."):
            resultat = mg.analyser_email_complet(
                domaine_expediteur=domaine, texte_email=texte, liens=liens, auth_header=auth_header,
            )
        st.markdown(badge_html(resultat["niveau"]), unsafe_allow_html=True)
        st.plotly_chart(gauge_score(resultat["score_final"], mg.SEUIL_DECISION), use_container_width=True)
        afficher_pipeline(resultat)
