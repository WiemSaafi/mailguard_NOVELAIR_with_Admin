"""
pages/06_⚙️_Paramètres.py
===========================
Seuils de décision, connexion à la boîte, action automatique, état des
modèles et gestion des données conservées.

Les clés de session et la logique sont celles d'origine. Le mot de
confirmation pour effacer l'historique reste CONFIRMER.
"""

import os

import streamlit as st
from dotenv import load_dotenv

from services import auth_service as auth
from services.database import informations_base
from services.history_service import effacer_historique, get_stats
from services.mail_providers import (
    DOSSIER_QUARANTAINE, DOSSIER_SUSPECTS, PROTOCOLES, creer_fournisseur,
)
from utils.auth_ui import exiger_connexion, fermer_session, id_utilisateur, utilisateur_actuel
from utils.ui_helpers import (
    COULEURS,
    appliquer_signature,
    appliquer_theme,
    entete_page,
    pastille,
    titre_section,
)

load_dotenv()
appliquer_theme()
appliquer_signature()
exiger_connexion()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

utilisateur = utilisateur_actuel()

entete_page(
    titre="Ce que le filtre laisse passer, et ce qu'il écarte",
    sous_titre="Les seuils s'appliquent immédiatement à toutes les pages. "
               "Ils décident de ce qui reste dans la boîte de réception.",
    surtitre="Paramètres",
    mot_accent="et ce qu'il écarte",
)

# ─── Seuils ───────────────────────────────────────────────────────────────────
titre_section("Seuils de décision")
gauche, droite = st.columns([1.1, 1], gap="large")

with gauche:
    seuil_suspect = st.slider(
        "À partir de quel score un message est-il à surveiller",
        0.60, 0.99, float(st.session_state.get("seuil_suspect", 0.825)), 0.005,
        help="En dessous, le message reste dans la boîte de réception. "
             "Valeur apprise par la fusion : 0,825 (au plus 2 % de vrais mails accusés).",
    )
    seuil_dangereux = st.slider(
        "À partir de quel score un message est-il frauduleux",
        0.60, 1.00, float(st.session_state.get("seuil_dangereux", 0.928)), 0.005,
        help="Au-dessus, le message est écarté selon l'action choisie plus bas. "
             "Valeur apprise par la fusion : 0,928 (au plus 0,5 % de vrais mails accusés).",
    )

    if seuil_dangereux <= seuil_suspect:
        st.error("Le seuil frauduleux doit rester au-dessus du seuil de surveillance.")
    elif st.button("Appliquer ces seuils", type="primary"):
        st.session_state["seuil_suspect"] = seuil_suspect
        st.session_state["seuil_dangereux"] = seuil_dangereux
        auth.enregistrer_preferences(utilisateur["email"],
                                     seuil_suspect=seuil_suspect,
                                     seuil_dangereux=seuil_dangereux)
        st.toast("Seuils enregistrés sur votre compte.")

with droite:
    l1, l2, l3 = seuil_suspect, max(seuil_dangereux - seuil_suspect, 0.01), max(1 - seuil_dangereux, 0.01)
    st.markdown(
        f'<div class="mg-carte"><h4>Ce que donnent ces seuils</h4>'
        f'<div style="display:flex;gap:4px;margin:1.1rem 0 .8rem 0;">'
        f'<div style="flex:{l1:.2f};height:30px;border-radius:9px 0 0 9px;'
        f'background:{COULEURS["sur"]};"></div>'
        f'<div style="flex:{l2:.2f};height:30px;background:{COULEURS["veille"]};"></div>'
        f'<div style="flex:{l3:.2f};height:30px;border-radius:0 9px 9px 0;'
        f'background:{COULEURS["menace"]};"></div></div>'
        f'<p>Sans risque jusqu\'à <b class="mg-mono">{seuil_suspect:.2f}</b>, '
        f'à surveiller jusqu\'à <b class="mg-mono">{seuil_dangereux:.2f}</b>, '
        f'menace au-delà.</p>'
        f'<p style="margin-top:.9rem;">Abaisser les seuils attrape davantage de phishing '
        f'mais écarte aussi des messages légitimes. Les valeurs par défaut 0,25 et 0,50 '
        f'viennent de la calibration sur le jeu de test.</p></div>',
        unsafe_allow_html=True,
    )

# ─── Connexion Gmail ──────────────────────────────────────────────────────────
titre_section(
    "Votre boîte de messagerie",
    "Choisissez le protocole de votre serveur. Ces identifiants n'appartiennent "
    "qu'à votre compte, et les secrets sont chiffrés avant d'être écrits en base.",
)

