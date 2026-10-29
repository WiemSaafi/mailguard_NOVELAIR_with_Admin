"""
verifier_logique.py — Vérification bout en bout du moteur MailGuard.

    .\.venv\Scripts\python.exe tests\verifier_logique.py

Ce script appelle mg.analyser_email_complet sur 12+ cas et vérifie que :
    - la catégorie correspond à l'attendu,
    - l'étape de décision est correcte,
    - le score_final est cohérent avec l'étape (0,0 ou 1,0 pour les étapes 0/1),
    - les raisons ne sont pas vides quand la catégorie n'est pas LÉGITIME,
    - scores_detail contient les 5 clés attendues (sauf étape 0),
    - categoriser_email(score_final, resultat) donne la même catégorie.

Aucun modèle n'est réentraîné, aucun fichier modifié. MAILGUARD_INTERNET=0
pour des résultats reproductibles.
"""

import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["MAILGUARD_INTERNET"] = "0"    # reproductible, pas de réseau

# Forcer l'encodage UTF-8 pour la console Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import stubs  # noqa: F401,E402

import mailguard_core as mg  # noqa: E402
from services.quarantine_service import categoriser_email  # noqa: E402


# ─────────────────────────────────────────────────────────────────────
# Helper : construire un en-tête Authentication-Results réaliste
# ─────────────────────────────────────────────────────────────────────

def auth_header(dom, spf="pass", dkim="pass", dmarc="pass", mailfrom=None):
    """En-tête avec alignement : mailfrom = header.d = header.from = dom
    (sauf si mailfrom est explicitement différent)."""
    mf = mailfrom or dom
    return (f"mx.nouvelair.com; spf={spf} smtp.mailfrom={mf}; "
            f"dkim={dkim} header.d={dom}; dmarc={dmarc} header.from={dom}")


# ─────────────────────────────────────────────────────────────────────
# Définition des cas
# ─────────────────────────────────────────────────────────────────────

