"""
pages/10_ADMIN_Trusted_Domains.py
Domaines de confiance (whitelist) — admin uniquement.
Avec vérification CANINE (signal 1) avant ajout.
"""
import streamlit as st
from services import auth_service as auth
from utils.auth_ui import exiger_admin

exiger_admin()

st.title("Trusted Domains")
st.caption("Trusted Domains with Smart Validation")
st.divider()

# Initialiser les listes si vides
auth.initialiser_listes_domaines()

onglet_liste, onglet_ajout = st.tabs(["Domain List", "+ Add Domain"])

# ── Liste ──────────────────────────────────────────────────────────────────
with onglet_liste:
    col_f1, col_f2 = st.columns([1, 2])
    with col_f1:
        filtre = st.selectbox("Status", ["All", "approved", "pending_validation", "rejected"],
                              key="td_filtre")
    with col_f2:
        recherche = st.text_input("Search Domain", key="td_search")

    map_f = {"All": "all", "approved": "approved",
              "pending_validation": "pending_validation", "rejected": "rejected"}
    domaines = auth.lister_domains_confiance(statut_filtre=map_f[filtre])

    if recherche:
        domaines = [d for d in domaines if recherche.lower() in d["domaine"].lower()]

    if not domaines:
        st.info("Aucun domaine de confiance trouvé.")
    else:
        st.markdown(f"**{len(domaines)} domaine(s) trouvé(s)**")
        for d in domaines:
            icone_statut = {"approved": "🟢", "pending_validation": "🟡",
                            "rejected": "🔴"}.get(d["statut"], "⚪")
            icone_bert = {"oui": " ✅ CANINE", "non": " ❌ CANINE", "nc": ""}.get(
                d.get("valide_par_bert", ""), "")

            with st.expander(f"{icone_statut} {d['domaine']} — Status: {d['statut']}{icone_bert}"):
                c1, c2, c3 = st.columns(3)
                c1.write(f"**Domaine :** `{d['domaine']}`")
                c1.write(f"**Statut :** {d['statut']}")
                c2.write(f"**Ajouté le :** {d['ajoute_le']}")
                c2.write(f"**Commentaire :** {d.get('commentaire', '—')}")
                c3.write(f"**CANINE :** {d.get('valide_par_bert', 'nc')}")
                with c3:
                    if d["statut"] != "approved":
                        if st.button("✅ Approuver", key=f"appr_td_{d['id']}"):
                            ok, msg = auth.valider_domain_confiance(d["id"])
                            st.success(msg) if ok else st.error(msg)
                            st.rerun()
                    if st.button("🗑️ Supprimer", key=f"del_td_{d['id']}"):
                        ok, msg = auth.supprimer_domain_confiance(d["id"])
                        st.success(msg) if ok else st.error(msg)
                        st.rerun()

# ── Ajout avec vérification CANINE ──────────────────────────────────────────────
with onglet_ajout:
    st.markdown(
        "Le modèle CANINE (signal 1) vérifie que le domaine n'imite pas une marque "
        "protégée avant de l'enregistrer. Rappel : un domaine de la liste blanche n'est "
        "accepté que si le message est authentifié (DKIM ou SPF aligné).",
    )

    with st.form("ajout_domaine_confiance"):
        nouveau_domaine = st.text_input("Nom de domaine", placeholder="exemple.com")
        commentaire = st.text_input("Commentaire / raison")
        valider = st.form_submit_button("Ajouter le domaine", type="primary")

    if valider:
        if not nouveau_domaine:
            st.error("Le nom de domaine est requis.")
        else:
            with st.spinner("Vérification CANINE en cours…"):
                ok, msg, bert = auth.ajouter_domain_confiance(
                    nouveau_domaine.strip(), commentaire)

            if ok:
                st.success(msg)
                if bert == "nc":
                    st.warning("⚠️ CANINE non disponible — vérification manuelle recommandée.")
                elif bert == "oui":
                    st.info("✅ CANINE : ce domaine n'imite aucune marque protégée.")
                st.rerun()
            else:
                st.error(msg)
                if bert == "non":
                    st.warning(
                        "💡 Si vous êtes certain que ce domaine est légitime, "
                        "vérifiez l'orthographe exacte. Le modèle signale une "
                        "ressemblance avec un domaine frauduleux connu."
                    )