messagerie = auth.lire_messagerie(utilisateur["email"])
codes = list(PROTOCOLES)
protocole = st.radio(
    "Protocole de relève",
    options=codes,
    index=codes.index(messagerie["protocole"]) if messagerie["protocole"] in codes else 0,
    format_func=lambda c: PROTOCOLES[c]["nom"],
    horizontal=True,
)
infos_protocole = PROTOCOLES[protocole]
st.caption(infos_protocole["description"])

if not infos_protocole["deplacement"]:
    st.markdown(
        '<div class="mg-alert mg-alert-warn"><b>POP3 ne connaît pas les dossiers.</b>'
        '<br>MailGuard pourra analyser les messages et vous alerter, mais pas les '
        'déplacer en quarantaine. C\'est une limite du protocole, pas de '
        'l\'application. Pour une mise en quarantaine réelle, choisissez IMAP ou '
        'Microsoft Graph.</div>',
        unsafe_allow_html=True,
    )

gauche, droite = st.columns([1.1, 1], gap="large")

with gauche:
    with st.form("messagerie"):
        adresse_saisie = st.text_input(
            "Adresse de la boîte à surveiller",
            value=messagerie["adresse"],
            placeholder="prenom.nom@nouvelair.com",
        )

        champs = {"adresse": adresse_saisie}

        if protocole in ("imap", "pop3"):
            champs["mot_de_passe"] = st.text_input(
                "Mot de passe d'application",
                type="password",
                placeholder="•" * 16 if messagerie["mot_de_passe"] else "seize caractères",
                help="Laissez vide pour conserver celui déjà enregistré.",
            )
            c_serveur, c_port = st.columns([2, 1])
            with c_serveur:
                champs["serveur"] = st.text_input(
                    "Serveur",
                    value=messagerie["serveur"] or infos_protocole["serveur_defaut"],
                )
            with c_port:
                champs["port"] = st.number_input(
                    "Port", min_value=1, max_value=65535,
                    value=int(messagerie["port"] or infos_protocole["port_defaut"]),
                )
        else:
            champs["tenant_id"] = st.text_input(
                "Identifiant de locataire (tenant)",
                value=messagerie["tenant_id"],
                placeholder="00000000-0000-0000-0000-000000000000",
            )
            champs["client_id"] = st.text_input(
                "Identifiant de l'application (client)",
                value=messagerie["client_id"],
            )
            champs["client_secret"] = st.text_input(
                "Secret client", type="password",
                placeholder="•" * 16 if messagerie["client_secret"] else "secret Azure",
                help="Laissez vide pour conserver celui déjà enregistré.",
            )

        enregistrer = st.form_submit_button("Relier cette boîte", type="primary",
                                            width="stretch")

    if enregistrer:
        if not adresse_saisie.strip():
            st.error("L'adresse de la boîte est nécessaire.")
        else:
            ok, message = auth.enregistrer_messagerie(utilisateur["email"],
                                                      protocole, **champs)
            (st.success if ok else st.error)(message)
            if ok:
                st.rerun()

    c_test, c_oubli = st.columns(2)
    with c_test:
        if st.button("Tester la connexion", width="stretch",
                     disabled=not messagerie["adresse"]):
            with st.spinner(f"Connexion en {infos_protocole['nom']}…"):
                fournisseur = creer_fournisseur(**messagerie)
                ok, message = fournisseur.tester_connexion()
            st.session_state["gmail_connecte"] = ok
            (st.success if ok else st.error)(message)
    with c_oubli:
        if st.button("Oublier ces identifiants", width="stretch",
                     disabled=not messagerie["adresse"]):
            auth.oublier_gmail(utilisateur["email"])
            st.session_state["gmail_connecte"] = False
            st.rerun()

with droite:
    if messagerie["adresse"]:
        st.markdown(
            pastille(f"{PROTOCOLES[messagerie['protocole']]['nom']} · "
                     f"{messagerie['adresse']}", "sur"),
            unsafe_allow_html=True,
        )
        st.write("")

    if protocole in ("imap", "pop3"):
        with st.expander("Obtenir un mot de passe d'application",
                         expanded=not messagerie["adresse"]):
            st.markdown(
                "Les serveurs modernes refusent le mot de passe habituel du compte "
                "pour ce type de connexion. Il faut un mot de passe dédié.\n\n"
                "**Gmail** : activez la validation en deux étapes, puis ouvrez "
                "`https://myaccount.google.com/apppasswords` et créez un mot de "
                "passe pour MailGuard. Recopiez les seize caractères sans espaces.\n\n"
                "**Autre serveur** : demandez au service informatique l'adresse du "
                "serveur, le port, et si un mot de passe d'application est requis.\n\n"
                "Le mot de passe peut être révoqué à tout moment sans changer celui "
                "du compte."
            )
    else:
        with st.expander("Enregistrer l'application dans Azure",
                         expanded=not messagerie["tenant_id"]):
            st.markdown(
                "Microsoft a supprimé l'accès aux boîtes par simple mot de passe. "
                "Il faut une application enregistrée, et trois éléments que le "
                "service informatique fournit.\n\n"
                "1. Portail Azure, Azure Active Directory, Inscriptions "
                "d'applications, Nouvelle inscription.\n"
                "2. Relevez l'identifiant de locataire et l'identifiant "
                "d'application.\n"
                "3. Certificats et secrets, Nouveau secret client. Le secret ne "
                "s'affiche qu'une fois.\n"
                "4. Autorisations d'API, Microsoft Graph, autorisations "
                "d'application, `Mail.ReadWrite`. **Un administrateur doit "
                "accorder le consentement**, sinon la connexion échouera.\n\n"
                "Sans l'accord du service informatique, ce protocole ne peut pas "
                "fonctionner. Utilisez IMAP en attendant."
            )

