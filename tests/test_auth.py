"""
test_auth.py — vérifie le service de comptes utilisateurs.

    python tests/test_auth.py

Le script travaille dans un dossier temporaire : ni le magasin de comptes réel
ni les historiques existants ne sont touchés.
"""

import os
import sys
import shutil
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Isolation : la base de test est jetable, la vraie n'est jamais touchee ──
_TEMP = tempfile.mkdtemp(prefix="mailguard_auth_")
_BASE_TEST = os.path.join(_TEMP, "essai.db")
os.environ["MAILGUARD_DATABASE_URL"] = f"sqlite:///{_BASE_TEST}"

from services import database as db  # noqa: E402

db.reinitialiser_moteur(f"sqlite:///{_BASE_TEST}")

from services import auth_service as auth  # noqa: E402

auth.CHEMIN_ENV = os.path.join(_TEMP, ".env")

RESULTATS = []
_section = [""]


def section(titre):
    _section[0] = titre
    print(f"\n\033[1;36m━━━ {titre} ━━━\033[0m")


def check(nom, condition, detail=""):
    ok = bool(condition)
    RESULTATS.append((_section[0], nom, ok, detail))
    print("  " + ("\033[32m✔\033[0m" if ok else "\033[31m✘\033[0m") + f" {nom}"
          + ("   \033[90m" + str(detail) + "\033[0m" if detail else ""))


EMAIL = "wiem.saafi@exemple.com"
MDP = "MailGuard2026"

# ══════════════════════════════════════════════════════════════════ 1
section("1. Inscription")

ok, message = auth.inscrire(EMAIL, MDP, "Wiem")
auth.activer_compte(EMAIL)   # validation par un administrateur
check("Création d'un compte valide", ok, message)
check("L'adresse d'inscription devient la boîte à surveiller",
      auth.lire_messagerie(EMAIL)["adresse"] == EMAIL,
      auth.lire_messagerie(EMAIL)["adresse"])
check("Mais le mot de passe d'application reste à fournir",
      auth.lire_messagerie(EMAIL)["mot_de_passe"] == "",
      "aucun fournisseur ne le communique à un programme")

ok, message = auth.inscrire(EMAIL, MDP, "Wiem")
check("Refus d'une adresse déjà utilisée", not ok, message)

for adresse in ("pas-une-adresse", "sans@domaine", "@exemple.com", "a b@c.com"):
    ok, _ = auth.inscrire(adresse, MDP)
    check(f"Adresse invalide refusée : {adresse!r}", not ok)

for faible, raison in (("court1", "trop court"), ("motdepasse", "sans chiffre"),
                       ("12345678", "sans lettre")):
    ok, message = auth.inscrire(f"x{faible}@exemple.com", faible)
    check(f"Mot de passe faible refusé ({raison})", not ok, message)

check("La casse et les espaces de l'adresse sont normalisés",
      auth.compte_existe("  WIEM.SAAFI@Exemple.COM  "))

# ══════════════════════════════════════════════════════════════════ 2
section("2. Stockage du mot de passe")

comptes = auth.charger_comptes()
compte = comptes[EMAIL]

check("Le mot de passe n'apparaît nulle part en clair",
      MDP not in str(comptes), "vérification sur toute la table des comptes")
check("Il n'apparaît pas non plus dans le fichier de base",
      MDP.encode() not in open(_BASE_TEST, "rb").read(),
      "lecture binaire du fichier SQLite")
check("Une empreinte et un sel sont enregistrés",
      bool(compte["empreinte"]) and bool(compte["sel"]))

autre = auth.hacher_mot_de_passe(MDP)[0]
check("Deux hachages du même mot de passe diffèrent",
      autre != compte["empreinte"], "le sel est bien aléatoire")
check("L'empreinte fait 32 octets (SHA-256)",
      len(__import__("base64").b64decode(compte["empreinte"])) == 32)

# ══════════════════════════════════════════════════════════════════ 3
section("3. Connexion")

ok, message, utilisateur = auth.connecter(EMAIL, MDP)
check("Connexion avec les bons identifiants", ok, message)
check("La session contient l'identifiant du compte",
      utilisateur.get("identifiant") and len(utilisateur["identifiant"]) == 16)

