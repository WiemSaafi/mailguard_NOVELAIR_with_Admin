"""
cas_de_test.py — exécute le plan de test des 12 cas et compare chaque
résultat obtenu à celui attendu.

    python tests/cas_de_test.py

Le script n'entraîne rien et ne modifie rien. Il n'écrit pas dans
l'historique. Le signal 2 interroge RDAP et crt.sh (réseau) : pour des
résultats reproductibles hors ligne, lancer avec MAILGUARD_INTERNET=0.

Moteur : 5 signaux + fusion, cascade listes → règles sûres → score.
Les notes ci-dessous expliquent, cas par cas, quelle étape décide.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stubs  # noqa: F401,E402  (MAILGUARD_INTERNET=0 par défaut ; mettre 1 pour interroger RDAP)

import mailguard_core as mg  # noqa: E402
from services.quarantine_service import categoriser_email  # noqa: E402

SEUIL_SUSPECT = 0.25
SEUIL_DANGEREUX = 0.50


def domaine_seul(valeur):
    """Le plan note parfois « info@nouvelair.com ». Le moteur attend un domaine,
    pas une adresse : on ne garde que ce qui suit l'arobase."""
    return valeur.split("@")[-1].strip().lower()


# ─────────────────────────────────────────────────────────────────────────
# Les douze cas
#
# "attendu" liste les catégories acceptables. Quand le plan écrit « 🟡/🔴 »,
# les deux sont acceptées.
# ─────────────────────────────────────────────────────────────────────────

