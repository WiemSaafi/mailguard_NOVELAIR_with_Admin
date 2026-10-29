"""
pages/13_🧠_Explain_Detection.py
Expliquer le raisonnement derrière une classification de domaine — admin.
"""
import streamlit as st
from utils.auth_ui import exiger_admin, banner_modele_absent
from utils.ui_helpers import appliquer_theme, appliquer_signature, entete_page, COULEURS

exiger_admin()
banner_modele_absent()

entete_page(
    titre="Explain Detection",
    sous_titre="Understand the reasoning behind domain classifications",
)

# ── Formulaire d'analyse ───────────────────────────────────────────────────
with st.container():
    st.markdown('<div class="mg-carte">', unsafe_allow_html=True)
    domaine_input = st.text_input("Enter Domain Name", placeholder="ex: nouvelairr.com",
                                   key="explain_domain")
    analyser = st.button("Analyze", type="primary")
    st.markdown('</div>', unsafe_allow_html=True)

if analyser and domaine_input:
    domaine = domaine_input.strip().lower()

    # Charger le core MailGuard pour analyser
    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        import mailguard_core as mg

        with st.spinner(f"Analyse de {domaine} en cours…"):
            # Analyse via le détecteur global si disponible
            try:
                resultat = mg.analyser_domaine(domaine)
            except Exception:
                resultat = None

        if resultat and resultat.get("score") is not None:
            categorie = "FRAUDULEUX" if resultat.get("frauduleux") else "LÉGITIME"
            couleur = {"FRAUDULEUX": "#FF4757", "LÉGITIME": "#2ED573"}[categorie]
            st.markdown(
                f'<div style="background:{couleur}22;border:2px solid {couleur};'
                f'border-radius:12px;padding:1.2rem 1.5rem;margin:1rem 0;">'
                f'<h3 style="color:{couleur};margin:0 0 .4rem 0;">{categorie}</h3>'
                f'<p style="margin:0;">{" · ".join(resultat.get("raisons", []))}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )

            st.subheader("Détail des signaux du domaine")
            c1, c2, c3 = st.columns(3)
            c1.metric("S1 · score d'imitation (CANINE)", f"{resultat['score']:.3f}",
                      help=f"Alerte à partir de {resultat.get('seuil', 0.44):.2f}")
            c2.metric("Marque la plus proche", resultat.get("marque") or "—")
            c3.metric("S2 · âge du domaine",
                      f"{resultat['age_jours']} jours" if resultat.get("age_jours") is not None else "muet",
                      help="RDAP et crt.sh ; muet si le domaine est très connu ou si les registres ne répondent pas.")
            st.info(f"💡 {resultat.get('verdict', '')}")
            if resultat.get("plus_proche") and "FRAUDULEUX" in resultat.get("verdict", ""):
                from utils.ui_helpers import comparateur_domaines
                comparateur_domaines(domaine, resultat["plus_proche"], resultat.get("distance"))
            st.caption("Seul le domaine est analysé ici (S1 + S2). Pour un message complet "
                       "(liens, texte, authentification), utilisez la page Test manuel.")
        else:
            st.warning("Le moteur MailGuard n'est pas chargé : vérifiez le dossier "
                       "modeles_mailguard (page Paramètres).")

    except ImportError:
        st.error("Le module mailguard_core n'est pas chargé. Lancez l'application depuis le répertoire principal.")

elif analyser and not domaine_input:
    st.warning("Saisissez un nom de domaine.")
