"""
services/mail_providers.py
===========================
Trois protocoles de relève, derrière une interface commune.

L'utilisateur choisit son protocole ; le reste de l'application ne voit qu'un
objet exposant toujours les mêmes méthodes. Ajouter un quatrième protocole ne
demanderait donc de toucher ni aux pages, ni au moteur de détection.

Ce qu'il faut savoir avant de choisir
-------------------------------------

IMAP
    Le protocole de référence pour ce projet. Les messages restent sur le
    serveur, les dossiers existent, et un message peut donc être déplacé en
    quarantaine. C'est le seul protocole où MailGuard peut réellement écarter
    un message de la boîte de réception.

POP3
    Conçu pour télécharger les messages puis les effacer du serveur. Il ne
    connaît pas la notion de dossier : **la mise en quarantaine est
    impossible**. MailGuard peut analyser et alerter, mais pas ranger. C'est
    une limite du protocole, pas de l'application, et aucun contournement
    n'existe.

Microsoft Graph
    L'API de Microsoft 365, à utiliser pour une boîte Outlook professionnelle.
    Elle gère les dossiers, donc la quarantaine fonctionne. En revanche elle
    exige une application enregistrée dans Azure Active Directory, avec un
    identifiant de locataire, un identifiant client et un secret. Sans ces
    trois éléments fournis par le service informatique, la connexion est
    impossible : Microsoft a supprimé l'authentification par simple mot de
    passe pour ce type d'accès.
"""

import email
import imaplib
import os
import poplib
from email.header import decode_header

import requests

DOSSIER_QUARANTAINE = "MailGuard/Quarantaine"
DOSSIER_SUSPECTS = "MailGuard/Suspects"

PROTOCOLES = {
    "imap": {
        "nom": "IMAP",
        "description": "Gmail, ou tout serveur classique. Déplacement des "
                       "messages possible.",
        "deplacement": True,
        "champs": ["adresse", "mot_de_passe", "serveur", "port"],
        "serveur_defaut": "imap.gmail.com",
        "port_defaut": 993,
    },
    "pop3": {
        "nom": "POP3",
        "description": "Ancien protocole de relève. Analyse et alerte "
                       "seulement : aucun déplacement possible.",
        "deplacement": False,
        "champs": ["adresse", "mot_de_passe", "serveur", "port"],
        "serveur_defaut": "pop.gmail.com",
        "port_defaut": 995,
    },
    "graph": {
        "nom": "Microsoft Graph",
        "description": "Boîte Outlook ou Microsoft 365. Déplacement possible, "
                       "mais demande une application enregistrée dans Azure.",
        "deplacement": True,
        "champs": ["adresse", "tenant_id", "client_id", "client_secret"],
        "serveur_defaut": "",
        "port_defaut": 0,
    },
}


# ═════════════════════════════════════════════════════════════════════════
# Interface commune
# ═════════════════════════════════════════════════════════════════════════

class FournisseurMail:
    """Contrat que respectent les trois implémentations."""

    protocole = ""
    supporte_deplacement = False

    def connecter(self) -> tuple[bool, str]:
        raise NotImplementedError

    def deconnecter(self):
        raise NotImplementedError

    def tester_connexion(self) -> tuple[bool, str]:
        ok, message = self.connecter()
        if ok:
            self.deconnecter()
        return ok, message

    def get_uids_actuels(self, dossier: str = "INBOX") -> set:
        raise NotImplementedError

    def fetch_email(self, uid):
        raise NotImplementedError

    def appliquer_action(self, uid, categorie: str, action_config: str) -> str:
        raise NotImplementedError

    def noop(self):
        """Maintient la connexion ouverte entre deux relevés."""
        return

    def dossier_spam(self):
        """Nom du dossier des indésirables, ou None si le protocole n'en a pas."""
        return None


def _libelle(categorie: str) -> str:
    """Nom affiché d'une catégorie (la clé interne DANGEREUX s'affiche « frauduleux »)."""
    return {"DANGEREUX": "frauduleux"}.get(categorie, (categorie or "").lower())