# ─── Compte ───# ─── Compte ───────────────────────────────────────────────────────────────────
titre_section("Votre compte")
gauche, droite = st.columns(2, gap="large")

with gauche:
    with st.form("mot_de_passe"):
        st.markdown("**Changer de mot de passe**")
        ancien = st.text_input("Mot de passe actuel", type="password")
        nouveau = st.text_input("Nouveau mot de passe", type="password",
                                help="Au moins 8 caractères, dont une lettre et un chiffre.")
        confirmation = st.text_input("Confirmez le nouveau mot de passe", type="password")
        changer = st.form_submit_button("Modifier", width="stretch")

    if changer:
        if nouveau != confirmation:
            st.error("Les deux mots de passe ne correspondent pas.")
        else:
            ok, message = auth.changer_mot_de_passe(utilisateur["email"], ancien, nouveau)
            (st.success if ok else st.error)(message)

with droite:
    with st.expander("Supprimer mon compte"):
        st.markdown(
            '<div class="mg-alert mg-alert-warn">Votre compte, vos identifiants '
            'Gmail et tout votre historique seront supprimés définitivement. '
            'Les messages déjà déplacés dans Gmail ne sont pas affectés.</div>',
            unsafe_allow_html=True,
        )
        mot_de_passe_suppression = st.text_input("Mot de passe", type="password",
                                                 key="suppression_compte")
        if st.button("Supprimer définitivement mon compte"):
            ok, message = auth.supprimer_compte(utilisateur["email"],
                                                mot_de_passe_suppression)
            if ok:
                fermer_session()
                st.rerun()
            else:
                st.error(message)

titre_section("Action automatique sur les messages détectés")

ACTIONS = {
    "quarantaine": ("Mettre en quarantaine",
                    f"Les menaces partent dans {DOSSIER_QUARANTAINE}, les messages à "
                    f"surveiller dans {DOSSIER_SUSPECTS}."),
    "suspects": ("Tout envoyer dans Suspects",
                 f"Menaces et messages douteux vont ensemble dans {DOSSIER_SUSPECTS}."),
    "marquer": ("Signaler sans déplacer",
                "Rien ne bouge dans la boîte, la décision est seulement enregistrée."),
    "rien": ("Observer",
             "Aucune action sur la boîte. Utile pour évaluer le filtre avant de lui "
             "confier vos messages."),
}

action_config = st.radio(
    "Comportement du filtre",
    options=list(ACTIONS),
    format_func=lambda cle: ACTIONS[cle][0],
    index=list(ACTIONS).index(st.session_state.get("action_config", "quarantaine")),
)
st.caption(ACTIONS[action_config][1])

if st.button("Enregistrer cette action"):
    st.session_state["action_config"] = action_config
    auth.enregistrer_preferences(utilisateur["email"], action_config=action_config)
    st.toast("Action enregistrée sur votre compte.")

# ─── Modèles ──────────────────────────────────────────────────────────────────
titre_section("Modèles chargés")

import mailguard_core as mg

_D = mg.DOSSIER_MODELES


def _existe(*chemin):
    return os.path.exists(os.path.join(_D, *chemin))


MODELES = [
    ("S1 · Domaine", "modeles/CANINE/model.safetensors",
     "CANINE : imitation d'une marque (seuil 0,44)", _existe("modeles", "CANINE", "model.safetensors")),
    ("S2 · Identité", "modeles_signal2_v2.joblib",
     "Gradient Boosting : âge RDAP et certificats (seuil 0,74)", _existe("modeles_signal2_v2.joblib")),
    ("S3 · Liens", "modeles_signal3_final.joblib",
     "Règles + Gradient Boosting du chemin (seuil 0,894)", _existe("modeles_signal3_final.joblib")),
    ("S4 · Contenu", "s4_modele_final/",
     "multilingual-e5 + régression logistique (seuil 0,391)", _existe("s4_modele_final")),
    ("S5 · Authentification", "s5_modele_final/",
     "Gradient Boosting sur 17 indices + veto Nouvelair", _existe("s5_modele_final")),
    ("Fusion", "fusion_modele/",
     "Régression logistique (0,825 suspect · 0,928 frauduleux)", _existe("fusion_modele")),
]



