"""
utils/auth_ui.py
=================
Écrans de connexion et d'inscription, et verrou d'accès aux pages.

Streamlit affiche toutes les pages du dossier `pages/` dans le menu, sans
notion d'autorisation. Le verrou est donc posé dans chaque page : un appel à
`exiger_connexion()` en tête de fichier interrompt le rendu et affiche le
formulaire tant que personne n'est authentifié.

La session vit dans `st.session_state`. Elle se termine à la fermeture de
l'onglet, ce qui est le comportement attendu pour un poste partagé.
"""

import streamlit as st

from services import auth_service as auth
from utils.ui_helpers import COULEURS, appliquer_theme, pastille  # noqa: F401

CLE_SESSION = "utilisateur"


# ─────────────────────────────────────────────────────────────────────────
# État de session
# ─────────────────────────────────────────────────────────────────────────

def utilisateur_actuel() -> dict | None:
    return st.session_state.get(CLE_SESSION)


def id_utilisateur() -> str | None:
    """Identifiant servant à nommer le fichier d'historique du compte."""
    utilisateur = utilisateur_actuel()
    return utilisateur["identifiant"] if utilisateur else None


def est_connecte() -> bool:
    return utilisateur_actuel() is not None


def est_admin() -> bool:
    """Retourne True si l'utilisateur connecté est un administrateur."""
    u = utilisateur_actuel()
    return u is not None and u.get("role") == "admin"


def exiger_admin():
    """Verrou admin : affiche une erreur et arrête le rendu si non-admin."""
    if not est_connecte():
        ecran_authentification()
    if not est_admin():
        st.error("⛔ Accès réservé aux administrateurs.")
        st.stop()


def ouvrir_session(utilisateur: dict):
    st.session_state[CLE_SESSION] = utilisateur
    # Les admins n'ont pas de préférences utilisateur
    if utilisateur.get("role") == "admin":
        st.session_state.setdefault("seuil_suspect", 0.825)
        st.session_state.setdefault("seuil_dangereux", 0.928)
        st.session_state.setdefault("action_config", "quarantaine")
    else:
        preferences = auth.lire_preferences(utilisateur["email"])
        st.session_state["seuil_suspect"] = preferences["seuil_suspect"]
        st.session_state["seuil_dangereux"] = preferences["seuil_dangereux"]
        st.session_state["action_config"] = preferences["action_config"]
    # Anciennes préférences (0,25 / 0,50) → seuils appris par la fusion (0,825 / 0,928)
    from services.quarantine_service import migrer_seuils
    st.session_state["seuil_suspect"], st.session_state["seuil_dangereux"] = migrer_seuils(
        st.session_state.get("seuil_suspect"), st.session_state.get("seuil_dangereux"))


def fermer_session():
    """Efface tout ce qui appartenait au compte, sans laisser de résidu."""
    try:
        from services.audit_service import journaliser
        u = st.session_state.get(CLE_SESSION) or {}
        if u.get("email"):
            journaliser("LOGOUT", "admin" if u.get("role") == "admin" else "utilisateur",
                        u["email"], "déconnexion", acteur=u["email"])
    except Exception:
        pass
    for cle in (CLE_SESSION, "journal", "messages_session", "nb_analyses_session",
                "derniere_alerte", "gmail_connecte", "surveillance_active",
                "ex_domaine", "ex_texte"):
        st.session_state.pop(cle, None)


# ─────────────────────────────────────────────────────────────────────────
# Formulaires
# ─────────────────────────────────────────────────────────────────────────

def _formulaire_connexion():
    with st.form("connexion"):
        email = st.text_input("Adresse email", placeholder="prenom.nom@exemple.com")
        mot_de_passe = st.text_input("Mot de passe", type="password")
        valider = st.form_submit_button("Se connecter", type="primary", width="stretch")

    if valider:
        if not email or not mot_de_passe:
            st.error("Renseignez votre adresse et votre mot de passe.")
            return
        ok, message, utilisateur = auth.connecter(email, mot_de_passe)
        if ok:
            ouvrir_session(utilisateur)
            role = utilisateur.get("role", "user")
            if role == "admin":
                st.success(f"✅ {message} — Accès administrateur accordé.")
            else:
                st.success(message)
            st.rerun()
        else:
            # Distinguer le cas "en attente" avec un message plus visible
            if "attente" in message.lower():
                st.warning(f"⏳ {message}")
            else:
                st.error(message)