def decoder_texte(valeur) -> str:
    """Décode un en-tête encodé (base64, quoted-printable)."""
    if not valeur:
        return ""
    morceaux = []
    for contenu, encodage in decode_header(valeur):
        if isinstance(contenu, bytes):
            morceaux.append(contenu.decode(encodage or "utf-8", errors="replace"))
        else:
            morceaux.append(contenu)
    return "".join(morceaux)


# ═════════════════════════════════════════════════════════════════════════
# IMAP
# ═════════════════════════════════════════════════════════════════════════

class FournisseurImap(FournisseurMail):
    protocole = "imap"
    supporte_deplacement = True

    def __init__(self, adresse=None, mot_de_passe=None,
                 serveur="imap.gmail.com", port=993):
        self.adresse = os.getenv("GMAIL_ADDRESS", "") if adresse is None else adresse
        self.mot_de_passe = (os.getenv("GMAIL_APP_PASSWORD", "")
                             if mot_de_passe is None else mot_de_passe)
        self.serveur = serveur or "imap.gmail.com"
        self.port = int(port or 993)
        self.connexion = None

    def connecter(self):
        if not self.adresse or not self.mot_de_passe:
            return False, "Adresse ou mot de passe manquant."
        try:
            self.connexion = imaplib.IMAP4_SSL(self.serveur, self.port)
            self.connexion.login(self.adresse, self.mot_de_passe)
            return True, f"Connecté à {self.adresse} en IMAP."
        except imaplib.IMAP4.error as exc:
            return False, f"Connexion IMAP refusée : {exc}"
        except Exception as exc:
            return False, f"Serveur IMAP injoignable : {exc}"

    def deconnecter(self):
        try:
            if self.connexion:
                self.connexion.logout()
        except Exception:
            pass
        self.connexion = None

    def noop(self):
        try:
            if self.connexion:
                self.connexion.noop()
        except Exception:
            pass

    @staticmethod
    def _nom(dossier):
        """Les noms avec espace (« [Google Mail]/Spam ») doivent être entre guillemets."""
        return f'"{dossier}"' if " " in dossier and not dossier.startswith('"') else dossier

    def dossier_spam(self):
        """Cherche le dossier marqué \\Junk par le serveur (Gmail : [Gmail]/Spam)."""
        if getattr(self, "_spam", None):
            return self._spam
        self._spam = "[Gmail]/Spam"
        try:
            statut, lignes = self.connexion.list()
            for ligne in lignes or []:
                texte = ligne.decode(errors="replace") if isinstance(ligne, bytes) else str(ligne)
                if "\\Junk" in texte:
                    self._spam = texte.rsplit(' "/" ', 1)[-1].strip().strip('"')
                    break
        except Exception:
            pass
        return self._spam

    def get_uids_actuels(self, dossier="INBOX"):
        """UID IMAP (stables) et non numéros de séquence, qui changent dès qu'un
        message est déplacé : sans cela, un message pouvait être ignoré ou relu."""
        try:
            statut, _ = self.connexion.select(self._nom(dossier))
            if statut != "OK":
                return set()
            self._dossier_courant = dossier
            statut, donnees = self.connexion.uid("search", None, "ALL")
            if statut != "OK":
                return set()
            return set(donnees[0].split())
        except Exception:
            return set()

    def fetch_email(self, uid):
        """BODY.PEEK[] : lit le message sans le marquer comme lu."""
        try:
            statut, donnees = self.connexion.uid("fetch", uid, "(BODY.PEEK[])")
            if statut != "OK" or not donnees or not isinstance(donnees[0], tuple):
                return None
            return email.message_from_bytes(donnees[0][1])
        except Exception:
            return None

    def _assurer_dossier(self, dossier):
        try:
            self.connexion.create(dossier)
        except Exception:
            pass

    def appliquer_action(self, uid, categorie, action_config):
        if uid is None:
            return "aucune (test manuel)"
        if action_config == "rien" or categorie == "LÉGITIME":
            return "conservé dans son dossier"
        if action_config == "marquer":
            return f"signalé comme {_libelle(categorie)}, non déplacé"
        courant = getattr(self, "_dossier_courant", "INBOX")
        if courant != "INBOX" and courant == self.dossier_spam():
            # Déjà isolé par le serveur : on ne le déplace pas (et on ne l'efface jamais du Spam).
            return f"signalé comme {_libelle(categorie)}, laissé dans le dossier Spam"

        cible = (DOSSIER_QUARANTAINE
                 if categorie == "DANGEREUX" and action_config == "quarantaine"
                 else DOSSIER_SUSPECTS)
        try:
            self._assurer_dossier(cible)
            statut, _ = self.connexion.uid("copy", uid, cible)
            if statut != "OK":
                return "déplacement impossible (copie refusée)"
            self.connexion.uid("store", uid, "+FLAGS", "(\\Deleted)")
            self.connexion.expunge()
            return f"déplacé vers {cible}"
        except Exception as exc:
            return f"déplacement impossible ({exc})"