CAS = [
    # ── (a) nouvelair.com authentifié, texte normal → LÉGITIME étape 0
    {
        "id": "a", "titre": "nouvelair.com, tout pass, texte normal",
        "args": {
            "domaine_expediteur": "info@nouvelair.com",
            "texte_email": "Bonjour, votre réservation NV456 est confirmée. Bon voyage.",
            "liens": [],
            "auth_header": auth_header("nouvelair.com"),
            "sujet": "Confirmation de réservation",
        },
        "attendu_categorie": ["LÉGITIME"],
        "attendu_etape_prefixe": "0.",
        "note": "Domaine officiel prouvé par DKIM aligné → liste blanche étape 0.",
    },
    # ── (b) nouvelair.com, DMARC fail, mailfrom différent → FRAUDULEUX étape 1 (veto S5)
    {
        "id": "b", "titre": "nouvelair.com, usurpation (DMARC fail, mailfrom étranger)",
        "args": {
            "domaine_expediteur": "rh@nouvelair.com",
            "texte_email": "Merci de mettre à jour votre mot de passe en cliquant ici.",
            "liens": [],
            "auth_header": auth_header("nouvelair.com", "fail", "none", "fail", "mail-out.ru"),
            "sujet": "Mise à jour du mot de passe",
        },
        "attendu_categorie": ["FRAUDULEUX"],
        "attendu_etape_prefixe": "1.",
        "note": "Veto S5 : DMARC échoue sur un domaine Nouvelair → règle sûre.",
    },
    # ── (c) n0uvelair.com (typosquat pas dans la liste noire), tout pass → FRAUDULEUX étape 1 (S1 CANINE)
    {
        "id": "c", "titre": "n0uvelair.com (typosquat), tout pass → S1 CANINE",
        "args": {
            "domaine_expediteur": "contact@n0uvelair.com",
            "texte_email": "Découvrez nos nouvelles destinations pour cet été. Cordialement.",
            "liens": [],
            "auth_header": auth_header("n0uvelair.com"),
            "sujet": "Newsletter",
        },
        "attendu_categorie": ["FRAUDULEUX"],
        "attendu_etape_prefixe": "1.",
        "note": "n0uvelair.com n'est pas dans la liste noire mais CANINE détecte l'imitation.",
    },
    # ── (d) nouve1air.com (liste noire) → FRAUDULEUX étape 0
    {
        "id": "d", "titre": "nouve1air.com (liste noire)",
        "args": {
            "domaine_expediteur": "x@nouve1air.com",
            "texte_email": "Bonjour",
            "liens": [],
            "auth_header": "",
            "sujet": "",
        },
        "attendu_categorie": ["FRAUDULEUX"],
        "attendu_etape_prefixe": "0.",
        "note": "nouve1air.com est dans la liste noire → étape 0.",
    },
    # ── (e) biat.com.tn (liste blanche), tout pass → LÉGITIME étape 0
    {
        "id": "e", "titre": "biat.com.tn (liste blanche), tout pass",
        "args": {
            "domaine_expediteur": "info@biat.com.tn",
            "texte_email": "Bonjour, veuillez trouver ci-joint le relevé du mois.",
            "liens": [],
            "auth_header": auth_header("biat.com.tn"),
            "sujet": "Relevé mensuel",
        },
        "attendu_categorie": ["LÉGITIME"],
        "attendu_etape_prefixe": "0.",
        "note": "biat.com.tn est dans la liste blanche + DKIM aligné → prouvé.",
    },
    # ── (f) biat.com.tn mais DKIM/SPF en échec → NE DOIT PAS passer par la liste blanche
    {
        "id": "f", "titre": "biat.com.tn mais auth en échec → pas de liste blanche",
        "args": {
            "domaine_expediteur": "info@biat.com.tn",
            "texte_email": "Bonjour, veuillez trouver ci-joint le relevé du mois.",
            "liens": [],
            "auth_header": auth_header("biat.com.tn", "fail", "none", "fail", "x.ru"),
            "sujet": "Relevé mensuel",
        },
        "attendu_categorie": None,   # on vérifie juste que ce n'est PAS étape 0 liste blanche
        "attendu_etape_prefixe": None,  # pas d'étape imposée, juste pas la liste blanche
        "verif_speciale": "pas_liste_blanche",
        "note": "Le domaine est dans la liste blanche mais pas prouvé → passe au score.",
    },
    # ── (g) domaine inconnu, texte phishing, lien suspect, auth en échec
    {
        "id": "g", "titre": "domaine inconnu, phishing complet",
        "args": {
            "domaine_expediteur": "security@verify-account-now.top",
            "texte_email": ("Votre compte a été suspendu suite à une activité suspecte. "
                            "Vérifiez votre mot de passe sous 24h sinon votre accès sera bloqué. "
                            "Cliquez sur le lien ci-dessous pour rétablir votre accès."),
            "liens": [{"texte_affiche": "Vérifier mon compte", "url_reelle": "http://secure-pay-verif.top/login/verify.php"}],
            "auth_header": auth_header("verify-account-now.top", "fail", "fail", "fail"),
            "sujet": "Votre compte est suspendu",
        },
        "attendu_categorie": ["SUSPECT", "FRAUDULEUX"],
        "attendu_etape_prefixe": "2.",
        "note": "Tous les signaux sont élevés → la fusion doit dépasser le seuil suspect.",
    },
    # ── (h) google.com authentifié, alerte de sécurité banale → LÉGITIME
    {
        "id": "h", "titre": "google.com authentifié, alerte banale, lien myaccount.google.com",
        "args": {
            "domaine_expediteur": "no-reply@google.com",
            "texte_email": ("Bonjour, une nouvelle connexion a été détectée sur votre compte Google "
                            "depuis un appareil Windows. Si c'était vous, aucune action n'est nécessaire."),
            "liens": [{"texte_affiche": "Vérifier l'activité", "url_reelle": "https://myaccount.google.com/notifications"}],
            "auth_header": auth_header("google.com"),
            "sujet": "Alerte de sécurité",
        },
        "attendu_categorie": ["LÉGITIME"],
        "attendu_etape_prefixe": "2.",
        "note": "google.com n'est pas dans la liste blanche mais auth ok, contenu banal.",
    },
    # ── (i) texte de moins de 30 caractères → S4 ignoré
    {
        "id": "i", "titre": "texte court (< 30 car) → S4 ignoré",
        "args": {
            "domaine_expediteur": "test@example.org",
            "texte_email": "Salut",
            "liens": [],
            "auth_header": auth_header("example.org"),
            "sujet": "",
        },
        "attendu_categorie": ["LÉGITIME"],
        "attendu_etape_prefixe": "2.",
        "verif_speciale": "s4_ignore",
        "note": "Texte trop court : S4 doit valoir 0.",
    },
    # ── (j) message sans lien ni en-tête d'authentification → pas d'erreur
    {
        "id": "j", "titre": "sans lien ni auth → S5 neutre, pas d'erreur",
        "args": {
            "domaine_expediteur": "test@example.org",
            "texte_email": "Ceci est un message de test sans lien et sans en-tête d'authentification pour vérifier la robustesse.",
            "liens": [],
            "auth_header": "",
            "sujet": "Message de test",
        },
        "attendu_categorie": ["LÉGITIME"],
        "attendu_etape_prefixe": "2.",
        "verif_speciale": "s5_neutre",
        "note": "Pas d'en-tête Authentication-Results → S5 doit être neutre (score 0).",
    },
    # ── (k1) email en arabe (phishing) → S4 élevé
    {
        "id": "k_arabe", "titre": "phishing en arabe → S4 élevé",
        "args": {
            "domaine_expediteur": "support@verify-now.top",
            "texte_email": ("تم تعليق حسابك بسبب نشاط مشبوه. يرجى تسجيل الدخول فورًا "
                            "لإعادة تفعيل حسابك وتأكيد معلوماتك البنكية. اضغط هنا الآن."),
            "liens": [],
            "auth_header": auth_header("verify-now.top", "fail", "fail", "fail"),
            "sujet": "تم تعليق حسابك",
        },
        "attendu_categorie": ["SUSPECT", "FRAUDULEUX"],
        "attendu_etape_prefixe": "2.",
        "verif_speciale": "s4_eleve",
        "note": "Le modèle e5 est multilingue : le texte arabe de phishing doit donner S4 élevé.",
    },
    # ── (k2) email en anglais (phishing) → S4 élevé
    {
        "id": "k_anglais", "titre": "phishing en anglais → S4 élevé",
        "args": {
            "domaine_expediteur": "security@verify-now.top",
            "texte_email": ("Dear customer, your account has been suspended due to suspicious activity. "
                            "Please verify your identity immediately by clicking the link below. "
                            "Failure to do so within 24 hours will result in permanent account closure."),
            "liens": [],
            "auth_header": auth_header("verify-now.top", "fail", "fail", "fail"),
            "sujet": "Account suspended",
        },
        "attendu_categorie": ["SUSPECT", "FRAUDULEUX"],
        "attendu_etape_prefixe": "2.",
        "verif_speciale": "s4_eleve",
        "note": "Texte anglais de phishing classique → S4 doit être élevé.",
    },
    # ── (m1) nouvelair.com authentifié + lien officiel → LÉGITIME, étape 0
    {
        "id": "m1", "titre": "liste blanche + lien officiel → étape 0",
        "args": {
            "domaine_expediteur": "promo@nouvelair.com",
            "texte_email": "Profitez de nos offres spéciales pour cet été !",
            "liens": [{"texte_affiche": "Voir les offres", "url_reelle": "https://www.nouvelair.com/promo"}],
            "auth_header": auth_header("nouvelair.com"),
            "sujet": "Offre spéciale",
        },
        "attendu_categorie": ["LÉGITIME"],
        "attendu_etape_prefixe": "0.",
        "note": "Lien vers le site officiel → la liste blanche court-circuite normalement.",
    },
    # ── (m2) nouvelair.com authentifié + lien piégé (nouvelairr.com) → pas LÉGITIME (R2)
    {
        "id": "m2", "titre": "liste blanche + lien piégé → SUSPECT ou FRAUDULEUX (R2)",
        "args": {
            "domaine_expediteur": "info@nouvelair.com",
            "texte_email": "Merci de mettre à jour vos informations via le lien ci-dessous. Cordialement.",
            "liens": [{"texte_affiche": "www.nouvelair.com/update", "url_reelle": "http://nouvelairr.com/update"}],
            "auth_header": auth_header("nouvelair.com"),
            "sujet": "Mise à jour",
        },
        "attendu_categorie": ["SUSPECT", "FRAUDULEUX"],
        "attendu_etape_prefixe": "1.",
        "verif_speciale": "raison_lien_dangereux",
        "note": "R1 (liste noire) ou R2 (confiance+lien piégé) : le mail ne doit PAS sortir LÉGITIME.",
    },
    # ── (m3) biat.com.tn authentifié + lien vers domaine de la liste noire → FRAUDULEUX étape 1 (R1)
    {
        "id": "m3", "titre": "biat.com.tn authentifié + lien nouve1air.com → FRAUDULEUX (R1)",
        "args": {
            "domaine_expediteur": "info@biat.com.tn",
            "texte_email": "Bonjour, veuillez trouver ci-joint le relevé du mois.",
            "liens": [{"texte_affiche": "Voir le relevé", "url_reelle": "http://nouve1air.com/phishing"}],
            "auth_header": auth_header("biat.com.tn"),
            "sujet": "Relevé mensuel",
        },
        "attendu_categorie": ["FRAUDULEUX"],
        "attendu_etape_prefixe": "1.",
        "verif_speciale": "raison_lien_dangereux",
        "note": "R1 : nouve1air.com est dans la liste noire → FRAUDULEUX étape 1.",
    },
    # ── (m4) domaine inconnu, auth pass, texte banal + lien vers nouve1air.com → FRAUDULEUX étape 1 (R1)
    {
        "id": "m4", "titre": "domaine inconnu + lien liste noire → FRAUDULEUX (R1)",
        "args": {
            "domaine_expediteur": "contact@entreprise-inconnue.com",
            "texte_email": "Bonjour, veuillez consulter le document ci-joint pour votre information.",
            "liens": [{"texte_affiche": "Document", "url_reelle": "http://nouve1air.com/document.pdf"}],
            "auth_header": auth_header("entreprise-inconnue.com"),
            "sujet": "Document important",
        },
        "attendu_categorie": ["FRAUDULEUX"],
        "attendu_etape_prefixe": "1.",
        "verif_speciale": "raison_lien_dangereux",
        "note": "R1 : tout expéditeur + lien vers liste noire → FRAUDULEUX.",
    },
    # ── (m5) R2 via CANINE : nouvelair.com authentifié + lien nouvelalr.com (hors liste noire)
    {
        "id": "m5", "titre": "R2 : confiance + lien imitation CANINE (hors liste noire) → SUSPECT",
        "args": {
            "domaine_expediteur": "info@nouvelair.com",
            "texte_email": "Bonjour, veuillez consulter les détails de votre réservation.",
            "liens": [{"texte_affiche": "Voir la réservation", "url_reelle": "http://nouvelalr.com/update"}],
            "auth_header": auth_header("nouvelair.com"),
            "sujet": "Détails réservation",
        },
        "attendu_categorie": ["SUSPECT", "FRAUDULEUX"],
        "attendu_etape_prefixe": "1.",
        "verif_speciale": "r2_suspect",
        "note": "R2 : nouvelalr.com HORS liste noire, détecté par CANINE (0.984). Pas R1.",
    },
    # ── (m6) biat.com.tn authentifié + lien biat.com.tn → LÉGITIME étape 0 (R2 ne se déclenche pas)
    {
        "id": "m6", "titre": "biat.com.tn + lien biat.com.tn → LÉGITIME (R2 ne doit PAS se déclencher)",
        "args": {
            "domaine_expediteur": "info@biat.com.tn",
            "texte_email": "Consultez votre relevé mensuel en ligne.",
            "liens": [{"texte_affiche": "Espace client", "url_reelle": "https://www.biat.com.tn/espace-client"}],
            "auth_header": auth_header("biat.com.tn"),
            "sujet": "Relevé mensuel",
        },
        "attendu_categorie": ["LÉGITIME"],
        "attendu_etape_prefixe": "0.",
        "note": "Lien vers le domaine du sender (officiel ou blanche). R2 ne doit PAS se déclencher.",
    },
    # ── (m7) R2 via règle forte IP : nouvelair.com authentifié + lien IP privée
    {
        "id": "m7", "titre": "R2 : confiance + lien IP (règle forte, hors liste noire) → SUSPECT",
        "args": {
            "domaine_expediteur": "info@nouvelair.com",
            "texte_email": "Veuillez vous connecter pour mettre à jour vos informations.",
            "liens": [{"texte_affiche": "Connexion", "url_reelle": "http://192.168.1.10/login"}],
            "auth_header": auth_header("nouvelair.com"),
            "sujet": "Mise à jour",
        },
        "attendu_categorie": ["SUSPECT", "FRAUDULEUX"],
        "attendu_etape_prefixe": "1.",
        "verif_speciale": "r2_suspect",
        "note": "R2 : 192.168.1.10 hors liste noire, détecté par règle forte (adresse IP). Pas R1.",
    },
    # ── (m8) Expéditeur inconnu authentifié + lien imitant une marque protégée
    {
        "id": "m8", "titre": "inconnu authentifié + lien imite marque (CANINE) → SUSPECT minimum",
        "args": {
            "domaine_expediteur": "contact@agence-voyage-exemple.tn",
            "texte_email": "Bonjour, nous vous informons que votre dossier est prêt. Consultez-le ci-dessous.",
            "liens": [{"texte_affiche": "Mon dossier", "url_reelle": "http://nouvelalr.com/update"}],
            "auth_header": auth_header("agence-voyage-exemple.tn"),
            "sujet": "Dossier prêt",
        },
        "attendu_categorie": ["SUSPECT", "FRAUDULEUX"],
        "attendu_etape_prefixe": "1.",
        "note": "R3 : nouvelalr.com imite nouvelair (CANINE 0.984), hors liste noire. Tout expéditeur.",
    },
]


