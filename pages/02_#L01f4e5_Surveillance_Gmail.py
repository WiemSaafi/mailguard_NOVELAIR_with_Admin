"""
pages/02_📥_Surveillance_Gmail.py
===================================
Surveillance de la boîte Gmail en direct : chaque nouveau message est
analysé à son arrivée, affiché avec son verdict, puis rangé selon l'action
choisie.
"""

import os
import time
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv

import mailguard_core as mg
from services import auth_service as auth
from services.history_service import ajouter_entree, charger_historique
from services.imap_service import extraire_domaine_expediteur, extraire_texte_brut
from services.mail_providers import PROTOCOLES, creer_fournisseur, decoder_texte
from services.quarantine_service import categoriser_email, get_seuils
from utils.auth_ui import exiger_connexion, id_utilisateur, utilisateur_actuel
from utils.ui_helpers import (
    COULEURS,
    afficher_alerte_securite,
    appliquer_signature,
    appliquer_theme,
    bandeau_verdict,
    entete_page,
    pastille,
    titre_section,
    rail_cascade,
)

load_dotenv()
appliquer_theme()
appliquer_signature()
exiger_connexion()
for cle, valeur in [
    ("surveillance_active", False), ("gmail_connecte", False),
    ("journal", []), ("messages_session", []), ("nb_analyses_session", 0),
]:
    st.session_state.setdefault(cle, valeur)

entete_page(
    titre="La boîte sous surveillance, message par message",
    sous_titre="MailGuard relève les nouveaux messages de la boîte de réception et du "
               "dossier Spam à intervalle régulier, et les analyse avant que vous ne les "
               "ouvriez.",
    surtitre="Surveillance Gmail",
    mot_accent="message par message",
)

# MULTI-UTILISATEURS : chaque compte relie sa propre boite. Le mot de passe
# d'application est stocke chiffre et dechiffre uniquement ici, au moment de
# la connexion IMAP.
_utilisateur = utilisateur_actuel()
messagerie = auth.lire_messagerie(_utilisateur["email"])
adresse = messagerie["adresse"]
protocole = messagerie["protocole"]
infos_protocole = PROTOCOLES.get(protocole, PROTOCOLES["imap"])


def identifiants_complets(m):
    """L'adresse seule ne suffit pas : il faut aussi le secret du protocole."""
    if m["protocole"] == "graph":
        return all([m["adresse"], m["tenant_id"], m["client_id"], m["client_secret"]])
    return bool(m["adresse"] and m["mot_de_passe"])


pret = identifiants_complets(messagerie)

# ── Réglages de la session ───────────────────────────────────────────────
gauche, droite = st.columns([1, 1], gap="large")

with gauche:
    titre_section("Réglages de la session")
    choix_dossiers = st.multiselect(
        "Dossiers à relever", ["Boîte de réception", "Spam"],
        default=["Boîte de réception", "Spam"],
        help="Le dossier Spam est trouvé automatiquement ([Gmail]/Spam sur Gmail). "
             "Un message du Spam est analysé mais jamais déplacé ni effacé.")
    autre_dossier = st.text_input("Autre dossier (facultatif)", value="",
                                  placeholder="ex. [Gmail]/Promotions")
    deja_presents = st.number_input(
        "Analyser aussi les N derniers messages déjà présents (par dossier)",
        min_value=0, max_value=20, value=0,
        help="0 = seuls les messages arrivés après le démarrage sont analysés.")
    intervalle = st.slider("Intervalle entre deux relevés (secondes)", 3, 30, 5)
    action_config = st.radio(
        "Que faire des messages dangereux",
        options=["quarantaine", "suspects", "marquer", "rien"],
        format_func=lambda x: {
            "quarantaine": "Déplacer vers MailGuard/Quarantaine",
            "suspects": "Déplacer vers MailGuard/Suspects",
            "marquer": "Signaler sans déplacer",
            "rien": "Observer sans rien changer",
        }[x],
    )
    st.session_state["action_config"] = action_config

with droite:
    titre_section("État")
    if pret:
        st.markdown(
            pastille(f"{infos_protocole['nom']} · {adresse}", "sur"),
            unsafe_allow_html=True,
        )
        if not infos_protocole["deplacement"]:
            st.markdown(
                '<div class="mg-alert mg-alert-warn">Protocole POP3 : les messages '
                'seront analysés et signalés, mais aucun ne pourra être déplacé en '
                'quarantaine.</div>',
                unsafe_allow_html=True,
            )
    elif adresse:
        st.markdown(pastille(f"{adresse} : mot de passe manquant", "veille"),
                    unsafe_allow_html=True)
        st.markdown(
            '<div class="mg-alert mg-alert-warn">Reliez d\'abord votre boîte '
            'depuis la page Paramètres. Vos identifiants restent chiffrés et '
            'ne sont visibles que par votre compte.</div>',
            unsafe_allow_html=True,
        )
    st.write("")
    c1, c2 = st.columns(2)
    c1.metric("Analysés dans cette session", st.session_state["nb_analyses_session"])
    c2.metric("Total de vos analyses", len(charger_historique(id_utilisateur())))