# ═════════════════════════════════════════════════════════════════════════
# POP3
# ═════════════════════════════════════════════════════════════════════════

class FournisseurPop3(FournisseurMail):
    """POP3 ne connaît pas les dossiers : aucune quarantaine n'est possible.

    Les identifiants renvoyés sont les UIDL du serveur, stables d'une session
    à l'autre, ce qui permet de reconnaître les messages déjà vus.
    """

    protocole = "pop3"
    supporte_deplacement = False

    def __init__(self, adresse="", mot_de_passe="",
                 serveur="pop.gmail.com", port=995):
        self.adresse = adresse
        self.mot_de_passe = mot_de_passe
        self.serveur = serveur or "pop.gmail.com"
        self.port = int(port or 995)
        self.connexion = None
        self._numeros = {}

    def connecter(self):
        if not self.adresse or not self.mot_de_passe:
            return False, "Adresse ou mot de passe manquant."
        try:
            self.connexion = poplib.POP3_SSL(self.serveur, self.port, timeout=20)
            self.connexion.user(self.adresse)
            self.connexion.pass_(self.mot_de_passe)
            return True, (f"Connecté à {self.adresse} en POP3. "
                          f"Attention : la mise en quarantaine est impossible "
                          f"avec ce protocole.")
        except poplib.error_proto as exc:
            return False, f"Connexion POP3 refusée : {exc}"
        except Exception as exc:
            return False, f"Serveur POP3 injoignable : {exc}"

    def deconnecter(self):
        try:
            if self.connexion:
                self.connexion.quit()
        except Exception:
            pass
        self.connexion = None

    def get_uids_actuels(self, dossier="INBOX"):
        # POP3 n'a qu'une seule boîte : le paramètre dossier est ignoré.
        try:
            reponse, lignes, _ = self.connexion.uidl()
            self._numeros = {}
            identifiants = set()
            for ligne in lignes:
                numero, identifiant = ligne.decode(errors="replace").split(maxsplit=1)
                self._numeros[identifiant] = int(numero)
                identifiants.add(identifiant.encode())
            return identifiants
        except Exception:
            return set()

    def fetch_email(self, uid):
        try:
            identifiant = uid.decode() if isinstance(uid, bytes) else str(uid)
            numero = self._numeros.get(identifiant)
            if numero is None:
                return None
            reponse, lignes, _ = self.connexion.retr(numero)
            return email.message_from_bytes(b"\n".join(lignes))
        except Exception:
            return None

    def appliquer_action(self, uid, categorie, action_config):
        if uid is None:
            return "aucune (test manuel)"
        if categorie == "LÉGITIME":
            return "conservé dans la boîte de réception"
        # Volontairement, aucune suppression n'est proposée : effacer un message
        # sur un serveur POP3 est irréversible, contrairement à un déplacement.
        return f"signalé comme {_libelle(categorie)} (POP3 : déplacement impossible)"