# ─────────────────────────────────────────────────────────────────────
# Exécution et vérifications
# ─────────────────────────────────────────────────────────────────────

CINQ_CLES = {"domaine_bert", "liens", "authentification", "contenu", "domaine_randomforest"}
OK_MARK = "\033[32m✔\033[0m"
KO_MARK = "\033[31m✘\033[0m"


def verifier(cas):
    """Exécute un cas et renvoie (resultat, liste_de_checks)."""
    checks = []
    t0 = time.time()
    r = mg.analyser_email_complet(**cas["args"])
    duree_ms = round((time.time() - t0) * 1000)

    cat = r.get("categorie", "?")
    etape = r.get("etape_decision", "")
    score_final = r.get("score_final", -1)
    score_fusion = r.get("score_fusion", -1)
    raisons = r.get("raisons", [])
    scores_det = r.get("scores_detail", {})

    # ── Vérification 1 : catégorie attendue
    attendu = cas.get("attendu_categorie")
    if attendu is not None:
        ok_cat = cat in attendu
        checks.append(("catégorie", ok_cat,
                        f"obtenu={cat}, attendu={'|'.join(attendu)}"))
    else:
        ok_cat = True
        checks.append(("catégorie", True, f"obtenu={cat} (pas de vérification)"))

    # ── Vérification 2 : étape de décision
    pref = cas.get("attendu_etape_prefixe")
    if pref is not None:
        ok_etape = etape.startswith(pref)
        checks.append(("étape", ok_etape, f"obtenu='{etape}', attendu préfixe='{pref}'"))
    else:
        ok_etape = True
        checks.append(("étape", True, f"obtenu='{etape}' (pas de vérification)"))

    # ── Vérification 3 : cohérence score_final / étape
    if etape.startswith("0.") and "liste noire" in etape:
        ok_score = score_final == 1.0
        checks.append(("score_final=1.0 (liste noire)", ok_score, f"{score_final}"))
    elif etape.startswith("0.") and "liste blanche" in etape:
        ok_score = score_final == 0.0
        checks.append(("score_final=0.0 (liste blanche)", ok_score, f"{score_final}"))
    elif etape.startswith("1."):
        if cat == "FRAUDULEUX":
            ok_score = score_final == 1.0
            checks.append(("score_final=1.0 (règle sûre, frauduleux)", ok_score, f"{score_final}"))
        else:
            seuil = r.get("seuil_suspect", 0.8252)
            ok_score = score_final >= seuil
            checks.append((f"score_final≥{seuil} (règle sûre, suspect)", ok_score, f"{score_final}"))
    elif etape.startswith("2."):
        ok_score = abs(score_final - score_fusion) < 0.001
        checks.append(("score_final≈score_fusion (étape 2)", ok_score,
                        f"final={score_final} fusion={score_fusion}"))
    else:
        ok_score = True

    # ── Vérification 4 : raisons non vides si non LÉGITIME
    if cat != "LÉGITIME":
        ok_raisons = len(raisons) > 0
        checks.append(("raisons non vides", ok_raisons,
                        f"{len(raisons)} raison(s)"))
    else:
        ok_raisons = True
        checks.append(("raisons", True, "LÉGITIME (pas vérifié)"))

    # ── Vérification 5 : scores_detail contient les 5 clés (sauf étape 0)
    if not etape.startswith("0."):
        ok_cles = set(scores_det.keys()) >= CINQ_CLES
        checks.append(("5 clés de signaux", ok_cles,
                        f"clés={set(scores_det.keys())}"))
    else:
        ok_cles = True
        checks.append(("5 clés de signaux", True, "étape 0, pas vérifié"))

    # ── Vérification 6 : categoriser_email(score_final, resultat) == categorie
    cat_verif = categoriser_email(score_final, r)
    # La clé interne est "DANGEREUX" pour "FRAUDULEUX"
    cat_attendu = "DANGEREUX" if cat == "FRAUDULEUX" else cat
    ok_coherence = cat_verif == cat_attendu
    checks.append(("cohérence categoriser_email", ok_coherence,
                    f"categoriser_email={cat_verif}, categorie={cat}"))

    # ── Vérifications spéciales
    vs = cas.get("verif_speciale")
    if vs == "pas_liste_blanche":
        ok_sp = "liste blanche" not in etape
        checks.append(("pas passé par la liste blanche", ok_sp, f"étape='{etape}'"))
    elif vs == "s4_ignore":
        s4 = scores_det.get("contenu", -1)
        ok_sp = s4 == 0.0 or s4 == 0
        checks.append(("S4=0 (texte court)", ok_sp, f"S4={s4}"))
    elif vs == "s5_neutre":
        s5 = scores_det.get("authentification", -1)
        ok_sp = s5 == 0 or s5 == 0.0
        checks.append(("S5=0 (pas d'en-tête auth)", ok_sp, f"S5={s5}"))
    elif vs == "s4_eleve":
        s4 = scores_det.get("contenu", 0)
        ok_sp = s4 is not None and s4 >= 0.3
        checks.append(("S4 ≥ 0.3 (phishing)", ok_sp, f"S4={s4}"))
    elif vs == "raison_lien_dangereux":
        ok_sp = any("lien dangereux" in r or "liste noire" in r for r in raisons)
        checks.append(("raison lien dangereux/liste noire", ok_sp,
                        f"raisons={raisons[:3]}"))
    elif vs == "r2_suspect":
        # R2 : raison contient « lien dangereux »
        ok_r = any("lien dangereux" in r for r in raisons)
        checks.append(("raison « lien dangereux » (R2)", ok_r,
                        f"raisons={raisons[:3]}"))
        # score_final >= SEUIL_SUSPECT
        sf = r.get("score_final", 0)
        seuil = r.get("seuil_suspect", 0.8252)
        ok_sf = sf >= seuil
        checks.append((f"score_final ({sf:.3f}) >= seuil_suspect ({seuil})", ok_sf,
                        f"score_final={sf}"))
        # score_fusion est la vraie valeur (inférieure au seuil suspect, car auth pass + texte banal)
        sfus = r.get("score_fusion", 0)
        ok_fus = sfus < seuil
        checks.append((f"score_fusion ({sfus:.3f}) = vraie valeur fusion (< seuil)", ok_fus,
                        f"score_fusion={sfus}"))

    return r, checks, duree_ms