# ── Commandes ────────────────────────────────────────────────────────────
st.write("")
b1, b2, b3 = st.columns([1, 1, 1.6])

demarrer = b1.button("Démarrer la surveillance", type="primary",
                     width="stretch",
                     disabled=st.session_state["surveillance_active"] or not pret)
arreter = b2.button("Arrêter", width="stretch",
                    disabled=not st.session_state["surveillance_active"])

with b3:
    if st.button("Tester la connexion", width="stretch"):
        with st.spinner(f"Connexion en {infos_protocole['nom']}…"):
            ok, message = creer_fournisseur(**messagerie).tester_connexion()
        st.session_state["gmail_connecte"] = ok
        (st.success if ok else st.error)(message)

if arreter:
    st.session_state["surveillance_active"] = False
    st.session_state["gmail_connecte"] = False
    st.rerun()

if demarrer:
    if not pret:
        st.error("Il manque le mot de passe d'application de votre boîte. "
                 "Renseignez-le depuis la page Paramètres, section Votre boîte "
                 "de messagerie.")
    else:
        st.session_state.update(
            surveillance_active=True, journal=[], messages_session=[], nb_analyses_session=0
        )

# ── Boucle de surveillance ───────────────────────────────────────────────
if st.session_state["surveillance_active"]:
    st.write("")
    st.markdown(
        f'<div class="mg-alert mg-alert-warn">Surveillance en cours. '
        f'Relevé de <span class="mg-mono">{", ".join(choix_dossiers + ([autre_dossier] if autre_dossier else [])) or "aucun dossier"}</span> en '
        f'{infos_protocole["nom"]}, toutes les {intervalle} secondes.</div>',
        unsafe_allow_html=True,
    )

    zone_journal = st.empty()
    zone_message = st.empty()

    service = creer_fournisseur(**messagerie)
    ok, message_connexion = service.connecter()

    if not ok:
        st.error(f"Connexion refusée. {message_connexion}")
        st.session_state["surveillance_active"] = False
    else:
        st.session_state["gmail_connecte"] = True
        journal = st.session_state["journal"]

        # Les dossiers à relever (le nom réel du Spam est demandé au serveur)
        dossiers = []
        if "Boîte de réception" in choix_dossiers:
            dossiers.append("INBOX")
        if "Spam" in choix_dossiers and service.dossier_spam():
            dossiers.append(service.dossier_spam())
        if autre_dossier.strip():
            dossiers.append(autre_dossier.strip())
        dossiers = list(dict.fromkeys(dossiers))

        def _ordre(u):
            try:
                return int(u)
            except (TypeError, ValueError):
                return 0

        # UID déjà vus, par dossier. Les N derniers peuvent être analysés tout de suite.
        uids_connus = {}
        for d in dossiers:
            presents = sorted(service.get_uids_actuels(d), key=_ordre)
            n = int(deja_presents)
            a_relire = set(presents[-n:]) if n else set()
            uids_connus[d] = set(presents) - a_relire
            journal.append(
                f"{datetime.now():%H:%M:%S}  {d} : {len(presents)} messages présents, "
                f"{len(a_relire)} analysés maintenant, les autres ignorés")
        if not dossiers:
            journal.append("aucun dossier choisi")

        def traiter(uid, dossier):
            """Analyse un message du dossier sélectionné, applique l'action et l'enregistre."""
            journal.append(f"{datetime.now():%H:%M:%S}  [{dossier}] message reçu, identifiant {uid.decode()}")
            with zone_message.container():
                with st.status("Analyse en cours…", expanded=True) as etat:
                    message = service.fetch_email(uid)
                    if not message:
                        etat.update(label="Message illisible, ignoré", state="error")
                        return

                    domaine = extraire_domaine_expediteur(message.get("From", ""))
                    sujet = decoder_texte(message.get("Subject", "(sans objet)"))
                    texte = extraire_texte_brut(message)
                    html = mg.extraire_corps_html(message)
                    liens = mg.extraire_liens(html) if html else []
                    auth = message.get("Authentication-Results", "")

                    st.write(f"Dossier : {dossier}")
                    st.write(f"Expéditeur : {domaine}")
                    st.write(f"Objet : {sujet[:70]}")
                    st.write("Analyse des cinq signaux (CANINE, identité, liens, e5, authentification)…")

                    depart = time.time()
                    resultat = mg.analyser_email_complet(
                        domaine_expediteur=domaine, texte_email=texte,
                        liens=liens, auth_header=auth,
                        message=message, sujet=sujet,   # message complet : tous les en-têtes sont lus
                    )
                    duree = round((time.time() - depart) * 1000, 1)

                    st.write(f"Étape qui a décidé : {resultat.get('etape_decision', '')}")

                    score = resultat.get("score_final", 0)
                    categorie = categoriser_email(score, resultat)
                    action = (service.appliquer_action(uid, categorie, action_config)
                              if action_config != "rien" else "observation seule")

                    libelles = {"DANGEREUX": ("Frauduleux", "error"),
                                "SUSPECT": ("Suspect", "running"),
                                "LÉGITIME": ("Légitime", "complete")}
                    titre, drapeau = libelles[categorie]
                    etat.update(label=f"{titre} — score {score:.3f} — {duree} ms — {dossier}",
                                state=drapeau)

                bandeau_verdict(score, action=action, domaine=domaine,
                                seuil_suspect=get_seuils()[0],
                                seuil_dangereux=get_seuils()[1],
                                etape=resultat.get("etape_decision"),
                                categorie=resultat.get("categorie"))
                st.write("")
                rail_cascade(signaux_calcules=resultat.get("signaux_calcules"),
                             etape=resultat.get("etape_decision"))
                if resultat.get("raisons"):
                    st.markdown("**Pourquoi :** " + " · ".join(resultat["raisons"][:4]))

            ajouter_entree(
                domaine_expediteur=domaine, sujet=sujet, texte_apercu=texte,
                nb_liens=len(liens), resultat=resultat, duree_ms=duree,
                action_appliquee=action, source="gmail", uid=uid.decode(),
                identifiant=id_utilisateur(),
            )

            st.session_state["nb_analyses_session"] += 1
            st.session_state["messages_session"].append({
                "domaine": domaine, "sujet": sujet, "score": score,
                "categorie": categorie, "action": action,
                "heure": datetime.now().strftime("%H:%M:%S"),
            })
            journal.append(f"{datetime.now():%H:%M:%S}  [{dossier}] {libelles[categorie][0].lower()}, "
                           f"score {score:.3f}, {action}")

            if categorie == "DANGEREUX":
                st.session_state["derniere_alerte"] = {
                    "domaine": domaine, "score": score, "action": action}

        RELEVES_MAX = 60
        releve = 0

        while st.session_state.get("surveillance_active") and releve < RELEVES_MAX:
            releve += 1
            with zone_journal.container():
                st.markdown("#### Journal")
                st.code("\n".join(journal[-12:]), language=None)

            service.noop()
            for d in dossiers:
                # get_uids_actuels sélectionne le dossier : on traite ses messages juste après.
                nouveaux = sorted(service.get_uids_actuels(d) - uids_connus[d], key=_ordre)
                for uid in nouveaux:
                    uids_connus[d].add(uid)
                    traiter(uid, d)

            time.sleep(intervalle)

        service.deconnecter()
        if releve >= RELEVES_MAX:
            st.session_state["surveillance_active"] = False
            st.info("Session de surveillance terminée. Relancez-la pour continuer.")

