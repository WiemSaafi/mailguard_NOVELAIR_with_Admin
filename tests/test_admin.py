"""
tests/test_admin.py — banc d'essai complet de l'espace ADMINISTRATION.

Vérifie :
  - Le rendu sans exception des 13 pages d'administration Streamlit.
  - La gestion des utilisateurs (activation, suspension, réactivation).
  - La gestion des administrateurs (création, suspension, suppression).
  - La gestion des listes de domaines (whitelist CANINE, blacklist dynamique).
  - Les indicateurs du Security Center.
  - La qualification humaine des détections (Review Detections, faux positifs).
  - Le cycle de vie des alertes de sécurité (vue, résolue, rouverte).
  - La calibration manuelle et la réinitialisation des seuils.
  - La détection de campagnes d'attaques groupées.
  - La génération de rapports périodiques.
  - La traçabilité exhaustive dans le journal d'audit (journal_audit).

Base de données : utilise EXCLUSIVEMENT une base SQLite temporaire jetable
définie par MAILGUARD_DATABASE_URL dans %TEMP%. La vraie base mailguard.db
n'est jamais touchée.
"""

import glob
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime

# ── 1. Configuration de l'environnement et base jetable ────────────────────
ICI = os.path.dirname(os.path.abspath(__file__))
PROJET = os.environ.get("MAILGUARD_DIR", os.path.dirname(ICI))
sys.path.insert(0, ICI)
sys.path.insert(0, PROJET)
os.chdir(PROJET)

temp_dir = os.environ.get("TEMP", tempfile.gettempdir())
db_jetable_fichier = os.path.join(temp_dir, "mailguard_test_admin.db")
if os.path.exists(db_jetable_fichier):
    try:
        os.remove(db_jetable_fichier)
    except Exception:
        pass

URL_BASE_JETABLE = f"sqlite:///{db_jetable_fichier.replace(os.sep, '/')}"
os.environ["MAILGUARD_DATABASE_URL"] = URL_BASE_JETABLE
os.environ["MAILGUARD_INTERNET"] = "0"

# Sauvegarde préventive de config_mailguard.json
config_path = os.path.join(PROJET, "config_mailguard.json")
config_backup = config_path + ".bak_test_admin"
if os.path.exists(config_path):
    shutil.copy2(config_path, config_backup)

import stubs  # noqa: F401,E402
import mailguard_core as mg  # noqa: E402
from services import auth_service as auth  # noqa: E402
from services import history_service  # noqa: E402
from services.database import (  # noqa: E402
    Administrateur, Analyse, DomainConfiance, DomainFrauduleux,
    EtatAlerte, JournalAudit, QualificationAnalyse, Utilisateur,
    reinitialiser_moteur, session,
)
from streamlit.testing.v1 import AppTest  # noqa: E402

# Initialisation du moteur sur la base temporaire
reinitialiser_moteur(URL_BASE_JETABLE)

RESULTATS = []


def verifier(titre: str, condition: bool, detail: str = ""):
    ok = bool(condition)
    RESULTATS.append((titre, ok, detail))
    icone = "\033[32m✔\033[0m" if ok else "\033[31m✘\033[0m"
    msg = f"  {icone} {titre}"
    if detail:
        msg += f"   \033[90m{detail}\033[0m"
    print(msg)
    return ok


