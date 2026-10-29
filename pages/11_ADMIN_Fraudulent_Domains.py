"""
pages/11_ADMIN_Fraudulent_Domains.py
Domaines frauduleux (blacklist) — admin uniquement. Persistance DB.
"""
import streamlit as st
import csv, io
from datetime import datetime
from services import auth_service as auth
from utils.auth_ui import exiger_admin

exiger_admin()

st.title("Fraudulent Domains")
st.caption("Fraudulent Domains Management")
st.divider()

# Initialiser les listes si vides
auth.initialiser_listes_domaines()

# ── Ajout manuel ───────────────────────────────────────────────────────────
with st.expander("➕ + Add Fraudulent Domain"):
    with st.form("ajout_fraude"):
        c1, c2 = st.columns(2)
        with c1:
            dom = st.text_input("Domaine frauduleux", placeholder="nouvelairr.com")
            raison = st.text_input("Raison", placeholder="typosquatting Nouvelair")
        with c2:
            score = st.slider("Score de risque estimé", 0.0, 1.0, 0.85, 0.01)
            commentaire = st.text_area("Commentaire", height=70)
        valider = st.form_submit_button("Ajouter", type="primary")

    if valider:
        if not dom:
            st.error("Le domaine est requis.")
        else:
            ok, msg = auth.ajouter_domain_frauduleux(dom, raison, score, commentaire)
            st.success(msg) if ok else st.error(msg)
            if ok:
                st.rerun()

# ── Filtres ────────────────────────────────────────────────────────────────
c_f1, c_f2 = st.columns([1, 2])
with c_f1:
    filtre = st.selectbox("Status Filter", ["All", "active", "archived"], key="fd_filtre")
with c_f2:
    recherche = st.text_input("Search", key="fd_search")

map_f = {"All": "all", "active": "active", "archived": "archived"}
domaines = auth.lister_domains_frauduleux(
    statut_filtre=map_f[filtre], recherche=recherche)

if not domaines:
    st.info("No fraudulent domains found.")
else:
    st.markdown(f"**{len(domaines)} domaine(s) frauduleux**")
    for d in domaines:
        couleur_score = "#FF4757" if d["score"] >= 0.85 else (
            "#FFA502" if d["score"] >= 0.70 else "#999")
        with st.expander(
            f"🚨 {d['domaine']} — Score: {d['score']:.2f} "
            f"— {d.get('raison', '')} — {d['statut']}"
        ):
            c1, c2, c3 = st.columns(3)
            c1.write(f"**Domaine :** `{d['domaine']}`")
            c1.write(f"**Raison :** {d.get('raison', '—')}")
            c2.write(f"**Score :** {d['score']:.2f}")
            c2.write(f"**Ajouté le :** {d['ajoute_le']}")
            c3.write(f"**Commentaire :** {d.get('commentaire', '—')}")
            with c3:
                if st.button("🗑️ Supprimer", key=f"del_fd_{d['id']}"):
                    ok, msg = auth.supprimer_domain_frauduleux(d["id"])
                    st.success(msg) if ok else st.error(msg)
                    st.rerun()

st.divider()

# ── Import CSV ──────────────────────────────────────────────────────────────
st.subheader("CSV Import")
st.caption("Upload Fraudulent Domains CSV — colonnes: domaine, raison, score")
fichier = st.file_uploader("", type=["csv"], label_visibility="collapsed",
                            help="200MB per file • CSV")
if fichier:
    contenu = fichier.read().decode("utf-8", errors="replace")
    lecteur = csv.DictReader(io.StringIO(contenu))
    nb_ok = nb_err = 0
    for ligne in lecteur:
        dom_csv = (ligne.get("domaine") or ligne.get("domain") or "").strip().lower()
        if not dom_csv:
            continue
        raison_csv = ligne.get("raison", "import CSV")
        score_csv = float(ligne.get("score", 0.8))
        ok, _ = auth.ajouter_domain_frauduleux(dom_csv, raison_csv, score_csv)
        if ok:
            nb_ok += 1
        else:
            nb_err += 1
    if nb_ok:
        st.success(f"✅ {nb_ok} domaine(s) importé(s).")
        st.rerun()
    if nb_err:
        st.warning(f"{nb_err} doublon(s) ignoré(s).")
    if nb_ok == 0 and nb_err == 0:
        st.warning("Aucun domaine trouvé dans le fichier.")
