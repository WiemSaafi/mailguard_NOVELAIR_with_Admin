"""
services/imap_service.py
==========================
Service IMAP pour Gmail : connexion, surveillance, déplacement de dossier.
Utilisé par la page Surveillance Gmail dans Streamlit.
"""

import os
import imaplib
import email
import time
import logging
from email.header import decode_header
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("imap_service")

IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993

DOSSIER_QUARANTAINE = "MailGuard/Quarantaine"
DOSSIER_SUSPECTS = "MailGuard/Suspects"


class ImapService:
    """Gère la connexion IMAP Gmail et les opérations sur les emails."""

    def __init__(self, address: str = None, password: str = None):
        # CORRECTIF 7 : "address or os.getenv(...)" retombait sur le .env quand on
        # passait une chaine vide, puisqu'une chaine vide est consideree fausse.
        # On distingue maintenant "non fourni" (None) de "fourni vide" ("").
        self.address = os.getenv("GMAIL_ADDRESS", "") if address is None else address
        self.password = os.getenv("GMAIL_APP_PASSWORD", "") if password is None else password
        self.imap = None
        self.connecte = False

    # ------------------------------------------------------------------
    # Connexion
    # ------------------------------------------------------------------
    def connecter(self) -> tuple[bool, str]:
        """Tente la connexion IMAP. Retourne (succès, message)."""
        if not self.address or not self.password:
            return False, "Identifiants manquants dans le fichier .env"
        try:
            self.imap = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
            self.imap.login(self.address, self.password)
            self.connecte = True
            return True, f"Connecté à {self.address}"
        except imaplib.IMAP4.error as e:
            self.connecte = False
            return False, f"Erreur IMAP : {e}"
        except Exception as e:
            self.connecte = False
            return False, f"Erreur connexion : {e}"

    def deconnecter(self):
        """Ferme proprement la connexion IMAP."""
        try:
            if self.imap:
                self.imap.logout()
        except Exception:
            pass
        finally:
            self.connecte = False
            self.imap = None

    def tester_connexion(self) -> tuple[bool, str]:
        """Test rapide de connexion (se déconnecte après)."""
        ok, msg = self.connecter()
        if ok:
            self.deconnecter()
        return ok, msg

    # ------------------------------------------------------------------
    # Surveillance
    # ------------------------------------------------------------------
    def get_uids_actuels(self, dossier: str = "INBOX") -> set:
        """Retourne l'ensemble des UIDs présents dans le dossier."""
        try:
            self.imap.select(dossier)
            _, data = self.imap.uid("search", None, "ALL")
            if data and data[0]:
                return set(data[0].split())
            return set()
        except Exception as e:
            log.warning(f"Erreur get_uids : {e}")
            return set()

    def fetch_email(self, uid: bytes) -> email.message.Message | None:
        """Récupère un email par UID."""
        try:
            _, msg_data = self.imap.uid("fetch", uid, "(RFC822)")
            if msg_data and msg_data[0]:
                return email.message_from_bytes(msg_data[0][1])
        except Exception as e:
            log.warning(f"Erreur fetch_email {uid} : {e}")
        return None

    def noop(self):
        """Garde la connexion active."""
        try:
            self.imap.noop()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Déplacement (quarantaine / suspects)
    # ------------------------------------------------------------------
    def creer_dossier_si_absent(self, dossier: str):
        """Crée le dossier IMAP s'il n'existe pas."""
        try:
            status, _ = self.imap.select(dossier)
            if status != "OK":
                self.imap.create(dossier)
                log.info(f"Dossier créé : {dossier}")
        except Exception:
            try:
                self.imap.create(dossier)
            except Exception as e:
                log.warning(f"Impossible de créer {dossier} : {e}")

    def deplacer_email(self, uid: bytes, dossier_destination: str) -> tuple[bool, str]:
        """
        Déplace un email vers un dossier Gmail.
        Retourne (succès, message).
        """
        try:
            # S'assurer que le dossier existe
            self.creer_dossier_si_absent(dossier_destination)

            # Copier vers le dossier destination
            result = self.imap.uid("copy", uid, dossier_destination)
            if result[0] != "OK":
                return False, f"Échec de la copie vers {dossier_destination}"

            # Marquer l'original pour suppression
            self.imap.uid("store", uid, "+FLAGS", "\\Deleted")

            # Supprimer définitivement
            self.imap.expunge()

            return True, f"Email déplacé vers {dossier_destination}"
        except Exception as e:
            return False, f"Erreur déplacement : {e}"

    def mettre_en_quarantaine(self, uid: bytes) -> tuple[bool, str]:
        return self.deplacer_email(uid, DOSSIER_QUARANTAINE)

    def deplacer_vers_suspects(self, uid: bytes) -> tuple[bool, str]:
        return self.deplacer_email(uid, DOSSIER_SUSPECTS)

    def appliquer_action(self, uid: bytes, categorie: str, action_config: str) -> str:
        """
        Applique l'action selon la catégorie et la config.
        Retourne la description de l'action appliquée.
        """
        if not uid:
            return "aucune (test manuel)"

        if categorie == "DANGEREUX":
            if action_config == "quarantaine":
                ok, msg = self.mettre_en_quarantaine(uid)
                return f"Quarantaine : {msg}"
            elif action_config == "suspects":
                ok, msg = self.deplacer_vers_suspects(uid)
                return f"Suspects : {msg}"
            elif action_config == "marquer":
                return "Marqué comme dangereux (sans déplacement)"
            else:
                return "Aucune action appliquée"

        elif categorie == "SUSPECT":
            if action_config in ("suspects", "quarantaine"):
                ok, msg = self.deplacer_vers_suspects(uid)
                return f"Suspects : {msg}"
            else:
                return "Conservé avec avertissement"

        else:  # LÉGITIME
            return "Conservé dans la boîte de réception"


# ------------------------------------------------------------------
# Helpers d'extraction
# ------------------------------------------------------------------

def decoder_texte(valeur) -> str:
    """Décode un en-tête email encodé."""
    if valeur is None:
        return ""
    morceaux = decode_header(valeur)
    texte = ""
    for contenu, encodage in morceaux:
        if isinstance(contenu, bytes):
            texte += contenu.decode(encodage or "utf-8", errors="ignore")
        else:
            texte += str(contenu)
    return texte


def extraire_domaine_expediteur(from_header: str) -> str:
    """Extrait le domaine depuis l'en-tête From."""
    from_header = decoder_texte(from_header)
    if "@" in from_header:
        adresse = from_header.split("<")[-1].split(">")[0]
        return adresse.split("@")[-1].strip().lower()
    return "inconnu"


def extraire_texte_brut(msg: email.message.Message) -> str:
    """Extrait le corps texte d'un email."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(errors="ignore")
                except Exception:
                    continue
        # Fallback HTML
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    from bs4 import BeautifulSoup
                    html = part.get_payload(decode=True).decode(errors="ignore")
                    return BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)
                except Exception:
                    pass
        return ""
    else:
        try:
            payload = msg.get_payload(decode=True)
            return payload.decode(errors="ignore") if payload else ""
        except Exception:
            return ""
