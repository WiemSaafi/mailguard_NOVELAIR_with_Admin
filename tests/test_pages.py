"""
test_pages.py — exécute réellement chaque page Streamlit et signale toute
exception levée au rendu.

Lancement :  python tests/test_pages.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import socket as _s  # noqa: E402

_s.setdefaulttimeout(4)
import stubs  # noqa: F401,E402

# Racine du projet : le dossier parent de tests/. Fonctionne quel que soit
# l'endroit ou le projet est installe.
PROJET = os.environ.get(
    "MAILGUARD_DIR",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
sys.path.insert(0, PROJET)
os.chdir(PROJET)

from streamlit.testing.v1 import AppTest  # noqa: E402
from services import auth_service as auth  # noqa: E402

# Un compte de test : les pages sont desormais protegees par le verrou
# d'authentification, il faut donc ouvrir une session avant de les rendre.
EMAIL_TEST, MDP_TEST = "banc.essai@exemple.com", "motdepasse1"
auth.inscrire(EMAIL_TEST, MDP_TEST, "Banc d'essai")
auth.activer_compte(EMAIL_TEST)   # les comptes attendent la validation d'un admin
_ok, _msg, UTILISATEUR = auth.connecter(EMAIL_TEST, MDP_TEST)
assert _ok, _msg

import glob  # noqa: E402

PAGES = ["app.py"] + sorted(
    os.path.relpath(f, PROJET) for f in glob.glob(os.path.join(PROJET, "pages", "*.py"))
    if not os.path.basename(f).startswith("_")
)

OK, KO = "\033[32m✔\033[0m", "\033[31m✘\033[0m"
echecs = []
print("\n\033[1;36m━━━ Rendu des pages Streamlit ━━━\033[0m")

for page in PAGES:
    essai = AppTest.from_file(os.path.join(PROJET, page), default_timeout=90)
    essai.session_state["utilisateur"] = UTILISATEUR
    essai.session_state["seuil_suspect"] = 0.825
    essai.session_state["seuil_dangereux"] = 0.928
    essai.session_state["action_config"] = "quarantaine"
    try:
        essai.run()
        erreurs = list(essai.exception)
        if erreurs:
            echecs.append((page, erreurs[0].value))
            print(f"  \033[31m✘\033[0m {page}\n      {erreurs[0].value}")
        else:
            print(f"  \033[32m✔\033[0m {page}")
    except Exception as exc:
        echecs.append((page, repr(exc)))
        print(f"  \033[31m✘\033[0m {page}\n      {exc!r}")

# ── Écran d'authentification : la barre des pages doit être masquée ──────
print("\n\033[1;36m━━━ Écran de connexion ━━━\033[0m")
_essai_auth = AppTest.from_file(os.path.join(PROJET, "app.py"), default_timeout=120)
_essai_auth.run()
_texte_auth = " ".join(b.value for b in _essai_auth.markdown)

for _libelle, _condition in (
    ("la barre des pages est masquée tant que personne n'est connecté",
     '[data-testid="stSidebar"]' in _texte_auth and "display:none" in _texte_auth),
    ("l'écran s'affiche sans exception", not list(_essai_auth.exception)),
    ("la marque et le titre sont présents",
     "MailGuard" in _texte_auth and "n'arrive jamais" in _texte_auth),
    ("les deux onglets sont proposés", len(_essai_auth.tabs) >= 2),
):
    print(f"  {OK if _condition else KO} {_libelle}")
    if not _condition:
        echecs.append(("écran de connexion", _libelle))


# ── Parcours : remplir le formulaire d'analyse et le soumettre ───────────
print("\n\033[1;36m━━━ Parcours : analyser un message ━━━\033[0m")
PAGE_TEST = [p for p in PAGES if "Test_Manuel" in p or "Analyser" in p][0]
essai = AppTest.from_file(os.path.join(PROJET, PAGE_TEST), default_timeout=120)
essai.session_state["utilisateur"] = UTILISATEUR
essai.session_state["utilisateur"] = UTILISATEUR
essai.session_state["seuil_suspect"] = 0.825
essai.session_state["seuil_dangereux"] = 0.928
essai.run()

# le premier bouton doit pré-remplir le formulaire (correctif des exemples)
CLE_DOM = "saisie_domaine" if "Analyser" in PAGE_TEST else "ex_domaine"
exemples = [b for b in essai.button if "hishing" in b.label or "Une tentative" in b.label]
exemples[0].click().run()
try:
    _valeur_dom = essai.session_state[CLE_DOM]
except Exception:
    _valeur_dom = None
prerempli = _valeur_dom == "nouvelair-verification.com"
print(f"  {OK if prerempli else KO} "
      f"l'exemple pré-remplit le formulaire "
      f"(domaine = {_valeur_dom!r})")
if not prerempli:
    echecs.append(("exemples", "le formulaire n'est pas pré-rempli"))

soumettre = [b for b in essai.button if "ANALYSER" in b.label.upper()]
assert soumettre, "bouton de soumission introuvable"
soumettre[0].click().run()

erreurs = list(essai.exception)
if erreurs:
    echecs.append(("soumission", erreurs[0].value))
    print(f"  \033[31m✘\033[0m soumission du formulaire\n      {erreurs[0].value}")
else:
    marqueurs = " ".join(bloc.value for bloc in essai.markdown)
    verdict = ("Frauduleux" in marqueurs) or ("FRAUDULEUX" in marqueurs)
    print(f"  {OK if verdict else KO} "
          f"le typosquat ressort frauduleux dans le bandeau de verdict")
    if not verdict:
        echecs.append(("verdict", "bandeau de verdict absent ou mal libellé"))

# ── Parcours : effacement de l'historique en deux temps ─────────────────
print("\n\033[1;36m━━━ Parcours : effacer l'historique ━━━\033[0m")
from services.history_service import ajouter_entree, charger_historique  # noqa: E402
import mailguard_core as mg  # noqa: E402

resultat = mg.analyser_email_complet(
    "nouvelairr.com", "Votre compte a été suspendu, vérifiez vos informations "
    "bancaires immédiatement sous 24 heures.", [], "spf=fail dkim=fail dmarc=fail")
ajouter_entree("nouvelairr.com", "Test", "texte", 0, resultat, 12.0,
               "Quarantaine", "manuel", "t1",
               identifiant=UTILISATEUR["identifiant"])

PAGE_HIST = [p for p in PAGES if "Historique" in p][0]
essai = AppTest.from_file(os.path.join(PROJET, PAGE_HIST), default_timeout=120)
essai.session_state["utilisateur"] = UTILISATEUR
essai.session_state["utilisateur"] = UTILISATEUR
essai.session_state["seuil_suspect"] = 0.825
essai.session_state["seuil_dangereux"] = 0.928
essai.run()

bouton = [b for b in essai.button if "Effacer" in b.label]
if not bouton:
    echecs.append(("historique", "bouton d'effacement absent"))
    print("  \033[31m✘\033[0m bouton d'effacement absent")
else:
    bouton[0].click().run()
    confirmer = [b for b in essai.button if "Confirmer la suppression" in b.label or "définitivement" in b.label]
    print(f"  {OK if confirmer else KO} "
          f"la confirmation reste affichée après le premier clic")
    if confirmer:
        confirmer[0].click().run()
        vide = charger_historique(UTILISATEUR["identifiant"]) == []
        print(f"  {OK if vide else KO} "
              f"l'historique est bien vidé")
        if not vide:
            echecs.append(("historique", "l'effacement n'a rien supprimé"))
    else:
        echecs.append(("historique", "confirmation inatteignable"))

print()
if echecs:
    print(f"  \033[31m{len(echecs)} problème(s)\033[0m")
    sys.exit(1)
print("  \033[32mtoutes les pages se rendent sans erreur\033[0m\n")