# ── Messages de la session ───────────────────────────────────────────────
st.write("")
titre_section("Messages analysés dans cette session")

messages = st.session_state.get("messages_session", [])
if not messages:
    st.markdown(
        '<div class="mg-carte"><p>Rien pour l\'instant. Démarrez la surveillance, '
        'puis envoyez-vous un message depuis une autre boîte pour voir l\'analyse '
        'se dérouler.</p></div>',
        unsafe_allow_html=True,
    )
else:
    tons = {"LÉGITIME": "sur", "SUSPECT": "veille", "DANGEREUX": "menace"}
    for item in reversed(messages[-10:]):
        ton = tons.get(item["categorie"], "attenue")
        st.markdown(
            f'<div class="mg-carte" style="border-left:3px solid {COULEURS[ton]};'
            f'margin-bottom:0.5rem;">'
            f'<div style="display:flex;justify-content:space-between;gap:1rem;">'
            f'<div><b class="mg-mono">{item["domaine"]}</b> '
            f'<span style="color:{COULEURS["attenue"]};">{item["sujet"][:60]}</span></div>'
            f'<div class="mg-mono" style="color:{COULEURS[ton]};font-weight:600;">'
            f'{item["score"]:.3f}</div></div>'
            f'<p style="margin-top:0.35rem;font-size:0.82rem;">{item["heure"]} — '
            f'{item["action"]}</p></div>',
            unsafe_allow_html=True,
        )

# ── Aide à la démonstration ──────────────────────────────────────────────
with st.expander("Préparer une démonstration"):
    st.markdown(
        "1. Activez la validation en deux étapes sur le compte Gmail, puis générez "
        "un mot de passe d'application sur "
        "`https://myaccount.google.com/apppasswords`.\n"
        "2. Renseignez `GMAIL_ADDRESS` et `GMAIL_APP_PASSWORD` dans `.env`, puis "
        "testez la connexion ci-dessus.\n"
        "3. Démarrez la surveillance avec l'action « Déplacer vers "
        "MailGuard/Quarantaine ».\n"
        "4. Depuis une autre boîte, envoyez un message dont l'objet annonce une "
        "suspension de compte et dont le corps pointe vers un domaine proche du "
        "vôtre à une lettre près.\n"
        "5. L'analyse apparaît en quelques secondes. Vérifiez ensuite dans Gmail "
        "que le message a bien quitté la boîte de réception."
    )