def _formulaire_inscription():
    with st.form("inscription"):
        nom = st.text_input("Nom affiché", placeholder="facultatif")
        email = st.text_input(
            "Adresse email de la boîte à protéger",
            placeholder="prenom.nom@nouvelair.com",
            key="inscription_email",
            help="C'est cette boîte que MailGuard surveillera. Elle est reprise "
                 "automatiquement dans vos réglages : vous n'aurez pas à la "
                 "ressaisir.",
        )
        mot_de_passe = st.text_input(
            "Mot de passe", type="password",
            help="Au moins 8 caractères, dont une lettre et un chiffre.")
        confirmation = st.text_input("Confirmez le mot de passe", type="password")
        valider = st.form_submit_button("Créer mon compte", type="primary",
                                        width="stretch")

    if valider:
        if mot_de_passe != confirmation:
            st.error("Les deux mots de passe ne correspondent pas.")
            return
        ok, message = auth.inscrire(email, mot_de_passe, nom)
        if ok:
            st.success(message)
            st.info("Passez à l'onglet « Se connecter » pour ouvrir votre session. "
                    "Votre adresse est déjà enregistrée comme boîte à surveiller ; "
                    "il ne restera qu'à fournir un mot de passe d'application.")
        else:
            st.error(message)


CSS_AUTHENTIFICATION = """
<style>
/* Tant que personne n'est connecté, le menu des pages est masqué : laisser
   voir des écrans verrouillés n'apporte rien et prête à confusion. */
[data-testid="stSidebar"],
[data-testid="stSidebarNav"],
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"] { display:none !important; }
[data-testid="stHeader"] { background:transparent; }

.block-container { max-width:560px !important; padding-top:3.4rem !important;
                   padding-bottom:4rem !important; }

/* L'aurore est plus franche ici : c'est la seule page sans contenu autour. */
.stApp::before { height:100% !important; opacity:.16 !important; }

.mg-auth-marque { display:flex; align-items:center; gap:.85rem; margin-bottom:2.2rem; }
.mg-auth-pastille { width:46px; height:46px; border-radius:13px; flex-shrink:0;
  background:linear-gradient(101deg,#00D4FF,#635BFF 55%,#FF5996);
  box-shadow:0 8px 20px -8px rgba(99,91,255,.7); }
.mg-auth-nom { font-size:1.5rem; font-weight:800; letter-spacing:-.04em; color:#0A2540;
               line-height:1.1; }
.mg-auth-sous { font-size:.82rem; color:#8792A2; }

.mg-auth-titre { font-size:2.4rem; font-weight:800; letter-spacing:-.045em;
                 color:#0A2540; line-height:1.1; margin:0 0 .7rem 0; }
.mg-auth-intro { color:#425466; font-size:1.02rem; line-height:1.6; margin:0 0 2rem 0; }

.mg-auth-carte { background:#FFFFFF; border:1px solid #E3E8EE; border-radius:20px;
  padding:1.9rem 2rem 1.4rem 2rem;
  box-shadow:0 13px 27px -5px rgba(50,50,93,.15), 0 8px 16px -8px rgba(10,37,64,.16); }

.mg-auth-notes { margin-top:1.7rem; display:flex; flex-direction:column; gap:.7rem; }
.mg-auth-note { display:flex; gap:.7rem; align-items:flex-start; font-size:.87rem;
                color:#425466; line-height:1.5; }
.mg-auth-puce { width:6px; height:6px; border-radius:99px; background:#635BFF;
                margin-top:.5rem; flex-shrink:0; }
.mg-auth-bas { margin-top:2rem; font-size:.8rem; color:#8792A2; line-height:1.6;
               border-top:1px solid #E3E8EE; padding-top:1.1rem; }
</style>
"""


def ecran_authentification():
    """Écran plein cadre affiché tant que personne n'est connecté."""
    st.markdown(CSS_AUTHENTIFICATION, unsafe_allow_html=True)

    st.markdown(
        '<div class="mg-auth-marque">'
        '<div class="mg-auth-pastille"></div>'
        '<div><div class="mg-auth-nom">MailGuard</div>'
        '<div class="mg-auth-sous">Nouvelair · Sécurité de la messagerie</div>'
        '</div></div>'
        '<h1 class="mg-auth-titre">Le message frauduleux '
        '<span class="mg-degrade">n\'arrive jamais</span> jusqu\'à vous</h1>'
        '<p class="mg-auth-intro">Connectez-vous pour analyser votre boîte. '
        'L\'adresse que vous indiquez est celle que MailGuard surveillera.</p>',
        unsafe_allow_html=True,
    )

    onglet_connexion, onglet_inscription = st.tabs(
        ["Se connecter", "Créer un compte"])
    with onglet_connexion:
        _formulaire_connexion()
    with onglet_inscription:
        _formulaire_inscription()

    st.markdown(
        '<div class="mg-auth-notes">'
        '<div class="mg-auth-note"><span class="mg-auth-puce"></span>'
        'Votre mot de passe n\'est jamais stocké : seule une empreinte à sel '
        'aléatoire est conservée.</div>'
        '<div class="mg-auth-note"><span class="mg-auth-puce"></span>'
        'Le mot de passe d\'application de votre boîte est chiffré avant d\'être '
        'écrit en base.</div>'
        '<div class="mg-auth-note"><span class="mg-auth-puce"></span>'
        'Vos analyses, vos seuils et vos identifiants n\'appartiennent qu\'à '
        'votre compte.</div>'
        '</div>'
        '<div class="mg-auth-bas">Installation locale, sans vérification '
        'd\'adresse par email ni récupération de mot de passe oublié. '
        'Notez vos identifiants.</div>',
        unsafe_allow_html=True,
    )

    st.stop()