def main():
    print("=" * 80)
    print("Banc d'essai Administration MailGuard (AppTest + Base Jetable)")
    print(f"Base temporaire : {URL_BASE_JETABLE}")
    print("=" * 80)

    # ── Étape 1 : Préparation des données ──────────────────────────────────
    print("\n\033[1;36m━━━ 1. Préparation des données de test ━━━\033[0m")
    EMAIL_ADMIN = "admin.test@nouvelair.com"
    MDP_ADMIN = "AdminTest1234"
    auth.creer_admin(EMAIL_ADMIN, MDP_ADMIN, "Admin Test")
    ok_conn_admin, msg_conn_admin, ADMIN_USER = auth.connecter(EMAIL_ADMIN, MDP_ADMIN)
    verifier("Création et connexion de l'administrateur principal",
             ok_conn_admin and ADMIN_USER.get("role") == "admin",
             f"{EMAIL_ADMIN} ({ADMIN_USER.get('role')})")

    # Inscrire 2 utilisateurs (statut initial 'pending')
    USER1 = "user1.test@nouvelair.com"
    USER2 = "user2.test@nouvelair.com"
    auth.inscrire(USER1, "Motdepasse1", "Utilisateur Un")
    auth.inscrire(USER2, "Motdepasse2", "Utilisateur Deux")
    with session() as s:
        nb_pending = s.query(Utilisateur).filter_by(statut="pending").count()
    verifier("Inscription de 2 utilisateurs en attente", nb_pending == 2, f"{nb_pending} en attente")

    # Initialisation des listes de domaines
    auth.initialiser_listes_domaines()
    with session() as s:
        nb_wl = s.query(DomainConfiance).count()
        nb_bl = s.query(DomainFrauduleux).count()
    verifier("Initialisation listes de domaines", nb_wl > 0 and nb_bl > 0,
             f"{nb_wl} confiance, {nb_bl} frauduleux")

    # Enregistrement de 3 analyses : Frauduleuse, Suspecte, Légitime
    # 1) Frauduleuse : nouvelair-verification.com (CANINE élevé) + auth en échec
    hdr_fraude = (
        "mx.nouvelair.com; spf=fail smtp.mailfrom=nouvelair-verification.com; "
        "dkim=fail header.d=nouvelair-verification.com; dmarc=fail header.from=nouvelair-verification.com"
    )
    r_f = mg.analyser_email_complet(
        "service@nouvelair-verification.com",
        "Votre compte a été compromis. Veuillez cliquer ici pour vérifier.",
        [],
        hdr_fraude,
        sujet="Alerte urgente sécurité",
    )
    e_f = history_service.ajouter_entree(
        domaine_expediteur="nouvelair-verification.com",
        sujet="Alerte urgente sécurité",
        texte_apercu="Votre compte a été compromis...",
        nb_liens=0,
        resultat=r_f,
        duree_ms=120.0,
        action_appliquee="quarantaine",
        source="manuel",
        identifiant=ADMIN_USER["identifiant"],
    )

    # 2) Suspecte : nouvelair.com authentifié + lien piégé http://nouvelalr.com/update
    hdr_ok = (
        "mx.nouvelair.com; spf=pass smtp.mailfrom=nouvelair.com; "
        "dkim=pass header.d=nouvelair.com; dmarc=pass header.from=nouvelair.com"
    )
    r_s = mg.analyser_email_complet(
        "info@nouvelair.com",
        "Bonjour, merci de mettre à jour vos coordonnées.",
        [{"texte_affiche": "Mise à jour", "url_reelle": "http://nouvelalr.com/update"}],
        hdr_ok,
        sujet="Mise à jour coordonnées",
    )
    e_s = history_service.ajouter_entree(
        domaine_expediteur="nouvelair.com",
        sujet="Mise à jour coordonnées",
        texte_apercu="Bonjour, merci de mettre à jour...",
        nb_liens=1,
        resultat=r_s,
        duree_ms=140.0,
        action_appliquee="aucune",
        source="manuel",
        identifiant=ADMIN_USER["identifiant"],
    )

    # 3) Légitime : nouvelair.com authentifié, texte normal
    r_l = mg.analyser_email_complet(
        "info@nouvelair.com",
        "Bonjour, voici votre confirmation de réservation. Bon voyage avec Nouvelair.",
        [{"texte_affiche": "Site Nouvelair", "url_reelle": "https://www.nouvelair.com/promo"}],
        hdr_ok,
        sujet="Confirmation réservation",
    )
    e_l = history_service.ajouter_entree(
        domaine_expediteur="nouvelair.com",
        sujet="Confirmation réservation",
        texte_apercu="Bonjour, voici votre confirmation...",
        nb_liens=1,
        resultat=r_l,
        duree_ms=50.0,
        action_appliquee="aucune",
        source="manuel",
        identifiant=ADMIN_USER["identifiant"],
    )

    verifier("Enregistrement des 3 analyses de référence",
             e_f["categorie"] == "DANGEREUX" and e_s["categorie"] == "SUSPECT" and e_l["categorie"] == "LÉGITIME",
             f"fraude={e_f['categorie']}, suspect={e_s['categorie']}, légitime={e_l['categorie']}")

    # ── Étape 2a : Rendu sans exception de toutes les pages admin ───────────
    print("\n\033[1;36m━━━ 2a. Rendu des pages d'administration ━━━\033[0m")
    PAGES_ADMIN = sorted(
        os.path.relpath(f, PROJET) for f in glob.glob(os.path.join(PROJET, "pages", "*ADMIN*.py"))
    )
    for p in PAGES_ADMIN:
        app = AppTest.from_file(os.path.join(PROJET, p), default_timeout=60)
        app.session_state["utilisateur"] = ADMIN_USER
        app.session_state["seuil_suspect"] = 0.825
        app.session_state["seuil_dangereux"] = 0.928
        app.run()
        errs = list(app.exception)
        verifier(f"Affichage sans exception : {os.path.basename(p)}",
                 len(errs) == 0,
                 str(errs[0].value) if errs else "OK")

    # ── Étape 2b : Utilisateurs / Security Center ───────────────────────────
    print("\n\033[1;36m━━━ 2b. Utilisateurs : activation, suspension, réactivation ━━━\033[0m")
    # Activer USER1
    auth.activer_compte(USER1)
    with session() as s:
        u1 = s.query(Utilisateur).filter_by(email=USER1).first()
        statut_u1 = u1.statut if u1 else None
    verifier("Activer compte en attente → statut 'active' en base", statut_u1 == "active", f"statut={statut_u1}")

    # Suspendre USER1
    auth.suspendre_compte(USER1)
    with session() as s:
        u1 = s.query(Utilisateur).filter_by(email=USER1).first()
        statut_u1_sus = u1.statut if u1 else None
    verifier("Suspendre compte actif → statut 'suspended' en base", statut_u1_sus == "suspended", f"statut={statut_u1_sus}")

    # Tester la connexion du compte suspendu (attendu : connexion refusée)
    ok_conn_sus, msg_conn_sus, _ = auth.connecter(USER1, "Motdepasse1")
    verifier("Connexion utilisateur suspendu : connexion refusée",
             not ok_conn_sus,
             f"obtenu: ok={ok_conn_sus}, msg='{msg_conn_sus}'")

    # Réactiver USER1
    auth.activer_compte(USER1)
    ok_conn_react, msg_conn_react, _ = auth.connecter(USER1, "Motdepasse1")
    verifier("Réactiver compte → connexion acceptée",
             ok_conn_react,
             f"obtenu: ok={ok_conn_react}, msg='{msg_conn_react}'")

    # ── Étape 2c : Administrateurs ──────────────────────────────────────────
    print("\n\033[1;36m━━━ 2c. Administrateurs : cycle de vie d'un second admin ━━━\033[0m")
    ADMIN2 = "admin2.test@nouvelair.com"
    ok_c_a2, msg_c_a2 = auth.creer_admin(ADMIN2, "AdminDeux1234", "Admin Deux")
    verifier("Création d'un second administrateur", ok_c_a2, msg_c_a2)

    ok_s_a2, msg_s_a2 = auth.changer_statut_admin(ADMIN2, "suspended")
    with session() as s:
        a2 = s.query(Administrateur).filter_by(email=ADMIN2).first()
        statut_a2 = a2.statut if a2 else None
    verifier("Suspension du second administrateur", ok_s_a2 and statut_a2 == "suspended", f"statut={statut_a2}")

    ok_del_a2, msg_del_a2 = auth.supprimer_admin(ADMIN2, EMAIL_ADMIN)
    with session() as s:
        a2_post = s.query(Administrateur).filter_by(email=ADMIN2).first()
    verifier("Suppression du second administrateur", ok_del_a2 and a2_post is None, msg_del_a2)

    # ── Étape 2d : Fraudulent Domains ───────────────────────────────────────
    print("\n\033[1;36m━━━ 2d. Fraudulent Domains : ajout et relecture dynamique ━━━\033[0m")
    DOM_ARNAQUE = "test-arnaque-exemple.com"
    ok_add_fd, _ = auth.ajouter_domain_frauduleux(DOM_ARNAQUE, "Campagne test phishing", 0.95)
    r_test_fd = mg.analyser_email_complet(f"contact@{DOM_ARNAQUE}", "Vérifiez votre compte", [], "")
    verifier("Ajout domaine frauduleux → classé FRAUDULEUX étape '0. liste noire'",
             ok_add_fd and r_test_fd.get("categorie") == "FRAUDULEUX" and r_test_fd.get("etape_decision") == "0. liste noire",
             f"cat={r_test_fd.get('categorie')}, etape='{r_test_fd.get('etape_decision')}'")

    with session() as s:
        d_fd = s.query(DomainFrauduleux).filter_by(domaine=DOM_ARNAQUE).first()
        d_fd_id = d_fd.id if d_fd else None
    ok_del_fd, _ = auth.supprimer_domain_frauduleux(d_fd_id)
    r_test_fd_post = mg.analyser_email_complet(f"contact@{DOM_ARNAQUE}", "Vérifiez votre compte", [], "")
    verifier("Suppression domaine frauduleux → ce n'est plus '0. liste noire'",
             ok_del_fd and r_test_fd_post.get("etape_decision") != "0. liste noire",
             f"etape='{r_test_fd_post.get('etape_decision')}'")

    # ── Étape 2e : Trusted Domains ──────────────────────────────────────────
    print("\n\033[1;36m━━━ 2e. Trusted Domains : validation CANINE (signal 1) ━━━\033[0m")
    ok_td_imite, _, bert_imite = auth.ajouter_domain_confiance("nouvelairr.com", "Tentative d'ajout typosquat")
    verifier("Ajout nouvelairr.com en liste blanche REFUSÉ par CANINE",
             (not ok_td_imite) and bert_imite == "non",
             f"ok={ok_td_imite}, bert='{bert_imite}'")

    ok_td_vrai, _, bert_vrai = auth.ajouter_domain_confiance("partenaire-exemple.tn", "Vrai partenaire légitime")
    verifier("Ajout partenaire-exemple.tn en liste blanche ACCEPTÉ",
             ok_td_vrai and bert_vrai == "oui",
             f"ok={ok_td_vrai}, bert='{bert_vrai}'")

    # ── Étape 2f : Security Center ──────────────────────────────────────────
    print("\n\033[1;36m━━━ 2f. Security Center : compteurs KPIs ━━━\033[0m")
    app_sc = AppTest.from_file(os.path.join(PROJET, "pages/07_ADMIN_Security_Center.py"), default_timeout=60)
    app_sc.session_state["utilisateur"] = ADMIN_USER
    app_sc.run()
    metrics_sc = {m.label: m.value for m in app_sc.metric}
    val_fraud = metrics_sc.get("Frauduleux")
    val_trusted = metrics_sc.get("Domaines de Confiance")
    val_fraud_dom = metrics_sc.get("Domaines Frauduleux")
    verifier("Security Center : compteur 'Frauduleux' vaut 1 (et pas 0)",
             val_fraud == "1",
             f"Frauduleux = {val_fraud}")
    verifier("Security Center : 'Domaines de Confiance' et 'Domaines Frauduleux' non nuls",
             val_trusted not in (None, "0") and val_fraud_dom not in (None, "0"),
             f"Confiance={val_trusted}, Frauduleux={val_fraud_dom}")

    # ── Étape 2g : Review Detections ────────────────────────────────────────
    print("\n\033[1;36m━━━ 2g. Review Detections : qualification et détection faux positifs ━━━\033[0m")
    app_rd = AppTest.from_file(os.path.join(PROJET, "pages/12_ADMIN_Review_Detections.py"), default_timeout=60)
    app_rd.session_state["utilisateur"] = ADMIN_USER
    app_rd.run()
    # Qualification de l'analyse légitime (ID e_l['id']) en "LÉGITIME"
    btn_q_l = [b for b in app_rd.button if b.key == f"q_LÉGITIME_{e_l['id']}"]
    if btn_q_l:
        btn_q_l[0].click().run()

    # Qualification de l'analyse frauduleuse (ID e_f['id']) en "LÉGITIME" (désaccord/faux positif)
    app_rd_step2 = AppTest.from_file(os.path.join(PROJET, "pages/12_ADMIN_Review_Detections.py"), default_timeout=60)
    app_rd_step2.session_state["utilisateur"] = ADMIN_USER
    app_rd_step2.run()
    btn_q_f = [b for b in app_rd_step2.button if b.key == f"q_LÉGITIME_{e_f['id']}"]
    if btn_q_f:
        btn_q_f[0].click().run()

    # Rechargement nouvel AppTest pour vérifier persistance
    app_rd_final = AppTest.from_file(os.path.join(PROJET, "pages/12_ADMIN_Review_Detections.py"), default_timeout=60)
    app_rd_final.session_state["utilisateur"] = ADMIN_USER
    app_rd_final.run()
    metrics_rd = {m.label: m.value for m in app_rd_final.metric}
    nb_qual = metrics_rd.get("Analyses qualifiées")
    nb_fp = metrics_rd.get("Faux positifs")
    verifier("Review Detections : 2 analyses qualifiées persistées",
             nb_qual == "2",
             f"Analyses qualifiées = {nb_qual}")
    verifier("Review Detections : 1 faux positif détecté",
             nb_fp == "1",
             f"Faux positifs = {nb_fp}")

    # ── Étape 2h : Security Alerts ──────────────────────────────────────────
    print("\n\033[1;36m━━━ 2h. Security Alerts : cycle de vie des alertes ━━━\033[0m")
    app_sa = AppTest.from_file(os.path.join(PROJET, "pages/17_ADMIN_Security_Alerts.py"), default_timeout=60)
    app_sa.session_state["utilisateur"] = ADMIN_USER
    app_sa.run()
    m_sa_init = {m.label: m.value for m in app_sa.metric}
    verifier("Security Alerts : 2 alertes initiales (1 frauduleuse + 1 suspecte)",
             m_sa_init.get("Alertes") == "2" and m_sa_init.get("Nouvelles") == "2",
             f"Total={m_sa_init.get('Alertes')}, Nouvelles={m_sa_init.get('Nouvelles')}")

    # Action 1 : Marquer comme vue l'alerte frauduleuse
    btn_vue = [b for b in app_sa.button if b.key == f"vu_{e_f['id']}"]
    if btn_vue:
        btn_vue[0].click().run()
    app_sa_v = AppTest.from_file(os.path.join(PROJET, "pages/17_ADMIN_Security_Alerts.py"), default_timeout=60)
    app_sa_v.session_state["utilisateur"] = ADMIN_USER
    app_sa_v.run()
    m_sa_v = {m.label: m.value for m in app_sa_v.metric}
    verifier("Security Alerts : statut 'Vue' persisté après rechargement",
             m_sa_v.get("Vues") == "1" and m_sa_v.get("Nouvelles") == "1",
             f"Nouvelles={m_sa_v.get('Nouvelles')}, Vues={m_sa_v.get('Vues')}")

    # Action 2 : Résoudre l'alerte
    btn_res = [b for b in app_sa_v.button if b.key == f"res_{e_f['id']}"]
    if btn_res:
        btn_res[0].click().run()
    app_sa_r = AppTest.from_file(os.path.join(PROJET, "pages/17_ADMIN_Security_Alerts.py"), default_timeout=60)
    app_sa_r.session_state["utilisateur"] = ADMIN_USER
    app_sa_r.run()
    m_sa_r = {m.label: m.value for m in app_sa_r.metric}
    verifier("Security Alerts : statut 'Résolue' persisté après rechargement",
             m_sa_r.get("Résolues") == "1" and m_sa_r.get("Vues") == "0",
             f"Résolues={m_sa_r.get('Résolues')}, Vues={m_sa_r.get('Vues')}")

    # Action 3 : Rouvrir l'alerte
    btn_reopen = [b for b in app_sa_r.button if b.key == f"reopen_{e_f['id']}"]
    if btn_reopen:
        btn_reopen[0].click().run()
    app_sa_re = AppTest.from_file(os.path.join(PROJET, "pages/17_ADMIN_Security_Alerts.py"), default_timeout=60)
    app_sa_re.session_state["utilisateur"] = ADMIN_USER
    app_sa_re.run()
    m_sa_re = {m.label: m.value for m in app_sa_re.metric}
    verifier("Security Alerts : statut 'Nouvelle' restauré après réouverture",
             m_sa_re.get("Nouvelles") == "2" and m_sa_re.get("Résolues") == "0",
             f"Nouvelles={m_sa_re.get('Nouvelles')}, Résolues={m_sa_re.get('Résolues')}")

    # ── Étape 2i : Calibration ──────────────────────────────────────────────
    print("\n\033[1;36m━━━ 2i. Calibration : modification et restauration des seuils ━━━\033[0m")
    app_cal = AppTest.from_file(os.path.join(PROJET, "pages/15_ADMIN_Calibration.py"), default_timeout=60)
    app_cal.session_state["utilisateur"] = ADMIN_USER
    app_cal.run()
    # Appliquer 0.850 / 0.950 avec raison
    app_cal.number_input[0].set_value(0.850)
    app_cal.number_input[1].set_value(0.950)
    app_cal.text_input[0].input("Ajustement de test")
    btn_app = [b for b in app_cal.button if "Appliquer" in b.label]
    if btn_app:
        btn_app[0].click().run()
    verifier("Calibration : application des seuils 0.85 / 0.95",
             abs(mg.SEUIL_SUSPECT - 0.85) < 0.001 and abs(mg.SEUIL_FRAUDULEUX - 0.95) < 0.001,
             f"suspect={mg.SEUIL_SUSPECT:.3f}, frauduleux={mg.SEUIL_FRAUDULEUX:.3f}")

    # Revenir aux seuils appris
    app_cal_rev = AppTest.from_file(os.path.join(PROJET, "pages/15_ADMIN_Calibration.py"), default_timeout=60)
    app_cal_rev.session_state["utilisateur"] = ADMIN_USER
    app_cal_rev.run()
    btn_rev = [b for b in app_cal_rev.button if "Revenir" in b.label]
    if btn_rev:
        btn_rev[0].click().run()
    verifier("Calibration : retour aux seuils appris (0.8252 / 0.9277)",
             abs(mg.SEUIL_SUSPECT - 0.8252) < 0.002 and abs(mg.SEUIL_FRAUDULEUX - 0.9277) < 0.002,
             f"suspect={mg.SEUIL_SUSPECT:.4f}, frauduleux={mg.SEUIL_FRAUDULEUX:.4f}")

    # ── Étape 2j : Attack Campaigns ─────────────────────────────────────────
    print("\n\033[1;36m━━━ 2j. Attack Campaigns : détection groupée ━━━\033[0m")
    app_ac = AppTest.from_file(os.path.join(PROJET, "pages/16_ADMIN_Attack_Campaigns.py"), default_timeout=60)
    app_ac.session_state["utilisateur"] = ADMIN_USER
    app_ac.run()
    btn_detect = [b for b in app_ac.button if "Detect Campaigns" in b.label]
    if btn_detect:
        btn_detect[0].click().run()
    camps = app_ac.session_state.get("campaigns", [])
    racines = [c["racine"] for c in camps]
    verifier("Attack Campaigns : détection d'au moins une campagne 'imite « nouvelair »'",
             any("nouvelair" in r for r in racines),
             f"Campagnes détectées : {racines}")

    # ── Étape 2k : Reports ──────────────────────────────────────────────────
    print("\n\033[1;36m━━━ 2k. Reports : génération de rapport ━━━\033[0m")
    app_rep = AppTest.from_file(os.path.join(PROJET, "pages/18_ADMIN_Reports.py"), default_timeout=60)
    app_rep.session_state["utilisateur"] = ADMIN_USER
    app_rep.run()
    btn_gen = [b for b in app_rep.button if "Generate Report" in b.label]
    if btn_gen:
        btn_gen[0].click().run()
    m_rep = {m.label: m.value for m in app_rep.metric}
    verifier("Reports : 3 analyses générées pour la période Today",
             m_rep.get("Total") == "3",
             f"Total={m_rep.get('Total')}")
    verifier("Reports : 1 analyse classée frauduleuse",
             m_rep.get("Frauduleux") == "1",
             f"Frauduleux={m_rep.get('Frauduleux')}")

    # ── Étape 2m : Connexion avec mauvais mot de passe ──────────────────────
    print("\n\033[1;36m━━━ 2m. Sécurité : tentative de connexion échouée ━━━\033[0m")
    ok_bad, msg_bad, _ = auth.connecter(EMAIL_ADMIN, "MauvaisMotDePasse")
    with session() as s:
        dernier_log_fail = (s.query(JournalAudit)
                            .filter_by(action="LOGIN_FAILED")
                            .order_by(JournalAudit.id.desc())
                            .first())
    verifier("Tentative mot de passe erroné → journalise LOGIN_FAILED",
             not ok_bad and dernier_log_fail is not None and dernier_log_fail.entite_id == EMAIL_ADMIN,
             f"action={getattr(dernier_log_fail, 'action', None)}, entite={getattr(dernier_log_fail, 'entite_id', None)}")

    # ── Étape 2l : Audit Logs ───────────────────────────────────────────────
    print("\n\033[1;36m━━━ 2l. Audit Logs : traçabilité, note et export CSV ━━━\033[0m")
    app_al = AppTest.from_file(os.path.join(PROJET, "pages/19_ADMIN_Audit_Logs.py"), default_timeout=60)
    app_al.session_state["utilisateur"] = ADMIN_USER
    app_al.run()

    # Ajout d'une note d'audit
    app_al.text_input[1].input("Note vérification audit")
    btn_note = [b for b in app_al.button if "Enregistrer" in b.label]
    if btn_note:
        btn_note[0].click().run()

    # Relecture des logs en base
    with session() as s:
        tous_logs = s.query(JournalAudit).order_by(JournalAudit.id.asc()).all()
        actions_presentes = {l.action for l in tous_logs}
        note_log = s.query(JournalAudit).filter_by(action="NOTE").first()

    verifier("Audit Logs : ajout d'une note consignée avec action 'NOTE'",
             note_log is not None and "Note vérification audit" in note_log.details,
             f"note='{getattr(note_log, 'details', None)}'")

    # Vérification présence des actions clés sans hallucination
    actions_attendues = {
        "CREATE_ADMIN", "LOGIN", "LOGIN_FAILED", "ACTIVATE_USER",
        "SUSPEND_USER", "DELETE_ADMIN", "DOMAIN_ADD", "DOMAIN_REMOVE",
        "QUALIFICATION", "ALERT_VIEW", "ALERT_RESOLVE", "ALERT_REOPEN",
        "THRESHOLD_CHANGE", "NOTE",
    }
    manquantes = actions_attendues - actions_presentes
    verifier("Audit Logs : toutes les actions d'administration tracées",
             len(manquantes) == 0,
             f"{len(tous_logs)} logs au total, manquantes: {manquantes or 'aucune'}")

    # Vérification présence du bouton d'export CSV
    app_al_post = AppTest.from_file(os.path.join(PROJET, "pages/19_ADMIN_Audit_Logs.py"), default_timeout=60)
    app_al_post.session_state["utilisateur"] = ADMIN_USER
    app_al_post.run()
    dl_csv = [b for b in app_al_post.download_button if "CSV" in b.label]
    verifier("Audit Logs : bouton d'export CSV opérationnel",
             len(dl_csv) > 0,
             f"label='{dl_csv[0].label}'" if dl_csv else "non trouvé")

    # ── Nettoyage et restauration ───────────────────────────────────────────
    print("\n\033[1;36m━━━ Nettoyage et Restauration ━━━\033[0m")
    import services.database as db_mod
    import gc
    if db_mod._moteur is not None:
        db_mod._moteur.dispose()
    db_mod._moteur = None
    db_mod._Session = None
    gc.collect()

    if os.path.exists(config_backup):
        shutil.copy2(config_backup, config_path)
        os.remove(config_backup)
        print("  ✔ config_mailguard.json restauré dans son état initial.")

    if os.path.exists(db_jetable_fichier):
        try:
            os.remove(db_jetable_fichier)
            print("  ✔ Base temporaire supprimée.")
        except Exception as e:
            print(f"  ⚠ Nettoyage base temporaire : {e}")

    # ── Bilan ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    total = len(RESULTATS)
    reussis = sum(1 for _, ok, _ in RESULTATS if ok)
    print(f"BILAN : {reussis}/{total} vérifications réussies.")
    print("=" * 80)


if __name__ == "__main__":
    main()