ok, message, _ = auth.connecter(EMAIL, "MauvaisMotDePasse1")
check("Mot de passe erroné refusé", not ok)

ok, message_inconnu, _ = auth.connecter("inconnu@exemple.com", MDP)
check("Compte inexistant refusé", not ok)
check("Le message ne révèle pas si l'adresse existe",
      message == message_inconnu, message)

depart = time.time()
auth.connecter("inconnu@exemple.com", MDP)
duree_inconnu = time.time() - depart
check("Un compte inexistant coûte quand même un hachage",
      duree_inconnu > 0.02, f"{duree_inconnu * 1000:.0f} ms")

check("La date de dernière connexion est mise à jour",
      auth.charger_comptes()[EMAIL]["derniere_connexion"] is not None)

# ══════════════════════════════════════════════════════════════════ 4
section("4. Identifiants Gmail chiffrés")

MDP_APP = "abcd efgh ijkl mnop"
ok, message = auth.enregistrer_gmail(EMAIL, "wiem@gmail.com", MDP_APP)
check("Enregistrement des identifiants Gmail", ok, message)

brut = open(_BASE_TEST, "rb").read()
check("Le mot de passe d'application n'est pas lisible dans la base",
      b"abcdefghijklmnop" not in brut and MDP_APP.encode() not in brut)

adresse, secret = auth.lire_gmail(EMAIL)
check("Déchiffrement correct", secret == "abcdefghijklmnop", secret)
check("Les espaces du mot de passe Google sont retirés", " " not in secret)
check("L'adresse Gmail est restituée", adresse == "wiem@gmail.com")

auth.oublier_gmail(EMAIL)
check("Oubli des identifiants", auth.lire_gmail(EMAIL) == ("", ""))
auth.enregistrer_gmail(EMAIL, "wiem@gmail.com", MDP_APP)

# ══════════════════════════════════════════════════════════════════ 5
section("5. Cloisonnement entre comptes")

EMAIL2, MDP2 = "collegue@exemple.com", "AutreMotDePasse9"
auth.inscrire(EMAIL2, MDP2, "Collègue")
auth.activer_compte(EMAIL2)
_, _, utilisateur2 = auth.connecter(EMAIL2, MDP2)

check("Deux comptes ont des identifiants distincts",
      utilisateur["identifiant"] != utilisateur2["identifiant"])
check("L'identifiant ne laisse pas deviner l'adresse",
      "@" not in utilisateur["identifiant"]
      and EMAIL.split("@")[0] not in utilisateur["identifiant"])
check("L'identifiant est stable dans le temps",
      auth.identifiant_utilisateur(EMAIL) == utilisateur["identifiant"])

from services import history_service as hs  # noqa: E402

hs.effacer_historique(utilisateur["identifiant"])
hs.effacer_historique(utilisateur2["identifiant"])

faux_resultat = {
    "score_final": 0.9, "etage": 1, "signaux_calcules": 4,
    "scores_detail": {"domaine_bert": 1.0, "contenu": 1.0,
                      "liens": 0.0, "authentification": 1.0},
    "details": {},
}
hs.ajouter_entree("nouvelairr.com", "Test", "texte", 0, faux_resultat, 10.0,
                  "Quarantaine", "manuel", "u1",
                  identifiant=utilisateur["identifiant"])

check("L'analyse est visible par son auteur",
      len(hs.charger_historique(utilisateur["identifiant"])) == 1)
check("Elle est invisible pour l'autre compte",
      hs.charger_historique(utilisateur2["identifiant"]) == [])
check("Les statistiques sont propres à chaque compte",
      hs.get_stats(utilisateur["identifiant"])["total"] == 1
      and hs.get_stats(utilisateur2["identifiant"])["total"] == 0)

# ══════════════════════════════════════════════════════════════════ 6
section("6. Préférences par compte")

auth.enregistrer_preferences(EMAIL, seuil_suspect=0.15, seuil_dangereux=0.60,
                             action_config="rien")
preferences = auth.lire_preferences(EMAIL)
check("Les seuils sont enregistrés sur le compte",
      preferences["seuil_suspect"] == 0.15 and preferences["seuil_dangereux"] == 0.60)
