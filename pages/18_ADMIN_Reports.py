"""
pages/18_📄_Reports.py
Génération de rapports et exportations de données — admin.
"""
import streamlit as st
import json, io
from datetime import datetime, date, timedelta
import pandas as pd
from utils.auth_ui import exiger_admin
from utils.ui_helpers import appliquer_theme, appliquer_signature, entete_page
from services.database import Analyse, Utilisateur, libelle_categorie, session as db_session

exiger_admin()

entete_page(
    titre="Security Reports",
    sous_titre="Génération de rapports et exportations de données",
)

# ── Sélecteur de période ───────────────────────────────────────────────────
st.markdown("**Quick Select**")
periode = st.radio("", ["Today", "Last 7 Days", "Last 30 Days", "Custom"],
                   label_visibility="collapsed")

date_debut = date.today()
date_fin = date.today()

if periode == "Today":
    date_debut = date_fin = date.today()
elif periode == "Last 7 Days":
    date_debut = date.today() - timedelta(days=7)
elif periode == "Last 30 Days":
    date_debut = date.today() - timedelta(days=30)
elif periode == "Custom":
    c1, c2 = st.columns(2)
    with c1:
        date_debut = st.date_input("Date de début", value=date.today() - timedelta(days=7))
    with c2:
        date_fin = st.date_input("Date de fin", value=date.today())

if st.button("📊 Generate Report", type="primary"):
    dt_debut = datetime.combine(date_debut, datetime.min.time())
    dt_fin = datetime.combine(date_fin, datetime.max.time())

    with db_session() as s:
        q = s.query(Analyse).filter(
            Analyse.horodatage >= dt_debut,
            Analyse.horodatage <= dt_fin,
        ).order_by(Analyse.horodatage.desc())
        analyses = q.all()

        data = [{
            "ID": a.id,
            "Horodatage": a.horodatage.strftime("%Y-%m-%d %H:%M:%S") if a.horodatage else "",
            "Domaine expéditeur": a.domaine_expediteur,
            "Sujet": a.sujet,
            "Score final": round(a.score_final, 4),
            "Catégorie": libelle_categorie(a.categorie),
            "Action appliquée": a.action_appliquee,
            "Source": a.source,
            "Nb liens": a.nb_liens,
            "Durée analyse (ms)": round(a.duree_analyse_ms, 1),
        } for a in analyses]

    if not data:
        st.warning("Aucune analyse trouvée pour cette période.")
    else:
        df = pd.DataFrame(data)

        # ── Statistiques sommaires ──────────────────────────────────────────
        st.subheader(f"Rapport du {date_debut} au {date_fin}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", len(df))
        c2.metric("Frauduleux", (df["Catégorie"] == "FRAUDULEUX").sum())
        c3.metric("Suspects", (df["Catégorie"] == "SUSPECT").sum())
        c4.metric("Légitimes", (df["Catégorie"] == "LÉGITIME").sum())

        st.dataframe(df, width="stretch", hide_index=True)

        # ── Export CSV ──────────────────────────────────────────────────────
        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False, encoding="utf-8")
        st.download_button(
            "⬇️ Télécharger CSV",
            data=csv_buf.getvalue().encode("utf-8"),
            file_name=f"mailguard_rapport_{date_debut}_{date_fin}.csv",
            mime="text/csv",
        )

        # ── Export JSON ─────────────────────────────────────────────────────
        st.download_button(
            "⬇️ Télécharger JSON",
            data=json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name=f"mailguard_rapport_{date_debut}_{date_fin}.json",
            mime="application/json",
        )
