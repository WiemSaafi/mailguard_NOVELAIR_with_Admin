"""
gmail_watcher.py
=================
Surveille ta boîte Gmail EN DIRECT (via IMAP) et fait analyser chaque
nouvel email par MailGuard dès sa réception.

⚠️ Tes identifiants restent 100% locaux : ils sont lus depuis un fichier
   ".env" sur TA machine, jamais envoyés ailleurs.

Lancement :
    1. Copie ".env.example" en ".env" et remplis-le avec tes identifiants
    2. pip install -r requirements.txt
    3. python gmail_watcher.py

Ce script écrit chaque résultat dans "historique_analyses.json" —
c'est ce fichier que le dashboard Streamlit (app_dashboard.py) lit et
affiche en direct.
"""

import os
import json
import time
import email
import imaplib
import logging
from datetime import datetime
from email.header import decode_header

from dotenv import load_dotenv

import mailguard_core as mg

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("gmail_watcher")

load_dotenv()

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
GMAIL_FOLDER = os.getenv("GMAIL_FOLDER", "INBOX")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "5"))

HISTORIQUE_PATH = os.path.join(mg.BASE_DIR, "historique_analyses.json")
IMAP_SERVER = "imap.gmail.com"


def _decoder_texte(valeur):
    if valeur is None:
        return ""
    morceaux = decode_header(valeur)
    texte = ""
    for contenu, encodage in morceaux:
        if isinstance(contenu, bytes):
            texte += contenu.decode(encodage or "utf-8", errors="ignore")
        else:
            texte += contenu
    return texte


def _extraire_domaine_expediteur(from_header):
    from_header = _decoder_texte(from_header)
    if "@" in from_header:
        adresse = from_header.split("<")[-1].split(">")[0]
        return adresse.split("@")[-1].strip().lower()
    return "inconnu"


def _extraire_texte_brut(msg):
    """Récupère le corps texte (fallback : dérivé du HTML)."""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(errors="ignore")
                except Exception:
                    continue
        # fallback : extraire le texte depuis le HTML
        html = mg.extraire_corps_html(msg)
        if html:
            from bs4 import BeautifulSoup
            return BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)
        return ""
    else:
        try:
            payload = msg.get_payload(decode=True)
            return payload.decode(errors="ignore") if payload else ""
        except Exception:
            return ""


def _charger_historique():
    if os.path.exists(HISTORIQUE_PATH):
        try:
            with open(HISTORIQUE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _sauvegarder_historique(historique):
    with open(HISTORIQUE_PATH, "w", encoding="utf-8") as f:
        json.dump(historique, f, indent=2, ensure_ascii=False)


def analyser_et_enregistrer(msg, uid):
    domaine = _extraire_domaine_expediteur(msg.get("From"))
    sujet = _decoder_texte(msg.get("Subject"))
    texte = _extraire_texte_brut(msg)
    html = mg.extraire_corps_html(msg)
    liens = mg.extraire_liens(html) if html else []
    auth_header = msg.get("Authentication-Results", "")

    log.info(f"📩 Nouvel email — de {domaine} — sujet : {sujet[:60]}")
    log.info("   ↳ Analyse MailGuard en cours (5 signaux + fusion)...")

    t0 = time.time()
    resultat = mg.analyser_email_complet(
        domaine_expediteur=domaine, texte_email=texte, liens=liens, auth_header=auth_header,
        message=msg, sujet=sujet,     # le message complet : tous les en-têtes sont lus
    )
    duree_ms = round((time.time() - t0) * 1000, 1)

    log.info(f"   ↳ Verdict : {resultat['niveau']} (score={resultat['score_final']}, "
             f"étape={resultat.get('etape_decision', '')}, {duree_ms} ms)")

    entree = {
        "uid": uid,
        "timestamp": datetime.now().isoformat(),
        "domaine_expediteur": domaine,
        "sujet": sujet,
        "texte_apercu": texte[:300],
        "nb_liens": len(liens),
        "duree_analyse_ms": duree_ms,
        **resultat,
    }

    historique = _charger_historique()
    historique.append(entree)
    _sauvegarder_historique(historique)
    return entree


def boucle_surveillance():
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        raise SystemExit(
            "❌ GMAIL_ADDRESS / GMAIL_APP_PASSWORD manquants.\n"
            "   Copie '.env.example' en '.env' et remplis-le avec tes identifiants."
        )

    log.info(f"🔌 Connexion IMAP à {GMAIL_ADDRESS} ...")
    imap = imaplib.IMAP4_SSL(IMAP_SERVER)
    imap.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
    imap.select(GMAIL_FOLDER)

    # UID de départ : on ne traite que les emails reçus APRÈS le lancement du script
    _, data = imap.uid("search", None, "ALL")
    uids_connus = set(data[0].split())
    log.info(f"✅ Connecté. {len(uids_connus)} emails déjà présents (ignorés). "
             f"Surveillance des nouveaux emails toutes les {POLL_INTERVAL}s...")

    while True:
        try:
            imap.noop()  # garde la connexion active
            _, data = imap.uid("search", None, "ALL")
            uids_actuels = set(data[0].split())
            nouveaux = sorted(uids_actuels - uids_connus, key=lambda x: int(x))

            for uid in nouveaux:
                _, msg_data = imap.uid("fetch", uid, "(RFC822)")
                if not msg_data or msg_data[0] is None:
                    continue
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                analyser_et_enregistrer(msg, uid.decode())
                uids_connus.add(uid)

            time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            log.info("👋 Arrêt demandé. Fermeture de la connexion IMAP.")
            break
        except Exception as e:
            log.warning(f"⚠️ Erreur pendant la surveillance : {e} — nouvelle tentative dans {POLL_INTERVAL}s")
            time.sleep(POLL_INTERVAL)

    imap.logout()


if __name__ == "__main__":
    boucle_surveillance()
