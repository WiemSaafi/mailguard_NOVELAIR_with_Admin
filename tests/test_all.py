"""
test_all.py — banc d'essai de MailGuard (5 signaux + fusion).

Lancement :  python tests/test_all.py

Partie A : la logique de l'application (seuils, catégories, explications).
           Ne demande aucun modèle.
Partie B : le moteur réel (dossier modeles_mailguard/). Sautée si les
           modèles ne sont pas là.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stubs  # noqa: F401,E402  (hors ligne : signal 2 muet)

PROJET = os.environ.get("MAILGUARD_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJET)

RESULTATS = []
_section = [""]


def section(titre):
    _section[0] = titre
    print(f"\n\033[1;36m━━━ {titre} ━━━\033[0m")


def check(nom, condition, detail=""):
    ok = bool(condition)
    RESULTATS.append((_section[0], nom, ok, detail))
    icone = "\033[32m✔\033[0m" if ok else "\033[31m✘\033[0m"
    print(f"  {icone} {nom}" + (f"   \033[90m{detail}\033[0m" if detail else ""))
    return ok


# ============================================================ A. logique
section("A1. Seuils de décision")
import mailguard_core as mg  # noqa: E402
from services import quarantine_service as qs  # noqa: E402

check("Seuil frauduleux de la fusion ≈ 0,928", abs(mg.SEUIL_FRAUDULEUX - 0.928) < 0.002, f"{mg.SEUIL_FRAUDULEUX}")
check("Seuil suspect de la fusion ≈ 0,825", abs(mg.SEUIL_SUSPECT - 0.825) < 0.002, f"{mg.SEUIL_SUSPECT}")
check("SEUIL_DECISION = seuil frauduleux", mg.SEUIL_DECISION == mg.SEUIL_FRAUDULEUX)
check("Poids normalisés somment à 1", abs(sum(mg.POIDS.values()) - 1) < 0.01, f"{sum(mg.POIDS.values()):.3f}")
check("S5 authentification a le plus grand poids", max(mg.POIDS, key=mg.POIDS.get) == "authentification")

s, d = qs.migrer_seuils(0.25, 0.50)
check("Anciens seuils 0,25 / 0,50 remplacés par ceux de la fusion", s > 0.8 and d > 0.9, f"{s} / {d}")
s, d = qs.migrer_seuils(0.85, 0.95)
check("Seuils récents conservés", (s, d) == (0.85, 0.95))

section("A2. Catégorisation")
check("Score 0,10 → LÉGITIME", qs.categoriser_email(0.10) == "LÉGITIME")
check("Score 0,50 → LÉGITIME (ancien seuil, plus valable)", qs.categoriser_email(0.50) == "LÉGITIME")
check("Score 0,85 → SUSPECT", qs.categoriser_email(0.85) == "SUSPECT")
check("Score 0,95 → DANGEREUX (affiché FRAUDULEUX)", qs.categoriser_email(0.95) == "DANGEREUX")
check("Libellé du badge = FRAUDULEUX", qs.get_badge_info("DANGEREUX")["label"] == "FRAUDULEUX")
regle = {"etape_decision": "1. règle sûre", "categorie": "FRAUDULEUX"}
check("Règle sûre respectée même avec un score bas", qs.categoriser_email(0.1, regle) == "DANGEREUX")
blanche = {"etape_decision": "0. liste blanche (domaine prouvé)", "categorie": "LÉGITIME"}
check("Liste blanche prouvée respectée", qs.categoriser_email(0.99, blanche) == "LÉGITIME")

section("A3. Explications")
faux = {"etape_decision": "2. score ≥ seuil suspect", "categorie": "SUSPECT",
        "scores_detail": {"domaine_bert": 0.1, "liens": 0.0, "authentification": 0.7, "contenu": 0.6,
                          "domaine_randomforest": None},
        "details": {"domaine_bert": {"verdict": "LÉGITIME (aucune imitation, score 0.10)", "score": 0.1},
                    "contenu": {"probabilite": 0.6, "suspect": True, "seuil": 0.391},
                    "authentification": {"spf": "fail", "dkim": "none", "dmarc": "fail", "decision": "suspect"},
                    "liens": [], "fusion": {"score": 0.86, "seuil_suspect": 0.825, "seuil_frauduleux": 0.928}}}
facteurs = qs.construire_explication(faux)
check("L'étape de décision est expliquée", any("Étape" in f for f in facteurs))
check("S4 signalé comme phishing", any(f.startswith("✗ S4") for f in facteurs))
check("S2 muet signalé comme tel", any(f.startswith("– S2") for f in facteurs))
check("Tableau : une ligne par signal", len(qs.construire_tableau_signaux(faux)) == 5)

# ============================================================ B. moteur
section("B. Moteur réel (modeles_mailguard)")
if not mg._recharger_si_absent():
    print(f"  \033[33m⚠ modèles absents, partie B sautée : {mg._ERREUR_CHARGEMENT}\033[0m")
else:
    def auth(dom, spf="pass", dkim="pass", dmarc="pass", mailfrom=None):
        return (f"mx.nouvelair.com; spf={spf} smtp.mailfrom={mailfrom or dom}; "
                f"dkim={dkim} header.d={dom}; dmarc={dmarc} header.from={dom}")

    CAS = [
        ("Usurpation de nouvelair.com (DMARC échoue)", "FRAUDULEUX",
         ("rh@nouvelair.com", "Merci de mettre à jour votre mot de passe en cliquant ici.", [],
          auth("nouvelair.com", "fail", "none", "fail", "mail-out.ru"))),
        ("Typosquat nouvelairr.com", "FRAUDULEUX",
         ("service@nouvelairr.com", "Votre réservation est bloquée, confirmez votre carte bancaire.", [],
          auth("nouvelairr.com"))),
        ("Liste noire (nouve1air.com)", "FRAUDULEUX",
         ("x@nouve1air.com", "Bonjour", [], "")),
        ("Partenaire de la liste blanche, authentifié", "LÉGITIME",
         ("info@biat.com.tn", "Bonjour, veuillez trouver ci-joint le relevé du mois.", [], auth("biat.com.tn"))),
    ]
    for titre, attendu, (exp, texte, liens, entetes) in CAS:
        r = mg.analyser_email_complet(exp, texte, liens, entetes)
        check(f"{titre} → {attendu}", r["categorie"] == attendu,
              f"{r['categorie']} · {r['etape_decision']} · score {r['score_final']:.3f}")

    r = mg.analyser_email_complet("info@biat.com.tn", "Bonjour", [], auth("biat.com.tn", "fail", "none", "fail", "x.ru"))
    check("Liste blanche NON prouvée → ne passe pas par la liste blanche",
          not r["etape_decision"].startswith("0. liste blanche"), r["etape_decision"])
    check("Le résultat porte les 5 clés de signaux",
          set(r["scores_detail"]) == {"domaine_bert", "liens", "authentification", "contenu", "domaine_randomforest"})
    check("Chaque décision non légitime a au moins une raison",
          all(mg.analyser_email_complet(*c[2])["raisons"] for c in CAS if c[1] != "LÉGITIME"))
    d = mg.analyser_domaine_bert("nouvelair.com")
    check("Domaine officiel reconnu par S1", "LÉGITIME" in d["verdict"], d["verdict"])

# ============================================================ bilan
ok = sum(1 for r in RESULTATS if r[2])
print(f"\n\033[1m{ok}/{len(RESULTATS)} vérifications réussies\033[0m")
sys.exit(0 if ok == len(RESULTATS) else 1)
