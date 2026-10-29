"""
pages/03_🧪_Test_Manuel.py
============================
Analyse d'un email saisi à la main, sans passer par Gmail.
"""

import time
import streamlit as st

from services.history_service import ajouter_entree
from services.quarantine_service import categoriser_email, get_action_recommandee
from utils.display_result import afficher_resultat_complet
from utils.auth_ui import exiger_connexion, id_utilisateur
from utils.ui_helpers import (
    COULEURS,
    afficher_alerte_securite,
    appliquer_signature,
    appliquer_theme,
    entete_page,
    titre_section,
)

import mailguard_core as mg

appliquer_theme()
appliquer_signature()
exiger_connexion()

entete_page(
    titre="Analysez un message, voyez la décision se construire",
    sous_titre="Saisissez un email, ou partez d'un des trois exemples. Le résultat est "
               "présenté exactement comme pour un message relevé dans la boîte Gmail.",
    surtitre="Test manuel",
    mot_accent="voyez la décision se construire",
)

# ─── Exemples ─────────────────────────────────────────────────────────────────
# Chaque exemple définit aussi les valeurs SPF/DKIM/DMARC par défaut
ETATS_AUTH = ["pass", "fail", "none", "absent"]

# Trois exemples, un par issue possible : FRAUDULEUX, SUSPECT, LÉGITIME.
# Les domaines choisis ne sont PAS dans la liste noire : ce sont donc les modèles
# (et non une simple liste) qui décident, et les cinq signaux s'affichent.
EXEMPLES = {
    "Tentative de phishing": {
        "sujet": "Votre compte a été suspendu",
        "domaine": "nouvelair-verification.com",
        "texte": (
            "Bonjour,\n\nVotre compte Nouvelair a été suspendu suite à une activité suspecte.\n"
            "Veuillez vous connecter immédiatement pour vérifier vos informations bancaires.\n\n"
            "Équipe Sécurité"
        ),
        "note": "Domaine qui imite Nouvelair (absent de la liste noire), texte alarmiste, "
                "authentification en échec.",
        "attendu": "Frauduleux · règle sûre (CANINE)",
        "ton": "menace",
        "spf":   "fail",
        "dkim":  "none",
        "dmarc": "fail",
        "liens": [
            {"url": "http://nouvelair-verification.com/secure-login", "texte": "Connectez-vous sur nouvelair.com"},
        ],
    },
    "Compte piraté ?": {
        "sujet": "Détails de votre réservation",
        "domaine": "nouvelair.com",
        "texte": (
            "Bonjour,\n\nVeuillez consulter les détails de votre réservation "
            "en cliquant sur le lien ci-dessous.\n\nService clients"
        ),
        "note": "Vrai domaine Nouvelair, bien authentifié, texte banal… "
                "mais le lien mène vers nouvelalr.com.",
        "attendu": "Suspect · règle R2 (lien dangereux)",
        "ton": "veille",
        "spf":   "pass",
        "dkim":  "pass",
        "dmarc": "pass",
        "liens": [
            {"url": "http://nouvelalr.com/update", "texte": "Voir ma réservation"},
        ],
    },
    "Message légitime": {
        "sujet": "Confirmation de votre réservation",
        "domaine": "nouvelair.com",
        "texte": (
            "Bonjour,\n\nVotre réservation est confirmée.\n"
            "Merci d'avoir choisi Nouvelair pour votre prochain voyage.\n\nBonne journée."
        ),
        "note": "Domaine de confiance, contenu anodin, authentification en règle.",
        "attendu": "Légitime · liste blanche (domaine prouvé)",
        "ton": "sur",
        "spf":   "pass",
        "dkim":  "pass",
        "dmarc": "pass",
        "liens": [
            {"url": "https://www.nouvelair.com/fr/gerer-ma-reservation", "texte": "Gérer ma réservation"},
        ],
    },
}

titre_section("Partir d'un exemple",
              "Trois cas préparés qui couvrent les trois issues possibles du filtre.")