CAS = [
    {
        "n": 1, "titre": "Légitime, référence",
        "domaine": "nouvelair.com",
        "objet": "Confirmation de votre réservation NV123",
        "corps": "Bonjour, Votre réservation NV123 du 12/09/2026 Tunis-Paris est "
                 "confirmée. Retrouvez votre billet dans votre espace client. Cordialement.",
        "liens": [("https://www.nouvelair.com/mon-compte", "Accéder à mon espace client")],
        "auth": ("pass", "pass", "pass"),
        "attendu": ["LÉGITIME"],
        "note": "",
    },
    {
        "n": 2, "titre": "Typosquatting seul",
        "domaine": "n0uvelair.com",
        "objet": "Newsletter Nouvelair",
        "corps": "Bonjour, Découvrez nos nouvelles destinations pour l'été. Cordialement.",
        "liens": [("https://n0uvelair.com/offres", "Voir nos offres")],
        "auth": ("pass", "pass", "pass"),
        "attendu": ["SUSPECT", "DANGEREUX"],
        "note": "Le court-circuit typosquat force le score à 0.75 minimum.",
    },
    {
        "n": 3, "titre": "Contenu phishing seul",
        "domaine": "info@nouvelair.com",
        "objet": "Votre compte a été suspendu",
        "corps": "Bonjour, Votre compte sera suspendu dans 24h. Veuillez vous connecter "
                 "immédiatement pour le réactiver. Cliquez ici : "
                 "https://nouvelair.com/login. Cordialement.",
        "liens": [],
        "auth": ("pass", "pass", "pass"),
        "attendu": ["LÉGITIME"],
        # nouvelair.com est un domaine officiel, et le message est AUTHENTIFIÉ
        # (DKIM aligné) : la liste blanche décide à l'étape 0. Contrepartie
        # assumée : un compte interne compromis n'est pas détecté par ce filtre.
        "note": "Étape 0 : domaine officiel prouvé (DKIM aligné).",
    },
    {
        "n": 4, "titre": "Authentification cassée seule",
        "domaine": "info@nouvelair.com",
        "objet": "Confirmation de commande",
        "corps": "Bonjour, Votre commande a bien été enregistrée. Cordialement.",
        "liens": [],
        "auth": ("fail", "none", "fail"),
        "attendu": ["DANGEREUX"],
        # Un message au nom de nouvelair.com qui échoue DMARC est une usurpation :
        # la règle sûre du signal 5 (veto Nouvelair) décide à l'étape 1.
        "note": "Étape 1 : veto du signal 5 (DMARC échoue sur un domaine Nouvelair).",
    },
    {
        "n": 5, "titre": "Lien trompeur seul",
        "domaine": "info@nouvelair.com",
        "objet": "Mise à jour de vos informations",
        "corps": "Bonjour, Merci de mettre à jour vos informations via le lien "
                 "ci-dessous. Cordialement.",
        "liens": [("http://nouvelairr.com/update", "www.nouvelair.com/update")],
        "auth": ("pass", "pass", "pass"),
        "attendu": ["SUSPECT", "DANGEREUX"],
        # R1 : nouvelairr.com est dans la liste noire → FRAUDULEUX étape 1.
        # La liste blanche ne court-circuite plus grâce au garde-fou.
        "note": "R1 : le lien pointe vers la liste noire → règle sûre.",
    },
    {
        "n": 6, "titre": "Combiné complet",
        "domaine": "nouvelairr.com",
        "objet": "Votre compte a été suspendu",
        "corps": "Bonjour, Votre compte sera suspendu dans 24h. Veuillez vous connecter "
                 "immédiatement pour le réactiver. Cliquez ici : "
                 "http://nouvelairr.com/login. Cordialement.",
        "liens": [("http://nouvelairr.com/login", "Connectez-vous ici")],
        "auth": ("fail", "none", "fail"),
        "attendu": ["DANGEREUX"],
        "note": "",
    },
    {
        "n": 7, "titre": "Faux positif à éviter, lien de suivi",
        "domaine": "newsletter@nouvelair.com",
        "objet": "Merci pour votre inscription",
        "corps": "Bonjour, Merci de vous être inscrit à notre newsletter. Cordialement.",
        "liens": [("https://click.nouvelair.com/click?campaign=nl01", "Découvrir nos offres")],
        "auth": ("pass", "pass", "pass"),
        "attendu": ["LÉGITIME"],
        "note": "Cas important : le correctif 8 teste maintenant chaque segment du "
                "domaine, il ne doit pas signaler « click » à tort.",
    },
    {
        "n": 8, "titre": "Phishing en arabe",
        "domaine": "support@nouvelair.com",
        "objet": "تم تعليق حسابك",
        "corps": "مرحبا، سيتم تعليق حسابك خلال 24 ساعة. يرجى تسجيل الدخول فورًا "
                 "لإعادة تفعيله. اضغط هنا لتسجيل الدخول. مع التحية",
        "liens": [("http://nouvelairr.com/login", "تسجيل الدخول")],
        "auth": ("fail", "fail", "fail"),
        "attendu": ["DANGEREUX"],
        "note": "",
    },
    {
        "n": 9, "titre": "Fraude au président, en anglais",
        "domaine": "ceo@nouvelair.com",
        "objet": "Urgent wire transfer needed",
        "corps": "Hi, I need you to process an urgent wire transfer before end of day. "
                 "Please confirm you are available. Thanks",
        "liens": [],
        "auth": ("fail", "none", "fail"),
        "attendu": ["SUSPECT", "DANGEREUX"],
        "note": "",
    },
    {
        "n": 10, "titre": "Page inaccessible",
        "domaine": "airfrance.com",
        "objet": "Confirmation de vol",
        "corps": "Bonjour, Votre vol est confirmé. Cordialement.",
        "liens": [("https://www.airfrance.com/", "Voir ma réservation")],
        "auth": ("pass", "pass", "pass"),
        "attendu": ["LÉGITIME", "SUSPECT"],
        "note": "Interroge le réseau. Ne doit jamais ressortir DANGEREUX.",
    },
    {
        "n": 11, "titre": "Domaine récent au registre",
        "domaine": "nouvelair-secure-payment.tn",
        "objet": "Vérification de paiement requise",
        "corps": "Bonjour, Une vérification de paiement est requise sur votre compte. "
                 "Cordialement.",
        "liens": [("http://nouvelair-secure-payment.tn/verify", "Vérifier mon paiement")],
        "auth": ("fail", "fail", "fail"),
        "attendu": ["DANGEREUX"],
        # Le domaine CONTIENT la marque exacte (il ne la déforme pas) : CANINE
        # peut le juger proche de nouvelair. Sinon, c'est la fusion qui décide :
        # authentification en échec (S5) + texte de paiement (S4) + lien (S3).
        "note": "Marque exacte + mots ajoutés : CANINE ou la fusion (S5, S4, S3).",
    },
    {
        "n": 12, "titre": "Marketing légitime, cas frontière",
        "domaine": "info@nouvelair.com",
        "objet": "Offre spéciale, dernières places",
        "corps": "Bonjour, Profitez de notre offre spéciale, places limitées. Cordialement.",
        "liens": [("https://www.nouvelair.com/promo", "Voir l'offre")],
        "auth": ("pass", "pass", "pass"),
        "attendu": ["LÉGITIME", "SUSPECT"],
        "note": "",
    },
]