# ═════════════════════════════════════════════════════════════════════════
# Microsoft Graph
# ═════════════════════════════════════════════════════════════════════════

class FournisseurGraph(FournisseurMail):
    """Boîte Microsoft 365, via l'API Graph.

    L'authentification utilise le flux « client credentials » : une application
    enregistrée dans Azure Active Directory, à laquelle un administrateur a
    accordé la permission applicative Mail.ReadWrite. C'est le seul mode qui
    fonctionne sans interaction humaine, donc le seul compatible avec une
    surveillance automatique.
    """

    protocole = "graph"
    supporte_deplacement = True
    BASE = "https://graph.microsoft.com/v1.0"

    def __init__(self, adresse="", tenant_id="", client_id="", client_secret=""):
        self.adresse = adresse
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.jeton = None
        self._dossiers = {}

    def _entetes(self):
        return {"Authorization": f"Bearer {self.jeton}",
                "Content-Type": "application/json"}

    def connecter(self):
        manquants = [nom for nom, valeur in (
            ("adresse", self.adresse), ("identifiant de locataire", self.tenant_id),
            ("identifiant client", self.client_id),
            ("secret client", self.client_secret)) if not valeur]
        if manquants:
            return False, "Éléments manquants : " + ", ".join(manquants) + "."

        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        try:
            reponse = requests.post(url, timeout=20, data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            })
            donnees = reponse.json()
        except Exception as exc:
            return False, f"Serveur d'authentification injoignable : {exc}"

        if reponse.status_code != 200 or "access_token" not in donnees:
            description = donnees.get("error_description", donnees.get("error", ""))
            return False, f"Jeton refusé par Azure : {str(description)[:200]}"

        self.jeton = donnees["access_token"]

        try:
            controle = requests.get(f"{self.BASE}/users/{self.adresse}/mailFolders/inbox",
                                    headers=self._entetes(), timeout=20)
        except Exception as exc:
            return False, f"Graph injoignable : {exc}"

        if controle.status_code == 403:
            return False, ("Jeton valide mais permission refusée. "
                           "Un administrateur doit accorder Mail.ReadWrite "
                           "à l'application.")
        if controle.status_code == 404:
            return False, f"Boîte introuvable pour {self.adresse}."
        if controle.status_code != 200:
            return False, f"Graph a répondu {controle.status_code}."

        return True, f"Connecté à {self.adresse} via Microsoft Graph."

    def deconnecter(self):
        self.jeton = None

    def dossier_spam(self):
        return "junkemail"      # nom réservé de Microsoft Graph pour le courrier indésirable

    def get_uids_actuels(self, dossier="INBOX"):
        cible = "inbox" if dossier.upper() == "INBOX" else dossier
        try:
            reponse = requests.get(
                f"{self.BASE}/users/{self.adresse}/mailFolders/{cible}/messages",
                headers=self._entetes(), timeout=25,
                params={"$select": "id", "$top": 100,
                        "$orderby": "receivedDateTime desc"},
            )
            if reponse.status_code != 200:
                return set()
            return {m["id"].encode() for m in reponse.json().get("value", [])}
        except Exception:
            return set()

    def fetch_email(self, uid):
        """Récupère le message au format MIME, pour que le reste du code le
        traite exactement comme un message IMAP."""
        identifiant = uid.decode() if isinstance(uid, bytes) else str(uid)
        try:
            reponse = requests.get(
                f"{self.BASE}/users/{self.adresse}/messages/{identifiant}/$value",
                headers={"Authorization": f"Bearer {self.jeton}"}, timeout=25)
            if reponse.status_code != 200:
                return None
            return email.message_from_bytes(reponse.content)
        except Exception:
            return None

    def _id_dossier(self, chemin):
        """Crée si besoin l'arborescence MailGuard/... et renvoie son id."""
        if chemin in self._dossiers:
            return self._dossiers[chemin]

        parent = "msgfolderroot"
        for segment in chemin.split("/"):
            url = f"{self.BASE}/users/{self.adresse}/mailFolders/{parent}/childFolders"
            trouve = None
            reponse = requests.get(url, headers=self._entetes(), timeout=25,
                                   params={"$select": "id,displayName", "$top": 100})
            if reponse.status_code == 200:
                for dossier in reponse.json().get("value", []):
                    if dossier["displayName"].lower() == segment.lower():
                        trouve = dossier["id"]
                        break
            if trouve is None:
                creation = requests.post(url, headers=self._entetes(), timeout=25,
                                         json={"displayName": segment})
                if creation.status_code not in (200, 201):
                    raise RuntimeError(f"création du dossier {segment} refusée")
                trouve = creation.json()["id"]
            parent = trouve

        self._dossiers[chemin] = parent
        return parent

    def appliquer_action(self, uid, categorie, action_config):
        if uid is None:
            return "aucune (test manuel)"
        if action_config == "rien" or categorie == "LÉGITIME":
            return "conservé dans la boîte de réception"
        if action_config == "marquer":
            return f"signalé comme {_libelle(categorie)}, non déplacé"

        cible = (DOSSIER_QUARANTAINE
                 if categorie == "DANGEREUX" and action_config == "quarantaine"
                 else DOSSIER_SUSPECTS)
        identifiant = uid.decode() if isinstance(uid, bytes) else str(uid)
        try:
            destination = self._id_dossier(cible)
            reponse = requests.post(
                f"{self.BASE}/users/{self.adresse}/messages/{identifiant}/move",
                headers=self._entetes(), timeout=25,
                json={"destinationId": destination})
            if reponse.status_code in (200, 201):
                return f"déplacé vers {cible}"
            return f"déplacement refusé par Graph ({reponse.status_code})"
        except Exception as exc:
            return f"déplacement impossible ({exc})"