for colonne, (nom, ex) in zip(st.columns(3, gap="medium"), EXEMPLES.items()):
    with colonne:
        st.markdown(
            f'<div class="mg-carte" style="border-top:3px solid {COULEURS[ex["ton"]]};'
            f'padding:1.4rem 1.5rem;">'
            f'<h4>{nom}</h4>'
            f'<p class="mg-mono" style="font-size:.85rem;color:{COULEURS["encre"]};'
            f'margin:.35rem 0 .6rem 0;">{ex["domaine"]}</p>'
            f'<p style="font-size:.9rem;">{ex["note"]}</p>'
            f'<p style="font-size:.8rem;color:#888;">SPF={ex["spf"]} · '
            f'DKIM={ex["dkim"]} · DMARC={ex["dmarc"]}</p>'
            f'<p style="font-size:.82rem;font-weight:700;color:{COULEURS[ex["ton"]]};'
            f'margin-top:.4rem;">Attendu : {ex["attendu"]}</p>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button(f"Charger « {nom} »", key=f"ex_{nom}", width="stretch"):
            st.session_state["ex_domaine"] = ex["domaine"]
            st.session_state["ex_texte"]   = ex["texte"]
            st.session_state["ex_sujet"]   = ex.get("sujet", "")
            st.session_state["ex_spf"]     = ex["spf"]
            st.session_state["ex_dkim"]    = ex["dkim"]
            st.session_state["ex_dmarc"]   = ex["dmarc"]
            st.session_state["ex_liens"]   = ex["liens"]
            st.rerun()

# ─── Formulaire ───────────────────────────────────────────────────────────────
titre_section("Le message à analyser",
              "Seuls le domaine et le contenu sont nécessaires. Le reste affine l'analyse.")

# Lire les valeurs courantes depuis session_state
_spf_val   = st.session_state.get("ex_spf",   "pass")
_dkim_val  = st.session_state.get("ex_dkim",  "pass")
_dmarc_val = st.session_state.get("ex_dmarc", "pass")
_liens     = st.session_state.get("ex_liens", [])

def _idx(val):
    try:
        return ETATS_AUTH.index(val)
    except ValueError:
        return 0

with st.form("form_test_manuel", clear_on_submit=False):
    col_g, col_d = st.columns(2, gap="large")

    with col_g:
        domaine = st.text_input(
            "Domaine de l'expéditeur",
            value=st.session_state.get("ex_domaine", ""),
            placeholder="nouvelairr.com",
            help="La partie qui suit l'arobase dans l'adresse de l'expéditeur.",
        )
        sujet = st.text_input("Objet", value=st.session_state.get("ex_sujet", ""),
                              placeholder="Votre compte a été suspendu")
        texte = st.text_area(
            "Corps du message",
            value=st.session_state.get("ex_texte", ""),
            height=232,
            placeholder="Collez ici le texte complet du message.",
        )

    with col_d:
        st.markdown("**Liens contenus dans le message**")
        url_lien1   = st.text_input("Adresse du premier lien",
                                    value=_liens[0]["url"]   if _liens else "",
                                    placeholder="http://nouvelairr.com/login")
        texte_lien1 = st.text_input("Texte affiché du premier lien",
                                    value=_liens[0]["texte"] if _liens else "",
                                    placeholder="Connectez-vous sur nouvelair.com")
        url_lien2   = st.text_input("Adresse du second lien",
                                    value=_liens[1]["url"]   if len(_liens) > 1 else "",
                                    placeholder="facultatif")
        texte_lien2 = st.text_input("Texte affiché du second lien",
                                    value=_liens[1]["texte"] if len(_liens) > 1 else "",
                                    placeholder="facultatif")

        st.markdown("**Résultats d'authentification**")
        col_spf, col_dkim, col_dmarc = st.columns(3)
        with col_spf:
            spf = st.selectbox("SPF", ETATS_AUTH, index=_idx(_spf_val))
        with col_dkim:
            dkim = st.selectbox("DKIM", ETATS_AUTH, index=_idx(_dkim_val))
        with col_dmarc:
            dmarc_val = st.selectbox("DMARC", ETATS_AUTH, index=_idx(_dmarc_val))

        sauvegarder = st.checkbox("Conserver cette analyse dans l'historique", value=True)

    submitted = st.form_submit_button("Analyser ce message", type="primary", width="stretch")

# ─── Analyse ──────────────────────────────────────────────────────────────────
if submitted and not domaine:
    st.error("Le domaine de l'expéditeur est nécessaire pour lancer l'analyse.")

elif submitted and domaine:
    liens = []
    if url_lien1:
        liens.append({"texte_affiche": texte_lien1 or url_lien1, "url_reelle": url_lien1})
    if url_lien2:
        liens.append({"texte_affiche": texte_lien2 or url_lien2, "url_reelle": url_lien2})

    # En-tête Authentication-Results réaliste : le signal 5 vérifie aussi l'ALIGNEMENT
    # (le domaine signé / l'expéditeur SMTP doivent être celui du From).
    dom_auth = domaine.split("@")[-1].strip().lower()
    auth_header = (f"mx.nouvelair.com; spf={spf} smtp.mailfrom={dom_auth}; "
                   f"dkim={dkim} header.d={dom_auth}; dmarc={dmarc_val} header.from={dom_auth}")

    titre_section("La décision")

    with st.status("Analyse en cours", expanded=True) as status:
        st.write("Extraction des informations du message")
        time.sleep(0.3)
        st.write("S1 · le nom du domaine imite-t-il une marque ? (CANINE)")
        st.write("S2 · âge et identité du domaine (RDAP, certificats)")
        if liens:
            st.write(f"S3 · vérification de {len(liens)} lien(s)")
        st.write("S4 · classement du texte (multilingual-e5)")
        st.write("S5 · SPF, DKIM, DMARC et alignement")

        t0 = time.time()
        resultat = mg.analyser_email_complet(
            domaine_expediteur=domaine,
            texte_email=texte,
            liens=liens,
            auth_header=auth_header,
            sujet=sujet,
        )
        duree_ms = round((time.time() - t0) * 1000, 1)
        st.write(f"Fusion et cascade : {resultat.get('etape_decision', '')}")

        status.update(label=f"Analyse terminée en {duree_ms} ms", state="complete")

    # Sécuriser les clés manquantes dans le résultat
    if "categorie" not in resultat:
        st.error(
            f"L'analyse n'a pas produit de résultat complet. "
            f"Résultat brut reçu : `{resultat}`"
        )
        st.stop()

    action = get_action_recommandee(
        resultat.get("categorie", "LÉGITIME"),
        st.session_state.get("action_config", "quarantaine"),
    )

    if resultat.get("categorie") != "LÉGITIME":
        afficher_alerte_securite(domaine, resultat.get("score_final", 0), action, sujet,
                                 categorie=resultat.get("categorie"))

    afficher_resultat_complet(resultat, domaine=domaine, sujet=sujet, action=action)
    st.caption(f"Analyse faite en {duree_ms} ms.")

    if sauvegarder:
        id_u = id_utilisateur()
        if id_u:
            try:
                ajouter_entree(
                    domaine_expediteur=domaine, sujet=sujet, texte_apercu=texte,
                    nb_liens=len(liens), resultat=resultat, duree_ms=duree_ms,
                    action_appliquee=action, source="manuel", identifiant=id_u,
                )
            except Exception:
                pass