def main():
    print("=" * 100)
    print("  VÉRIFICATION LOGIQUE — MailGuard (5 signaux + fusion)")
    print("  MAILGUARD_INTERNET=0 (reproductible)")
    print("=" * 100)

    resultats_globaux = []

    for cas in CAS:
        r, checks, duree_ms = verifier(cas)

        all_ok = all(c[1] for c in checks)
        resultats_globaux.append((cas["id"], cas["titre"], all_ok, r, checks, duree_ms))

        icone = OK_MARK if all_ok else KO_MARK
        print(f"\n{icone} Cas {cas['id']} — {cas['titre']}  ({duree_ms} ms)")

        # Détails concis
        cat = r.get("categorie", "?")
        etape = r.get("etape_decision", "")
        sf = r.get("score_final", -1)
        sfus = r.get("score_fusion", -1)
        signaux = r.get("signaux", {})
        raisons = r.get("raisons", [])

        print(f"    catégorie={cat}  étape='{etape}'  score_final={sf:.3f}  score_fusion={sfus:.3f}")
        if signaux:
            print(f"    S1={signaux.get('S1', '?')}  S2={signaux.get('S2', '?')}  "
                  f"S3_chemin={signaux.get('S3_chemin', '?')}  S3_regle={signaux.get('S3_regle', '?')}  "
                  f"S4={signaux.get('S4', '?')}  S5={signaux.get('S5', '?')}")
        if raisons:
            for rai in raisons[:3]:
                print(f"    → {rai}")

        for nom, ok, detail in checks:
            if not ok:
                print(f"    {KO_MARK} {nom} : {detail}")

        if cas.get("note"):
            print(f"    \033[90m{cas['note']}\033[0m")

    # ─── Tableau récapitulatif ───
    print("\n" + "=" * 100)
    print("  TABLEAU RÉCAPITULATIF")
    print("=" * 100)
    print(f"  {'Cas':<12} {'Titre':<55} {'Cat':<12} {'Étape':<35} {'Score':<8} {'OK/KO'}")
    print("  " + "-" * 130)

    nb_ok = 0
    for cas_id, titre, all_ok, r, checks, duree_ms in resultats_globaux:
        cat = r.get("categorie", "?")
        etape = r.get("etape_decision", "")[:32]
        sf = r.get("score_final", -1)
        statut = "\033[32mOK\033[0m" if all_ok else "\033[31mKO\033[0m"
        nb_ok += int(all_ok)
        print(f"  {cas_id:<12} {titre[:53]:<55} {cat:<12} {etape:<35} {sf:<8.3f} {statut}")

    print(f"\n  Bilan : {nb_ok}/{len(resultats_globaux)} cas conformes")

    # ─── Liste des KO avec diagnostic ───
    echecs = [(cas_id, titre, r, checks) for cas_id, titre, all_ok, r, checks, _ in resultats_globaux if not all_ok]
    if echecs:
        print("\n  DÉTAIL DES ÉCARTS :")
        for cas_id, titre, r, checks in echecs:
            print(f"\n  Cas {cas_id} — {titre}")
            for nom, ok, detail in checks:
                if not ok:
                    print(f"    ✘ {nom} : {detail}")
    else:
        print("\n  \033[32mTous les cas sont conformes !\033[0m")

    print()
    sys.exit(0 if not echecs else 1)


if __name__ == "__main__":
    main()
