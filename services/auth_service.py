"""
services/auth_service.py
=========================
Comptes utilisateurs : inscription, connexion, et cloisonnement des données.

Principes retenus
-----------------
Un mot de passe n'est jamais stocké en clair. Il est haché par PBKDF2-HMAC-SHA256
avec 240 000 itérations et un sel aléatoire de 16 octets propre à chaque compte.
La vérification se fait en temps constant, pour ne pas laisser fuiter
d'information par la durée de la comparaison.

Le mot de passe d'application Gmail, lui, doit être restitué en clair au moment
de la connexion IMAP : il ne peut donc pas être haché. Il est chiffré avec
Fernet (AES-128 en mode CBC, authentifié par HMAC). La clé de chiffrement vit
dans le fichier .env sous MAILGUARD_SECRET_KEY et n'est jamais écrite dans le
magasin d'utilisateurs.

Chaque compte dispose de son propre fichier d'historique, de ses propres
identifiants Gmail et de ses propres seuils de décision. Deux utilisateurs de
la même installation ne voient jamais les analyses l'un de l'autre.

Persistance
-----------
Les comptes vivent dans la table `utilisateurs`, leurs identifiants Gmail dans
`identifiants_gmail` et leurs réglages dans `preferences`. La suppression d'un
compte entraîne en cascade celle de ses analyses, de ses scores, de ses
préférences et de ses identifiants.

Limites assumées, à mentionner en soutenance
--------------------------------------------
Il n'y a pas de vérification d'adresse par email, ni de récupération de mot de
passe oublié : un compte perdu doit être recréé. Rien ne limite le nombre de
tentatives de connexion. La session vit dans st.session_state, donc elle se
termine à la fermeture de l'onglet.
"""

import base64
import hashlib
import hmac
import os
import re
import unicodedata
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken

from services.database import (
    Analyse, Administrateur, IdentifiantGmail, Preference, Utilisateur, session,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHEMIN_ENV = os.path.join(BASE_DIR, ".env")

ITERATIONS = 240_000
LONGUEUR_SEL = 16
LONGUEUR_MDP_MIN = 8

MOTIF_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")


# ─────────────────────────────────────────────────────────────────────────
# Clé de chiffrement
# ─────────────────────────────────────────────────────────────────────────

def _obtenir_cle() -> bytes:
    """Lit la clé de chiffrement, ou en crée une au premier lancement.

    La clé est écrite dans .env plutôt que dans le magasin d'utilisateurs :
    quelqu'un qui récupérerait le seul fichier JSON ne pourrait pas déchiffrer
    les mots de passe d'application qu'il contient.
    """
    cle = os.getenv("MAILGUARD_SECRET_KEY", "").strip()
    if cle:
        return cle.encode()

    cle = Fernet.generate_key()
    ligne = f'\nMAILGUARD_SECRET_KEY={cle.decode()}\n'
    try:
        with open(CHEMIN_ENV, "a", encoding="utf-8") as f:
            f.write(ligne)
    except OSError:
        pass
    os.environ["MAILGUARD_SECRET_KEY"] = cle.decode()
    return cle


def chiffrer(texte: str) -> str:
    if not texte:
        return ""
    return Fernet(_obtenir_cle()).encrypt(texte.encode()).decode()


def dechiffrer(jeton: str) -> str:
    if not jeton:
        return ""
    try:
        return Fernet(_obtenir_cle()).decrypt(jeton.encode()).decode()
    except (InvalidToken, ValueError):
        # clé changée ou fichier corrompu : on ne fait pas planter l'application
        return ""


# ─────────────────────────────────────────────────────────────────────────
# Mots de passe
# ─────────────────────────────────────────────────────────────────────────

def hacher_mot_de_passe(mot_de_passe: str, sel: bytes = None) -> tuple[str, str]:
    """Renvoie (empreinte, sel) encodés en base64."""
    sel = sel or os.urandom(LONGUEUR_SEL)
    empreinte = hashlib.pbkdf2_hmac(
        "sha256", mot_de_passe.encode("utf-8"), sel, ITERATIONS
    )
    return base64.b64encode(empreinte).decode(), base64.b64encode(sel).decode()


def verifier_mot_de_passe(mot_de_passe: str, empreinte_b64: str, sel_b64: str) -> bool:
    """Comparaison en temps constant, pour ne pas trahir la réponse par la durée."""
    try:
        sel = base64.b64decode(sel_b64)
    except (ValueError, TypeError):
        return False
    calculee, _ = hacher_mot_de_passe(mot_de_passe, sel)
    return hmac.compare_digest(calculee, empreinte_b64)


def evaluer_mot_de_passe(mot_de_passe: str) -> tuple[bool, str]:
    """Exigences minimales, volontairement lisibles par l'utilisateur."""
    if len(mot_de_passe) < LONGUEUR_MDP_MIN:
        return False, f"Le mot de passe doit faire au moins {LONGUEUR_MDP_MIN} caractères."
    if not any(c.isdigit() for c in mot_de_passe):
        return False, "Le mot de passe doit contenir au moins un chiffre."
    if not any(c.isalpha() for c in mot_de_passe):
        return False, "Le mot de passe doit contenir au moins une lettre."
    return True, "Mot de passe accepté."


# ─────────────────────────────────────────────────────────────────────────
# Magasin de comptes
# ─────────────────────────────────────────────────────────────────────────

def normaliser_email(email: str) -> str:
    return unicodedata.normalize("NFKC", (email or "").strip()).lower()


def _compte(s, email: str):
    return s.query(Utilisateur).filter_by(email=normaliser_email(email)).first()


def identifiant_utilisateur(email: str) -> str:
    """Identifiant court et stable, derive de l'adresse.

    Il sert de cle publique du compte : on ne fait jamais circuler la cle
    primaire de la base ni l'adresse email dans l'interface.
    """
    return hashlib.sha256(normaliser_email(email).encode()).hexdigest()[:16]


def compte_existe(email: str) -> bool:
    with session() as s:
        return _compte(s, email) is not None


def charger_comptes() -> dict:
    """Vue en dictionnaire de la table des utilisateurs.

    Conservee pour les outils de diagnostic et la migration. L'application
    n'en depend pas.
    """
    with session() as s:
        comptes = {}
        for u in s.query(Utilisateur).all():
            comptes[u.email] = {
                "identifiant": u.identifiant,
                "nom": u.nom,
                "empreinte": u.empreinte,
                "sel": u.sel,
                "cree_le": u.cree_le.isoformat() if u.cree_le else None,
                "derniere_connexion": (u.derniere_connexion.isoformat()
                                       if u.derniere_connexion else None),
                "gmail_address": u.gmail.adresse if u.gmail else "",
                "gmail_password_chiffre": (u.gmail.mot_de_passe_chiffre
                                           if u.gmail else ""),
                "seuil_suspect": u.preferences.seuil_suspect if u.preferences else 0.825,
                "seuil_dangereux": (u.preferences.seuil_dangereux
                                    if u.preferences else 0.928),
                "action_config": (u.preferences.action_config
                                  if u.preferences else "quarantaine"),
            }
        return comptes


# ─────────────────────────────────────────────────────────────────────────
# Inscription et connexion
# ─────────────────────────────────────────────────────────────────────────

def inscrire(email: str, mot_de_passe: str, nom: str = "") -> tuple[bool, str]:
    email = normaliser_email(email)

    if not MOTIF_EMAIL.match(email):
        return False, "Cette adresse email n'est pas valide."

    valide, message = evaluer_mot_de_passe(mot_de_passe)
    if not valide:
        return False, message

    empreinte, sel = hacher_mot_de_passe(mot_de_passe)

    with session() as s:
        if _compte(s, email) is not None:
            return False, "Un compte existe déjà avec cette adresse."

        utilisateur = Utilisateur(
            email=email,
            identifiant=identifiant_utilisateur(email),
            nom=(nom or email.split("@")[0]).strip(),
            empreinte=empreinte,
            sel=sel,
            cree_le=datetime.now(),
            role="user",
            statut="pending",  # Le compte doit être activé par un admin
        )
        utilisateur.preferences = Preference()
        utilisateur.gmail = IdentifiantGmail(adresse=email, protocole="imap")
        s.add(utilisateur)
        s.commit()

    return True, ("Compte créé. Votre demande est en attente de validation "
                  "par un administrateur. Vous serez notifié dès l'activation.")


def connecter(email: str, mot_de_passe: str) -> tuple[bool, str, dict]:
    """Connexion unifiée : cherche d'abord dans administrateurs, puis utilisateurs.

    Retourne un dict enrichi avec les clés 'role' et 'statut'.
    """
    email = normaliser_email(email)
    echec = "Adresse ou mot de passe incorrect."

    with session() as s:
        # ── 1. Vérifier d'abord les administrateurs ──────────────────────
        admin = s.query(Administrateur).filter_by(email=email).first()
        if admin is not None:
            if not verifier_mot_de_passe(mot_de_passe, admin.empreinte, admin.sel):
                hacher_mot_de_passe(mot_de_passe)  # timing constant
                return False, echec, {}
            if admin.statut == "suspended":
                return False, "Ce compte administrateur est suspendu.", {}
            admin.derniere_connexion = datetime.now()
            s.commit()
            return True, f"Bienvenue, {admin.nom} (Admin).", {
                "email": admin.email,
                "identifiant": admin.identifiant,
                "nom": admin.nom,
                "role": "admin",
                "statut": "active",
            }

        # ── 2. Sinon chercher dans les utilisateurs ───────────────────────
        utilisateur = _compte(s, email)

        if utilisateur is None:
            hacher_mot_de_passe(mot_de_passe)
            return False, echec, {}

        if not verifier_mot_de_passe(mot_de_passe, utilisateur.empreinte,
                                     utilisateur.sel):
            return False, echec, {}

        # Vérification du statut : pending = pas encore validé par un admin
        statut = getattr(utilisateur, "statut", "active")
        if statut == "pending":
            return (False,
                    "Votre compte est en attente de validation par un administrateur. "
                    "Vous serez notifié dès son activation.",
                    {})
        if statut != "active":
            # suspendu (ou tout autre statut) : l'accès est refusé
            return False, "Ce compte est suspendu. Contactez un administrateur.", {}

        utilisateur.derniere_connexion = datetime.now()
        s.commit()

        return True, f"Bienvenue, {utilisateur.nom}.", {
            "email": utilisateur.email,
            "identifiant": utilisateur.identifiant,
            "nom": utilisateur.nom,
            "role": getattr(utilisateur, "role", "user"),
            "statut": getattr(utilisateur, "statut", "active"),
        }


def changer_mot_de_passe(email: str, ancien: str, nouveau: str) -> tuple[bool, str]:
    with session() as s:
        utilisateur = _compte(s, email)
        if utilisateur is None:
            return False, "Compte introuvable."
        if not verifier_mot_de_passe(ancien, utilisateur.empreinte, utilisateur.sel):
            return False, "Le mot de passe actuel est incorrect."
        valide, message = evaluer_mot_de_passe(nouveau)
        if not valide:
            return False, message
        utilisateur.empreinte, utilisateur.sel = hacher_mot_de_passe(nouveau)
        s.commit()
    return True, "Mot de passe modifié."


# ─────────────────────────────────────────────────────────────────────────
# Préférences et identifiants Gmail, propres à chaque compte
# ─────────────────────────────────────────────────────────────────────────

def lire_preferences(email: str) -> dict:
    with session() as s:
        utilisateur = _compte(s, email)
        if utilisateur is None:
            return {"gmail_address": "", "seuil_suspect": 0.825,
                    "seuil_dangereux": 0.928, "action_config": "quarantaine"}
        preferences = utilisateur.preferences or Preference()
        return {
            "gmail_address": utilisateur.gmail.adresse if utilisateur.gmail else "",
            "seuil_suspect": preferences.seuil_suspect,
            "seuil_dangereux": preferences.seuil_dangereux,
            "action_config": preferences.action_config,
        }


def enregistrer_preferences(email: str, **valeurs) -> bool:
    autorisees = {"seuil_suspect", "seuil_dangereux", "action_config"}
    with session() as s:
        utilisateur = _compte(s, email)
        if utilisateur is None:
            return False
        if "nom" in valeurs:
            utilisateur.nom = valeurs["nom"]
        if utilisateur.preferences is None:
            utilisateur.preferences = Preference()
        for cle, valeur in valeurs.items():
            if cle in autorisees:
                setattr(utilisateur.preferences, cle, valeur)
        s.commit()
    return True


def enregistrer_messagerie(email: str, protocole: str, **champs) -> tuple[bool, str]:
    """Enregistre les identifiants de messagerie, quel que soit le protocole.

    Les secrets (mot de passe d'application, secret client Azure) sont chiffres
    avant d'etre ecrits en base. Un champ laisse vide conserve la valeur
    precedente, pour ne pas obliger a ressaisir un secret a chaque reglage.
    """
    with session() as s:
        utilisateur = _compte(s, email)
        if utilisateur is None:
            return False, "Compte introuvable."
        if utilisateur.gmail is None:
            utilisateur.gmail = IdentifiantGmail()

        cible = utilisateur.gmail
        cible.protocole = (protocole or "imap").lower()
        cible.adresse = (champs.get("adresse") or "").strip()
        cible.serveur = (champs.get("serveur") or "").strip()
        cible.port = int(champs.get("port") or 0)
        cible.tenant_id = (champs.get("tenant_id") or "").strip()
        cible.client_id = (champs.get("client_id") or "").strip()

        secret = (champs.get("mot_de_passe") or "").replace(" ", "")
        if secret:
            cible.mot_de_passe_chiffre = chiffrer(secret)
        secret_client = (champs.get("client_secret") or "").strip()
        if secret_client:
            cible.client_secret_chiffre = chiffrer(secret_client)

        cible.maj_le = datetime.now()
        s.commit()
    return True, "Identifiants enregistrés, secrets chiffrés."


def lire_messagerie(email: str) -> dict:
    """Renvoie tous les identifiants de messagerie, secrets dechiffres."""
    vide = {"protocole": "imap", "adresse": "", "mot_de_passe": "",
            "serveur": "", "port": 0, "tenant_id": "", "client_id": "",
            "client_secret": ""}
    with session() as s:
        utilisateur = _compte(s, email)
        if utilisateur is None or utilisateur.gmail is None:
            return vide
        g = utilisateur.gmail
        return {
            "protocole": g.protocole or "imap",
            "adresse": g.adresse,
            "mot_de_passe": dechiffrer(g.mot_de_passe_chiffre),
            "serveur": g.serveur,
            "port": g.port,
            "tenant_id": g.tenant_id,
            "client_id": g.client_id,
            "client_secret": dechiffrer(g.client_secret_chiffre),
        }


def enregistrer_gmail(email: str, adresse_gmail: str,
                      mot_de_passe_app: str) -> tuple[bool, str]:
    """Le mot de passe d'application est chiffré avant d'être écrit en base."""
    with session() as s:
        utilisateur = _compte(s, email)
        if utilisateur is None:
            return False, "Compte introuvable."
        if utilisateur.gmail is None:
            utilisateur.gmail = IdentifiantGmail()
        utilisateur.gmail.adresse = adresse_gmail.strip()
        utilisateur.gmail.mot_de_passe_chiffre = chiffrer(
            mot_de_passe_app.replace(" ", ""))
        utilisateur.gmail.maj_le = datetime.now()
        s.commit()
    return True, "Identifiants Gmail enregistrés et chiffrés."


def lire_gmail(email: str) -> tuple[str, str]:
    """Renvoie (adresse, mot de passe d'application déchiffré)."""
    with session() as s:
        utilisateur = _compte(s, email)
        if utilisateur is None or utilisateur.gmail is None:
            return "", ""
        return (utilisateur.gmail.adresse,
                dechiffrer(utilisateur.gmail.mot_de_passe_chiffre))


def oublier_gmail(email: str) -> bool:
    """Efface tous les identifiants de messagerie du compte."""
    with session() as s:
        utilisateur = _compte(s, email)
        if utilisateur is None or utilisateur.gmail is None:
            return False
        g = utilisateur.gmail
        g.adresse = g.mot_de_passe_chiffre = g.serveur = ""
        g.tenant_id = g.client_id = g.client_secret_chiffre = ""
        g.port = 0
        s.commit()
    return True


def supprimer_compte(email: str, mot_de_passe: str) -> tuple[bool, str]:
    """La suppression en cascade emporte analyses, scores, preferences et
    identifiants Gmail : aucune donnee orpheline ne subsiste."""
    with session() as s:
        utilisateur = _compte(s, email)
        if utilisateur is None:
            return False, "Compte introuvable."
        if not verifier_mot_de_passe(mot_de_passe, utilisateur.empreinte,
                                     utilisateur.sel):
            return False, "Mot de passe incorrect."
        s.delete(utilisateur)
        s.commit()
    return True, "Compte et historique supprimés."


# ─────────────────────────────────────────────────────────────────────────
# Gestion des comptes utilisateurs par l'admin
# ─────────────────────────────────────────────────────────────────────────

def lister_utilisateurs(statut_filtre: str = "all") -> list[dict]:
    """Retourne tous les utilisateurs, avec filtre optionnel sur le statut."""
    with session() as s:
        q = s.query(Utilisateur)
        if statut_filtre == "pending":
            q = q.filter(Utilisateur.statut == "pending")
        elif statut_filtre == "active":
            q = q.filter(Utilisateur.statut == "active")
        utilisateurs = []
        for u in q.order_by(Utilisateur.cree_le.desc()).all():
            from services.database import Analyse
            nb_analyses = s.query(Analyse).filter_by(utilisateur_id=u.id).count()
            utilisateurs.append({
                "id": u.id,
                "email": u.email,
                "nom": u.nom,
                "role": getattr(u, "role", "user"),
                "statut": getattr(u, "statut", "active"),
                "cree_le": u.cree_le.strftime("%Y-%m-%d %H:%M:%S") if u.cree_le else "",
                "derniere_connexion": (u.derniere_connexion.strftime("%Y-%m-%d %H:%M:%S")
                                       if u.derniere_connexion else "—"),
                "nb_analyses": nb_analyses,
            })
        return utilisateurs


def activer_compte(email: str) -> tuple[bool, str]:
    """Active un compte utilisateur en attente."""
    with session() as s:
        utilisateur = _compte(s, email)
        if utilisateur is None:
            return False, "Compte introuvable."
        utilisateur.statut = "active"
        s.commit()
    return True, f"Compte {email} activé avec succès."


def suspendre_compte(email: str) -> tuple[bool, str]:
    """Suspend un compte utilisateur actif."""
    with session() as s:
        utilisateur = _compte(s, email)
        if utilisateur is None:
            return False, "Compte introuvable."
        utilisateur.statut = "suspended"
        s.commit()
    return True, f"Compte {email} suspendu."


def supprimer_compte_admin(email: str) -> tuple[bool, str]:
    """Suppression d'un compte par un administrateur (sans vérification de mdp)."""
    with session() as s:
        utilisateur = _compte(s, email)
        if utilisateur is None:
            return False, "Compte introuvable."
        s.delete(utilisateur)
        s.commit()
    return True, f"Compte {email} supprimé."


def nb_comptes_en_attente() -> int:
    """Nombre de comptes en attente de validation — utilisé pour les badges."""
    with session() as s:
        return s.query(Utilisateur).filter(Utilisateur.statut == "pending").count()


# ─────────────────────────────────────────────────────────────────────────
# Gestion des administrateurs
# ─────────────────────────────────────────────────────────────────────────

def _admin_par_email(s, email: str):
    return s.query(Administrateur).filter_by(email=normaliser_email(email)).first()


def admin_existe(email: str) -> bool:
    with session() as s:
        return _admin_par_email(s, email) is not None


def creer_admin(email: str, mot_de_passe: str, nom: str = "") -> tuple[bool, str]:
    """Crée un compte administrateur. Réservé à l'admin principal."""
    email = normaliser_email(email)
    if not MOTIF_EMAIL.match(email):
        return False, "Adresse email invalide."
    valide, message = evaluer_mot_de_passe(mot_de_passe)
    if not valide:
        return False, message
    with session() as s:
        if _admin_par_email(s, email) is not None:
            return False, "Un administrateur avec cet email existe déjà."
        empreinte, sel = hacher_mot_de_passe(mot_de_passe)
        admin = Administrateur(
            email=email,
            identifiant=identifiant_utilisateur(email),
            nom=(nom or email.split("@")[0]).strip(),
            empreinte=empreinte,
            sel=sel,
            cree_le=datetime.now(),
            statut="active",
        )
        s.add(admin)
        s.commit()
    return True, f"Administrateur {email} créé avec succès."


def lister_admins(statut_filtre: str = "all") -> list[dict]:
    """Retourne la liste de tous les administrateurs."""
    with session() as s:
        q = s.query(Administrateur)
        if statut_filtre != "all":
            q = q.filter(Administrateur.statut == statut_filtre)
        admins = []
        for a in q.order_by(Administrateur.cree_le.asc()).all():
            admins.append({
                "id": a.id,
                "email": a.email,
                "nom": a.nom,
                "statut": a.statut,
                "cree_le": a.cree_le.strftime("%Y-%m-%d %H:%M:%S") if a.cree_le else "",
                "derniere_connexion": (a.derniere_connexion.strftime("%Y-%m-%d %H:%M:%S")
                                       if a.derniere_connexion else "—"),
            })
        return admins


def changer_statut_admin(email: str, nouveau_statut: str) -> tuple[bool, str]:
    """Active ou suspend un administrateur."""
    with session() as s:
        admin = _admin_par_email(s, email)
        if admin is None:
            return False, "Administrateur introuvable."
        admin.statut = nouveau_statut
        s.commit()
    return True, f"Statut de {email} mis à jour : {nouveau_statut}."


def supprimer_admin(email: str, email_demandeur: str) -> tuple[bool, str]:
    """Supprime un admin. Un admin ne peut pas se supprimer lui-même."""
    if normaliser_email(email) == normaliser_email(email_demandeur):
        return False, "Vous ne pouvez pas supprimer votre propre compte admin."
    with session() as s:
        admin = _admin_par_email(s, email)
        if admin is None:
            return False, "Administrateur introuvable."
        # Vérifier qu'il reste au moins un autre admin actif
        nb_actifs = s.query(Administrateur).filter(
            Administrateur.statut == "active",
            Administrateur.email != normaliser_email(email)
        ).count()
        if nb_actifs == 0:
            return False, "Impossible : il doit rester au moins un administrateur actif."
        s.delete(admin)
        s.commit()
    return True, f"Administrateur {email} supprimé."


def est_admin(email: str) -> bool:
    """Vérifie si une adresse email correspond à un admin actif."""
    with session() as s:
        a = _admin_par_email(s, email)
        return a is not None and a.statut == "active"


def initialiser_admin_principal() -> tuple[bool, str]:
    """Crée l'admin par défaut si aucun n'existe.

    Identifiants initiaux : admin@nouvelair.com / Admin2024!
    À changer immédiatement après la première connexion.
    """
    with session() as s:
        nb = s.query(Administrateur).count()
        if nb > 0:
            return False, "Des administrateurs existent déjà."
    return creer_admin(
        email="admin@nouvelair.com",
        mot_de_passe="Admin2024!",
        nom="Admin MailGuard",
    )


# ─────────────────────────────────────────────────────────────────────────
# Gestion des domaines de confiance et frauduleux (persistance DB)
# ─────────────────────────────────────────────────────────────────────────

def _synchroniser_moteur():
    """Le moteur relit tout de suite les listes de domaines (au lieu d'attendre une minute)."""
    try:
        import mailguard_core as mg
        mg.synchroniser_listes(forcer=True)
    except Exception:
        pass


def _verifier_bert(domaine: str) -> str:
    """Vérifie avec CANINE (signal 1) que le domaine n'imite pas une marque protégée.
    Retourne 'oui' (légitime), 'non' (suspect/fraude), ou 'nc' (non disponible)."""
    try:
        import mailguard_core as mg
        if not mg._recharger_si_absent():
            return "nc"
        res = mg.analyser_domaine_bert(domaine)
        verdict = res.get("verdict", "")
        if "INDISPONIBLE" in verdict:
            return "nc"
        if "LÉGITIME" in verdict:
            return "oui"
        return "non"
    except Exception:
        return "nc"


# ── Domaines de confiance ─────────────────────────────────────────────────

def lister_domains_confiance(statut_filtre: str = "all") -> list[dict]:
    from services.database import DomainConfiance
    with session() as s:
        q = s.query(DomainConfiance)
        if statut_filtre != "all":
            q = q.filter(DomainConfiance.statut == statut_filtre)
        return [{
            "id": d.id, "domaine": d.domaine, "statut": d.statut,
            "commentaire": d.commentaire,
            "ajoute_le": d.ajoute_le.strftime("%Y-%m-%d") if d.ajoute_le else "",
            "valide_par_bert": d.valide_par_bert,
        } for d in q.order_by(DomainConfiance.ajoute_le.asc()).all()]


def ajouter_domain_confiance(domaine: str, commentaire: str = "") -> tuple[bool, str, str]:
    """Ajoute un domaine de confiance après vérification CANINE.
    Retourne (ok, message, bert_verdict)."""
    from services.database import DomainConfiance
    domaine = domaine.strip().lower()
    if not domaine:
        return False, "Le domaine est vide.", "nc"

    # Vérification CANINE (signal 1)
    bert = _verifier_bert(domaine)

    if bert == "non":
        return (False,
                f"⚠️ Le modèle CANINE signale que '{domaine}' imite une marque protégée "
                f"(typosquatting). Vérifiez l'orthographe avant d'ajouter.",
                bert)

    with session() as s:
        from services.database import DomainConfiance as DC
        existe = s.query(DC).filter_by(domaine=domaine).first()
        if existe:
            return False, f"Le domaine '{domaine}' existe déjà.", bert
        d = DC(domaine=domaine, commentaire=commentaire,
               statut="approved", valide_par_bert=bert)
        s.add(d)
        s.commit()
        _synchroniser_moteur()

    msg = (f"✅ Domaine '{domaine}' ajouté."
           if bert == "oui"
           else f"✅ Domaine '{domaine}' ajouté (BERT non disponible — vérification manuelle recommandée).")
    return True, msg, bert


def valider_domain_confiance(domaine_id: int) -> tuple[bool, str]:
    from services.database import DomainConfiance
    with session() as s:
        d = s.query(DomainConfiance).get(domaine_id)
        if not d:
            return False, "Domaine introuvable."
        d.statut = "approved"
        s.commit()
        _synchroniser_moteur()
    return True, "Domaine approuvé."


def supprimer_domain_confiance(domaine_id: int) -> tuple[bool, str]:
    from services.database import DomainConfiance
    with session() as s:
        d = s.query(DomainConfiance).get(domaine_id)
        if not d:
            return False, "Domaine introuvable."
        s.delete(d)
        s.commit()
        _synchroniser_moteur()
    return True, "Domaine supprimé."


# ── Domaines frauduleux ───────────────────────────────────────────────────

def lister_domains_frauduleux(statut_filtre: str = "all", recherche: str = "") -> list[dict]:
    from services.database import DomainFrauduleux
    with session() as s:
        q = s.query(DomainFrauduleux)
        if statut_filtre != "all":
            q = q.filter(DomainFrauduleux.statut == statut_filtre)
        if recherche:
            q = q.filter(DomainFrauduleux.domaine.ilike(f"%{recherche}%"))
        return [{
            "id": d.id, "domaine": d.domaine, "raison": d.raison,
            "score": d.score_estime, "commentaire": d.commentaire,
            "statut": d.statut,
            "ajoute_le": d.ajoute_le.strftime("%Y-%m-%d %H:%M") if d.ajoute_le else "",
        } for d in q.order_by(DomainFrauduleux.ajoute_le.desc()).all()]


def ajouter_domain_frauduleux(domaine: str, raison: str = "",
                               score: float = 0.8, commentaire: str = "") -> tuple[bool, str]:
    from services.database import DomainFrauduleux
    domaine = domaine.strip().lower()
    if not domaine:
        return False, "Le domaine est vide."
    with session() as s:
        from services.database import DomainFrauduleux as DF
        existe = s.query(DF).filter_by(domaine=domaine).first()
        if existe:
            return False, f"Le domaine '{domaine}' existe déjà dans la blacklist."
        d = DF(domaine=domaine, raison=raison, score_estime=score, commentaire=commentaire)
        s.add(d)
        s.commit()
        _synchroniser_moteur()
    return True, f"Domaine frauduleux '{domaine}' ajouté."


def supprimer_domain_frauduleux(domaine_id: int) -> tuple[bool, str]:
    from services.database import DomainFrauduleux
    with session() as s:
        d = s.query(DomainFrauduleux).get(domaine_id)
        if not d:
            return False, "Domaine introuvable."
        s.delete(d)
        s.commit()
        _synchroniser_moteur()
    return True, "Domaine supprimé."


def initialiser_listes_domaines():
    """Pré-charge whitelist et blacklist depuis l'email IT si la DB est vide."""
    from services.database import DomainConfiance, DomainFrauduleux

    WHITELIST = [
        ("nouvelair.com", "Domaine principal Nouvelair"),
        ("nouvelair.tn", "Domaine .tn Nouvelair"),
        ("mail.nouvelair.com", "Serveur mail Nouvelair"),
        ("nouvelair.com.tn", "Adresses internes .com.tn"),
        ("cohor.org", "Partenaire"),
        ("keyrus.com", "Partenaire IT"),
        ("trigodo.com", "Partenaire"),
        ("gts-poland.pl", "Partenaire GTS Poland"),
        ("anypli.com", "Partenaire"),
        ("asaviation.eu", "Partenaire aviation"),
        ("aas-switzerland.ch", "Partenaire Suisse"),
        ("2sauto.com.tn", "Partenaire TN"),
        ("fraport-slovenija.si", "Partenaire aéroport"),
        ("ppmdc.com.sa", "Partenaire SA"),
        ("id.lhsystems.aero", "Partenaire LH Systems"),
        ("perseusaviation.com", "Partenaire aviation"),
        ("biat.com.tn", "BIAT"),
        ("tunisie-catring.tn", "Tunisie Catering"),
    ]

    BLACKLIST = [
        ("nouevelair.com", "Typosquat Nouvelair", 0.95),
        ("nouevlair.com", "Typosquat Nouvelair", 0.95),
        ("nouvelair.co", "Typosquat Nouvelair", 0.95),
        ("nouvellair.com", "Typosquat Nouvelair", 0.95),
        ("nouvelairr.com", "Typosquat Nouvelair", 0.95),
        ("nouvelairl.com", "Typosquat Nouvelair", 0.95),
        ("nouve1air.com", "Typosquat (1 au lieu de l)", 0.97),
        ("nouvelaiir.com", "Typosquat Nouvelair", 0.95),
        ("nouveliar.com", "Typosquat Nouvelair", 0.95),
        ("nouelair.com", "Typosquat Nouvelair", 0.95),
        ("nouvelar.com", "Typosquat Nouvelair", 0.95),
        ("nouvelairc.com", "Typosquat Nouvelair", 0.95),
        ("nouvelair.cm", "Typosquat (cm au lieu de com)", 0.97),
        ("nouvelair.cn", "Typosquat (cn au lieu de com)", 0.97),
        ("nouvelair.io", "Typosquat Nouvelair", 0.90),
        ("aercaq.com", "Phishing confirmé", 0.90),
        ("alrbus.com", "Phishing confirmé", 0.90),
        ("dubalaerospace.com", "Phishing aéronautique", 0.85),
        ("dubaierospace.com", "Phishing aéronautique", 0.85),
        ("dubaiarospace.com", "Phishing aéronautique", 0.85),
        ("mohavkind.com", "Phishing confirmé", 0.85),
        ("chamwings.com", "Phishing aviation", 0.85),
        ("airpaz.com", "Phishing aviation", 0.80),
        ("jetmonde.com", "Phishing aviation", 0.80),
        ("saraejvo-airport-ba.com", "Typosquat Sarajevo Airport", 0.90),
        ("safirisalama.com", "Phishing confirmé", 0.85),
        ("imexqroup.com", "Phishing (group mal écrit)", 0.85),
        ("izonetelecom.com", "Spam/Phishing", 0.75),
        ("austom-nam.com", "Phishing", 0.80),
        ("monservice.email", "Phishing générique", 0.80),
        ("nucleus.com", "Phishing confirmé", 0.75),
        ("apollojets.com", "Phishing aviation", 0.80),
        ("invitations.mailinblack.com", "Spam marketing", 0.70),
        ("chiostrodelcarmine.com", "Phishing", 0.75),
        ("bentonrea.com", "Phishing", 0.75),
        ("tozya.com", "Spam/Phishing", 0.75),
        ("damanhur.it", "Phishing", 0.75),
        ("zugseil.com", "Phishing", 0.75),
        ("tourex.africa", "Phishing", 0.75),
        ("deped.gov.ph", "Phishing", 0.75),
        ("suitsforsuccessinc.org", "Phishing", 0.75),
        ("eyz.org.il", "Phishing", 0.75),
        ("banburypostiche.co.uk", "Phishing", 0.75),
        ("landschafftleben.at", "Phishing", 0.70),
        ("pcolle.com", "Phishing", 0.70),
        ("itea.ci", "Phishing", 0.70),
        ("player.rs", "Spam", 0.65),
        ("acmair.com", "Phishing aviation", 0.80),
    ]

    with session() as s:
        nb_wl = s.query(DomainConfiance).count()
        nb_bl = s.query(DomainFrauduleux).count()

        if nb_wl == 0:
            for domaine, commentaire in WHITELIST:
                s.add(DomainConfiance(domaine=domaine, commentaire=commentaire,
                                      statut="approved", valide_par_bert="oui"))
            s.commit()
            print(f"Whitelist initialisée: {len(WHITELIST)} domaines")

        if nb_bl == 0:
            for domaine, raison, score in BLACKLIST:
                s.add(DomainFrauduleux(domaine=domaine, raison=raison,
                                       score_estime=score, statut="active"))
            s.commit()
            print(f"Blacklist initialisée: {len(BLACKLIST)} domaines")

    return nb_wl == 0, nb_bl == 0


# ─────────────────────────────────────────────────────────────────────────
# Journal d'audit : chaque action d'administration réussie est enregistrée
# (table journal_audit). Les fonctions ci-dessus restent inchangées ; elles
# sont seulement enveloppées, pour ne rien oublier et ne rien dupliquer.
# ─────────────────────────────────────────────────────────────────────────

import functools as _functools


def _nom_domaine(modele, domaine_id):
    try:
        from services.database import DomainConfiance, DomainFrauduleux
        classe = DomainConfiance if modele == "confiance" else DomainFrauduleux
        with session() as s:
            d = s.get(classe, domaine_id)
            return d.domaine if d else str(domaine_id)
    except Exception:
        return str(domaine_id)


def _premier(*a, **k):
    return a[0] if a else next(iter(k.values()), "")


def _second(*a, **k):
    return a[1] if len(a) > 1 else (list(k.values())[1] if len(k) > 1 else "")


def _journalise(action, entite_type, entite=_premier, details=""):
    def decorer(fonction):
        @_functools.wraps(fonction)
        def enveloppe(*args, **kwargs):
            nom = entite(*args, **kwargs)                      # calculé AVANT (ex. domaine supprimé)
            resultat = fonction(*args, **kwargs)
            ok = resultat[0] if isinstance(resultat, tuple) else bool(resultat)
            if ok:
                from services.audit_service import journaliser
                texte = details(*args, **kwargs) if callable(details) else details
                act = action(*args, **kwargs) if callable(action) else action
                journaliser(act, entite_type, nom, texte)
            return resultat
        return enveloppe
    return decorer


activer_compte = _journalise("ACTIVATE_USER", "utilisateur", details="compte activé")(activer_compte)
suspendre_compte = _journalise("SUSPEND_USER", "utilisateur", details="compte suspendu")(suspendre_compte)
supprimer_compte_admin = _journalise("DELETE_USER", "utilisateur", details="compte supprimé")(supprimer_compte_admin)
creer_admin = _journalise("CREATE_ADMIN", "admin", details="administrateur créé")(creer_admin)
changer_statut_admin = _journalise(
    lambda *a, **k: "ACTIVATE_ADMIN" if (_second(*a, **k) or k.get("nouveau_statut")) == "active" else "SUSPEND_ADMIN",
    "admin", details=lambda *a, **k: f"nouveau statut : {_second(*a, **k) or k.get('nouveau_statut')}")(changer_statut_admin)
supprimer_admin = _journalise("DELETE_ADMIN", "admin", details="administrateur supprimé")(supprimer_admin)
ajouter_domain_confiance = _journalise(
    "DOMAIN_ADD", "domaine", entite=lambda *a, **k: str(_premier(*a, **k)).strip().lower(),
    details="ajouté à la liste blanche")(ajouter_domain_confiance)
valider_domain_confiance = _journalise(
    "DOMAIN_VALIDATE", "domaine", entite=lambda *a, **k: _nom_domaine("confiance", _premier(*a, **k)),
    details="liste blanche : domaine validé")(valider_domain_confiance)
supprimer_domain_confiance = _journalise(
    "DOMAIN_REMOVE", "domaine", entite=lambda *a, **k: _nom_domaine("confiance", _premier(*a, **k)),
    details="retiré de la liste blanche")(supprimer_domain_confiance)
ajouter_domain_frauduleux = _journalise(
    "DOMAIN_ADD", "domaine", entite=lambda *a, **k: str(_premier(*a, **k)).strip().lower(),
    details=lambda *a, **k: ("ajouté à la liste noire" + (f" ({_second(*a, **k) or k.get('raison')})"
                                                           if (_second(*a, **k) or k.get('raison')) else "")))(ajouter_domain_frauduleux)
supprimer_domain_frauduleux = _journalise(
    "DOMAIN_REMOVE", "domaine", entite=lambda *a, **k: _nom_domaine("frauduleux", _premier(*a, **k)),
    details="retiré de la liste noire")(supprimer_domain_frauduleux)


_connecter_sans_journal = connecter


@_functools.wraps(_connecter_sans_journal)
def connecter(email: str, mot_de_passe: str):
    ok, message, utilisateur = _connecter_sans_journal(email, mot_de_passe)
    from services.audit_service import journaliser
    role = (utilisateur or {}).get("role", "utilisateur") if ok else ""
    journaliser("LOGIN" if ok else "LOGIN_FAILED", "admin" if role == "admin" else "utilisateur",
                normaliser_email(email), "connexion réussie" if ok else message, acteur=normaliser_email(email))
    return ok, message, utilisateur
