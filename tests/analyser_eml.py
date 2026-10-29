"""
tests/analyser_eml.py — mesure MailGuard sur des mails de test construits (fictifs, .eml).

Ces messages vérifient la logique de décision ; les performances des modèles
sont celles mesurées sur les jeux de test des notebooks.

Ranger les mails dans :
    tests/eml/legitimes/*.eml
    tests/eml/phishing/*.eml
Lancement :
    .\.venv\Scripts\python.exe tests\analyser_eml.py

Affiche seulement le résultat (jamais le contenu des mails), puis :
faux positifs (légitimes accusés) et faux négatifs (phishing ratés).
"""
import email
import glob
import os
import sys
from email import policy

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
import stubs  # noqa: F401,E402  (MAILGUARD_INTERNET=0 par défaut ; mettre 1 pour interroger RDAP)

import mailguard_core as mg  # noqa: E402


LIMITES_CONNUES = {
    "P05_fraude_president.eml": (
        "fraude au président : compte Gmail authentifié, aucun lien, "
        "seuls le texte et le Reply-To sont suspects ; score juste sous le seuil suspect"
    ),
}


def regle(r):
    e = r.get("etape_decision", "")
    if e.startswith("0."):
        return "liste"
    if "liste noire" in " ".join(r.get("raisons", [])) and e.startswith("1."):
        return "R1 lien liste noire"
    if "confiance" in e:
        return "R2 confiance + lien"
    if "imite une marque" in e:
        return "R3 lien imite marque"
    if e.startswith("1."):
        return "S5 veto / S1 expéditeur"
    return "fusion"


def main():
    lignes, fp, fn = [], [], []
    for attendu, dossier in (("LÉGITIME", "legitimes"), ("PHISHING", "phishing")):
        fichiers = sorted(glob.glob(os.path.join(ICI, "eml", dossier, "*.eml")))
        for f in fichiers:
            with open(f, "rb") as fh:
                msg = email.message_from_bytes(fh.read(), policy=policy.compat32)
            r = mg.analyser_email_complet("", message=msg)
            cat = r["categorie"]
            ok = (cat == "LÉGITIME") if attendu == "LÉGITIME" else (cat != "LÉGITIME")
            nom = os.path.basename(f)
            lignes.append((nom, attendu, cat, r.get("etape_decision", ""), r.get("score_fusion", r["score_final"]),
                           regle(r), ok, r.get("raisons", [])[:2]))
            if not ok:
                (fp if attendu == "LÉGITIME" else fn).append(nom)

    if not lignes:
        print("Aucun .eml trouvé dans tests/eml/legitimes ni tests/eml/phishing.")
        return
    print(f"\n{'fichier':38s} {'attendu':9s} {'obtenu':11s} {'fusion':>7s}  règle")
    print("-" * 102)
    for nom, att, cat, etape, sf, rg, ok, rs in lignes:
        print(f"{'✔' if ok else '✘'} {nom[:36]:36s} {att:9s} {cat:11s} {sf:7.4f}  {rg}")
        if not ok:
            print(f"      étape : {etape} · raisons : {' | '.join(rs) or '—'}")
    nl = sum(1 for l in lignes if l[1] == "LÉGITIME")
    nph = len(lignes) - nl
    tp = sum(1 for l in lignes if l[1] == "PHISHING" and l[6])
    classes_non_legitimes = sum(1 for l in lignes if l[2] != "LÉGITIME")
    precision = (tp / classes_non_legitimes) if classes_non_legitimes > 0 else 0.0
    rappel = (tp / nph) if nph > 0 else 0.0

    print("\nBilan (mails de test construits, fictifs)")
    print(f"  légitimes : {nl}, faux positifs : {len(fp)}" + (f"  → {', '.join(fp)}" if fp else ""))
    print(f"  phishing  : {nph}, faux négatifs : {len(fn)}" + (f"  → {', '.join(fn)}" if fn else ""))
    print(f"  conformes : {sum(l[6] for l in lignes)}/{len(lignes)}")
    print(f"  précision : {precision:.1%} ({tp}/{classes_non_legitimes})")
    print(f"  rappel    : {rappel:.1%} ({tp}/{nph})")

    fn_connus = [f for f in fn if f in LIMITES_CONNUES]
    if fn_connus:
        print("\nLimites connues (comptées dans les faux négatifs) :")
        for f in fn_connus:
            print(f"  · {f} : {LIMITES_CONNUES[f]}")


if __name__ == "__main__":
    main()