etat = mg.etat_modeles()
if etat.get("charges"):
    st.markdown(
        f'<div class="mg-alert mg-alert-ok">Les cinq modèles et la fusion sont chargés '
        f'<b>une seule fois pour tout le serveur</b>, en '
        f'{etat["duree_chargement_s"]} s, sur <b>{etat["device"]}</b>. '
        f'Ils sont partagés par toutes les sessions ouvertes : un nouvel '
        f'utilisateur qui se connecte ne déclenche aucun rechargement. '
        f'Processus {etat["pid"]}, chargé à {etat["charge_le"][11:19]}.</div>',
        unsafe_allow_html=True,
    )

if not etat.get("charges"):
    st.markdown(
        f'<div class="mg-alert mg-alert-danger">Moteur non chargé : {etat.get("erreur") or "dossier absent"}.<br>'
        f'Dossier attendu : <span class="mg-mono">{_D}</span></div>',
        unsafe_allow_html=True,
    )

for indice, (nom, fichier, role, present) in enumerate(MODELES):
    if indice % 3 == 0:
        colonnes_modeles = st.columns(3, gap="medium")
    colonne = colonnes_modeles[indice % 3]
    couleur = COULEURS["sur"] if present else COULEURS["menace"]
    with colonne:
        st.markdown(
            f'<div class="mg-carte" style="border-top:3px solid {couleur};">'
            f'<h4>{nom}</h4>'
            f'<p class="mg-mono" style="font-size:.78rem;">{fichier}</p>'
            f'<p style="margin-top:.6rem;">{role}</p>'
            f'<p style="margin-top:.8rem;color:{couleur};font-weight:700;font-size:.82rem;">'
            f'{"chargé" if present else "introuvable"}</p></div>',
            unsafe_allow_html=True,
        )

# ─── Base de données ──────────────────────────────────────────────────────────
titre_section(
    "Base de données",
    "Toutes les données de l'application sont stockées dans une base "
    "relationnelle : comptes, identifiants Gmail, préférences, analyses et "
    "scores par signal.",
)

infos = informations_base()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Moteur", infos["moteur"])
c2.metric("Comptes", infos["utilisateurs"])
c3.metric("Analyses", infos["analyses"])
c4.metric("Scores enregistrés", infos["scores"])

st.markdown(
    f'<div class="mg-carte"><h4>Emplacement</h4>'
    f'<p class="mg-mono" style="font-size:.82rem;word-break:break-all;">'
    f'{infos["url"]}</p>'
    + (f'<p style="margin-top:.6rem;">Taille du fichier : '
       f'<b>{infos["taille_ko"]} Ko</b></p>' if "taille_ko" in infos else "")
    + f'<p style="margin-top:.9rem;">Le schéma comporte cinq tables reliées par '
      f'des clés étrangères, avec suppression en cascade : supprimer un compte '
      f'supprime ses analyses, ses scores, ses préférences et ses identifiants '
      f'Gmail, sans laisser de données orphelines.</p>'
      f'<p style="margin-top:.7rem;color:{COULEURS["faible"]};font-size:.86rem;">'
      f'Pour passer sur MySQL ou PostgreSQL, renseignez '
      f'<span class="mg-mono">MAILGUARD_DATABASE_URL</span> dans le fichier '
      f'<span class="mg-mono">.env</span>. Aucune requête du code n\'utilise de '
      f'syntaxe propre à un moteur.</p></div>',
    unsafe_allow_html=True,
)

# ─── Données conservées ───────────────────────────────────────────────────────
titre_section("Données conservées")

stats = get_stats(id_utilisateur())
c1, c2, c3, c4 = st.columns(4)
c1.metric("Analyses conservées", stats["total"])
c2.metric("Frauduleux", stats["dangereux"])
c3.metric("Suspects", stats["suspects"])
c4.metric("Score moyen", f"{stats['score_moyen']:.3f}")

with st.expander("Effacer l'historique"):
    st.markdown(
        f'<div class="mg-alert mg-alert-warn">Cette action supprime vos '
        f'{stats["total"]} analyses. Elle est définitive et ne concerne que '
        f'votre compte.</div>',
        unsafe_allow_html=True,
    )
    confirmation = st.text_input("Tapez CONFIRMER pour effacer l'historique")
    if st.button("Effacer l'historique"):
        if confirmation.strip().upper() == "CONFIRMER":
            effacer_historique(id_utilisateur())
            st.success("Historique effacé.")
        else:
            st.error("La confirmation ne correspond pas. Rien n'a été supprimé.")