# ═════════════════════════════════════════════════════════════════════════
# Fabrique
# ═════════════════════════════════════════════════════════════════════════

def creer_fournisseur(*args, **identifiants) -> FournisseurMail:
    """Renvoie l'implémentation correspondant au protocole choisi.

    Le protocole peut être donné en premier argument, ou figurer dans le
    dictionnaire d'identifiants. Les deux appels suivants sont équivalents,
    ce qui permet de passer directement le résultat de lire_messagerie() :

        creer_fournisseur("imap", adresse=..., mot_de_passe=...)
        creer_fournisseur(**auth.lire_messagerie(email))
    """
    # Signature volontairement souple : Python leve une erreur si un argument
    # nomme est donne deux fois, ce qui arrivait en ecrivant
    # creer_fournisseur(reglages["protocole"], **reglages). On accepte donc le
    # protocole en position, dans le dictionnaire, ou les deux.
    identifiants = dict(identifiants)
    depuis_dict = identifiants.pop("protocole", None)
    protocole = (args[0] if args else depuis_dict) or depuis_dict or "imap"
    protocole = str(protocole).lower()

    if protocole == "pop3":
        return FournisseurPop3(
            adresse=identifiants.get("adresse", ""),
            mot_de_passe=identifiants.get("mot_de_passe", ""),
            serveur=identifiants.get("serveur") or PROTOCOLES["pop3"]["serveur_defaut"],
            port=identifiants.get("port") or PROTOCOLES["pop3"]["port_defaut"],
        )

    if protocole == "graph":
        return FournisseurGraph(
            adresse=identifiants.get("adresse", ""),
            tenant_id=identifiants.get("tenant_id", ""),
            client_id=identifiants.get("client_id", ""),
            client_secret=identifiants.get("client_secret", ""),
        )

    return FournisseurImap(
        adresse=identifiants.get("adresse", ""),
        mot_de_passe=identifiants.get("mot_de_passe", ""),
        serveur=identifiants.get("serveur") or PROTOCOLES["imap"]["serveur_defaut"],
        port=identifiants.get("port") or PROTOCOLES["imap"]["port_defaut"],
    )