# ─────────────────────────────────────────────────────────────────────────
# Verrou et barre latérale
# ─────────────────────────────────────────────────────────────────────────

def exiger_connexion():
    """À appeler en tête de chaque page, juste après appliquer_theme()."""
    if not est_connecte():
        ecran_authentification()


def modele_disponible() -> bool:
    """Vérifie que les modèles ML sont chargés. Retente si le dossier existe."""
    try:
        import mailguard_core as mg
        return mg._recharger_si_absent()
    except Exception:
        return False


def banner_modele_absent():
    """Affiche un bandeau d'avertissement si les modèles MailGuard ne sont pas chargés."""
    if not modele_disponible():
        st.warning(
            "**Modèles MailGuard manquants** — L'analyse des emails est désactivée.  \n"
            "Copiez le dossier `modeles_mailguard` (5 signaux + fusion, avec "
            "`modeles/CANINE/model.safetensors`) à la racine du projet, ou indiquez "
            "son chemin avec `MAILGUARD_MODELES` dans le fichier `.env`.",
        )
        return True
    return False


def barre_utilisateur():
    """Bloc d'identité et bouton de déconnexion, dans la barre latérale."""
    utilisateur = utilisateur_actuel()
    if not utilisateur:
        return

    role = utilisateur.get("role", "user")
    couleur_avatar = "#E8590C" if role == "admin" else COULEURS["violet"]

    with st.sidebar:
        initiale = (utilisateur["nom"] or utilisateur["email"])[0].upper()
        badge_role = (
            '<span style="font-size:.68rem;background:#E8590C;color:#fff;'
            'border-radius:4px;padding:1px 6px;margin-left:4px;font-weight:700;">'
            'ADMIN</span>' if role == "admin" else ""
        )
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:.7rem;'
            f'padding:.2rem 0 .9rem 0;">'
            f'<div style="width:38px;height:38px;border-radius:50%;flex-shrink:0;'
            f'background:{couleur_avatar};color:#fff;display:grid;'
            f'place-items:center;font-weight:700;font-size:1.05rem;">{initiale}</div>'
            f'<div style="min-width:0;">'
            f'<div style="font-weight:700;color:{COULEURS["encre"]};'
            f'font-size:.95rem;">{utilisateur["nom"]}{badge_role}</div>'
            f'<div style="font-size:.75rem;color:{COULEURS["faible"]};'
            f'overflow:hidden;text-overflow:ellipsis;">{utilisateur["email"]}</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

        if role == "admin":
            # Afficher le nombre de comptes en attente
            nb_attente = auth.nb_comptes_en_attente()
            if nb_attente > 0:
                st.markdown(
                    f'<div style="background:#FFF3CD;border:1px solid #FFCA2C;'
                    f'border-radius:8px;padding:.5rem .8rem;font-size:.82rem;'
                    f'color:#664D03;margin-bottom:.5rem;">'
                    f'⚠️ <b>{nb_attente}</b> compte(s) en attente de validation</div>',
                    unsafe_allow_html=True,
                )
        else:
            # Pour les utilisateurs normaux : état de la boîte mail
            m = auth.lire_messagerie(utilisateur["email"])
            if m["protocole"] == "graph":
                complet = all([m["adresse"], m["tenant_id"], m["client_id"],
                               m["client_secret"]])
            else:
                complet = bool(m["adresse"] and m["mot_de_passe"])

            if complet:
                st.markdown(pastille(f"Boîte reliée ({m['protocole'].upper()})", "sur"),
                            unsafe_allow_html=True)
            elif m["adresse"]:
                st.markdown(pastille("Mot de passe d'application manquant", "veille"),
                            unsafe_allow_html=True)
            else:
                st.markdown(pastille("Aucune boîte reliée", "neutre"),
                            unsafe_allow_html=True)

        if st.button("Se déconnecter", width="stretch"):
            fermer_session()
            st.rerun()
        st.divider()