check("L'action automatique aussi", preferences["action_config"] == "rien")
check("Les préférences de l'autre compte sont inchangées",
      auth.lire_preferences(EMAIL2)["seuil_suspect"] == 0.825)

auth.enregistrer_preferences(EMAIL, empreinte="tentative", sel="tentative")
check("Une clé sensible ne peut pas être écrasée par ce chemin",
      auth.charger_comptes()[EMAIL]["empreinte"] != "tentative")

# ══════════════════════════════════════════════════════════════════ 7
section("7. Changement de mot de passe et suppression")

ok, message = auth.changer_mot_de_passe(EMAIL, "mauvais", "NouveauMdp2026")
check("Changement refusé si l'ancien est faux", not ok, message)

ok, message = auth.changer_mot_de_passe(EMAIL, MDP, "court")
check("Changement refusé si le nouveau est faible", not ok, message)

ok, message = auth.changer_mot_de_passe(EMAIL, MDP, "NouveauMdp2026")
check("Changement accepté", ok, message)
check("L'ancien mot de passe ne fonctionne plus",
      not auth.connecter(EMAIL, MDP)[0])
check("Le nouveau fonctionne", auth.connecter(EMAIL, "NouveauMdp2026")[0])

ok, _ = auth.supprimer_compte(EMAIL2, "mauvais")
check("Suppression refusée sans le bon mot de passe", not ok)

hs.ajouter_entree("x.com", "Test", "texte", 0, faux_resultat, 10.0,
                  "Quarantaine", "manuel", "u2",
                  identifiant=utilisateur2["identifiant"])
avant = len(hs.charger_historique(utilisateur2["identifiant"]))

ok, message = auth.supprimer_compte(EMAIL2, MDP2)
check("Suppression du compte", ok, message)
check("Le compte a disparu de la table", not auth.compte_existe(EMAIL2))
check("Ses analyses ont été supprimées en cascade",
      avant == 1 and hs.charger_historique(utilisateur2["identifiant"]) == [])
check("L'autre compte est intact", auth.compte_existe(EMAIL))

with db.session() as _s:
    orphelins = (_s.query(db.ScoreSignal)
                 .outerjoin(db.Analyse, db.Analyse.id == db.ScoreSignal.analyse_id)
                 .filter(db.Analyse.id.is_(None)).count())
    sans_compte = (_s.query(db.IdentifiantGmail)
                   .outerjoin(db.Utilisateur,
                              db.Utilisateur.id == db.IdentifiantGmail.utilisateur_id)
                   .filter(db.Utilisateur.id.is_(None)).count())
check("Aucun score orphelin apres suppression", orphelins == 0)
check("Aucun identifiant Gmail orphelin", sans_compte == 0)

# ══════════════════════════════════════════════════════════════════ 8
section("8. Schéma de la base")

with db.session() as _s:
    tables = db.Base.metadata.tables
check("Les onze tables sont créées",
      set(tables) == {"utilisateurs", "identifiants_gmail", "preferences", "analyses",
                      "scores_signaux", "administrateurs", "domains_confiance",
                      "domains_frauduleux", "qualifications", "etats_alertes",
                      "journal_audit"}, ", ".join(sorted(tables)))
check("L'adresse email est unique et indexée",
      tables["utilisateurs"].c.email.unique and tables["utilisateurs"].c.email.index)
ok_doublon, _ = auth.inscrire(EMAIL.upper(), "AutreMdp123")
check("La contrainte d'unicité empêche un doublon", not ok_doublon)
check("Les cles etrangeres suppriment en cascade",
      all(fk.ondelete == "CASCADE"
          for t in tables.values() for c in t.columns for fk in c.foreign_keys))

db.reinitialiser_moteur(f"sqlite:///{_BASE_TEST}")
check("La base se rouvre sans perte", auth.compte_existe(EMAIL))

# ══════════════════════════════════════════════════════════════════ 9
section("9. Protocoles de relève et chargement des modèles")

from services.mail_providers import (  # noqa: E402
    PROTOCOLES, FournisseurGraph, FournisseurImap, FournisseurPop3,
    creer_fournisseur,
)