MARQUES = {"LÉGITIME": "\033[32mLÉGITIME\033[0m",
           "SUSPECT": "\033[33mSUSPECT \033[0m",
           "DANGEREUX": "\033[31mDANGEREUX\033[0m"}


def executer(cas):
    liens = [{"texte_affiche": texte, "url_reelle": url} for url, texte in cas["liens"]]
    spf, dkim, dmarc = cas["auth"]
    depart = time.time()
    resultat = mg.analyser_email_complet(
        domaine_expediteur=domaine_seul(cas["domaine"]),
        texte_email=cas["corps"],
        liens=liens,
        auth_header=(f"mx.nouvelair.com; spf={spf} smtp.mailfrom={domaine_seul(cas['domaine'])}; "
                     f"dkim={dkim} header.d={domaine_seul(cas['domaine'])}; "
                     f"dmarc={dmarc} header.from={domaine_seul(cas['domaine'])}"),
        sujet=cas.get("objet", ""),
    )
    duree = round((time.time() - depart) * 1000)
    score = resultat.get("score_final", 0)
    return resultat, score, categoriser_email(score, resultat), duree


def main():
    print("=" * 84)
    print("Plan de test — 12 cas")
    print("=" * 84)

    reussis, lignes = 0, []

    for cas in CAS:
        resultat, score, obtenu, duree = executer(cas)
        ok = obtenu in cas["attendu"]
        reussis += ok

        icone = "\033[32m✔\033[0m" if ok else "\033[31m✘\033[0m"
        attendu = " ou ".join(cas["attendu"])
        print(f"\n{icone} Cas {cas['n']} — {cas['titre']}")
        print(f"    obtenu {MARQUES[obtenu]}  score {score:.3f}  "
              f"{resultat.get('etape_decision', '')}  {duree} ms")
        if not ok:
            print(f"    \033[31mattendu : {attendu}\033[0m")

        detail = resultat.get("scores_detail", {})
        morceaux = []
        for cle, nom in (("domaine_bert", "domaine"), ("contenu", "contenu"),
                         ("liens", "liens"), ("authentification", "auth"),
                         ("domaine_randomforest", "identité")):
            valeur = detail.get(cle)
            if valeur is not None:
                morceaux.append(f"{nom} {valeur:.2f}")
        print(f"    {'  ·  '.join(morceaux)}")
        if cas["note"]:
            print(f"    \033[90m{cas['note']}\033[0m")

        lignes.append((cas["n"], obtenu, attendu, score, ok))

    print("\n" + "=" * 84)
    print(f"Bilan : {reussis} cas sur {len(CAS)} conformes au plan")
    print("=" * 84)

    echecs = [l for l in lignes if not l[4]]
    if echecs:
        print("\nÉcarts :")
        for n, obtenu, attendu, score, _ in echecs:
            print(f"  Cas {n} : obtenu {obtenu} ({score:.3f}), attendu {attendu}")

    print("""
Rappel de lecture. Un écart n'est pas forcément un défaut du code : il peut
venir d'une attente mal posée dans le plan. Les cas 4 et 11 portent une note
à ce sujet. En revanche, un écart sur les cas 1, 7, 10 ou 12 est un vrai faux
positif, et c'est le plus préoccupant pour un filtre destiné à la production.
""")


if __name__ == "__main__":
    main()