check("Trois protocoles proposés", set(PROTOCOLES) == {"imap", "pop3", "graph"})
check("La fabrique renvoie la bonne implémentation",
      isinstance(creer_fournisseur("imap"), FournisseurImap)
      and isinstance(creer_fournisseur("pop3"), FournisseurPop3)
      and isinstance(creer_fournisseur("graph"), FournisseurGraph))
check("Un protocole inconnu retombe sur IMAP",
      isinstance(creer_fournisseur("smtp"), FournisseurImap))

# Le dictionnaire de lire_messagerie() contient deja la cle "protocole" :
# le passer en plus du premier argument levait un TypeError.
_reglages = {"protocole": "pop3", "adresse": "a@b.com", "mot_de_passe": "x",
             "serveur": "pop.b.com", "port": 995, "tenant_id": "",
             "client_id": "", "client_secret": ""}
check("creer_fournisseur accepte directement le dictionnaire des réglages",
      isinstance(creer_fournisseur(**_reglages), FournisseurPop3))
check("Et tolère aussi le protocole donné deux fois",
      isinstance(creer_fournisseur(_reglages["protocole"], **_reglages),
                 FournisseurPop3))
check("POP3 annonce qu'il ne peut pas déplacer",
      PROTOCOLES["pop3"]["deplacement"] is False
      and PROTOCOLES["imap"]["deplacement"] is True
      and PROTOCOLES["graph"]["deplacement"] is True)
check("POP3 le dit aussi dans l'action appliquée",
      "impossible" in FournisseurPop3().appliquer_action(b"1", "DANGEREUX", "quarantaine"))
check("Aucun protocole n'agit sur un message légitime",
      all("conservé" in creer_fournisseur(p).appliquer_action(b"1", "LÉGITIME", "quarantaine")
          for p in ("imap", "pop3", "graph")))
check("Graph refuse proprement sans les éléments Azure",
      FournisseurGraph(adresse="a@b.com").connecter()[0] is False,
      FournisseurGraph(adresse="a@b.com").connecter()[1][:70])

auth.enregistrer_messagerie(EMAIL, "graph", adresse="chef@nouvelair.com",
                            tenant_id="T-1", client_id="C-1",
                            client_secret="SecretAzure")
m = auth.lire_messagerie(EMAIL)
check("Les identifiants Graph sont restitués",
      m["protocole"] == "graph" and m["tenant_id"] == "T-1"
      and m["client_secret"] == "SecretAzure")
check("Le secret Azure n'est pas lisible dans la base",
      b"SecretAzure" not in open(_BASE_TEST, "rb").read())

auth.enregistrer_messagerie(EMAIL, "pop3", adresse="x@gmail.com",
                            mot_de_passe="abcd efgh ijkl mnop",
                            serveur="pop.gmail.com", port=995)
m = auth.lire_messagerie(EMAIL)
check("Le changement de protocole est conservé",
      m["protocole"] == "pop3" and m["port"] == 995
      and m["mot_de_passe"] == "abcdefghijklmnop")

auth.enregistrer_messagerie(EMAIL, "pop3", adresse="x@gmail.com",
                            mot_de_passe="", serveur="pop.gmail.com", port=995)
check("Un secret laissé vide conserve l'ancien",
      auth.lire_messagerie(EMAIL)["mot_de_passe"] == "abcdefghijklmnop")

auth.oublier_gmail(EMAIL)
efface = auth.lire_messagerie(EMAIL)
check("L'oubli efface tous les secrets, tous protocoles confondus",
      not any([efface["adresse"], efface["mot_de_passe"], efface["client_secret"],
               efface["tenant_id"], efface["client_id"]]))

# ══════════════════════════════════════════════════════════════════ bilan
db.reinitialiser_moteur.__self__ if False else None
shutil.rmtree(_TEMP, ignore_errors=True)

total = len(RESULTATS)
reussis = sum(1 for *_, ok, _ in RESULTATS if ok)
print(f"\n  {reussis}/{total} vérifications passées\n")

echecs = [(s, n, d) for s, n, ok, d in RESULTATS if not ok]
if echecs:
    print("  Échecs :")
    for s, n, d in echecs:
        print(f"    • [{s}] {n} — {d}")
sys.exit(0 if not echecs else 1)
