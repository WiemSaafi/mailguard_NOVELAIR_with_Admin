"""
verifier_avant_publication.py — contrôle ce qui partirait sur GitHub.

    python tests/verifier_avant_publication.py

À lancer avant le premier `git push`, et après chaque ajout de fichier.
Le script ne modifie rien : il signale.

Trois familles de problèmes sont cherchées.

  1. Les secrets. Un mot de passe d'application, une clé de chiffrement ou
     une base de données publiés une fois restent dans l'historique Git,
     même supprimés au commit suivant.
  2. Les fichiers trop lourds. GitHub refuse tout fichier de plus de 100 Mo,
     et le push échoue sans qu'on comprenne pourquoi.
  3. Les données personnelles. Les analyses contiennent des adresses et des
     objets de messages réels.
"""

import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LIMITE_GITHUB_MO = 100
LIMITE_CONSEILLEE_MO = 25

PROBLEMES = []
AVERTISSEMENTS = []

# Fichiers qui ne doivent jamais partir, avec la raison.
INTERDITS = {
    ".env": "contient vos identifiants et la clé de chiffrement",
    "mailguard.db": "contient les comptes et les mots de passe d'application chiffrés",
    "comptes_utilisateurs.json": "ancien magasin de comptes",
    "historique_analyses.json": "contient des adresses et des objets de messages réels",
    "modeles_mailguard": "modèles privés de Nouvelair (dont un entraîné sur des mails réels) : jamais publiés",
}

# Motifs de secrets trouvés en clair dans un fichier destiné au dépôt.
MOTIFS_SECRETS = [
    (re.compile(r"GMAIL_APP_PASSWORD\s*=\s*[A-Za-z]{16}"), "mot de passe d'application Gmail"),
    (re.compile(r"MAILGUARD_SECRET_KEY\s*=\s*\S{20,}"), "clé de chiffrement"),
    (re.compile(r"client_secret\s*=\s*['\"][A-Za-z0-9~._-]{20,}"), "secret client Azure"),
    (re.compile(r"['\"][A-Za-z0-9+/]{40,}={0,2}['\"]\s*#\s*(?i:secret|token)"), "jeton"),
]

EXTENSIONS_TEXTE = {".py", ".md", ".json", ".toml", ".txt", ".cfg", ".ini", ".yml", ".yaml"}


def lire_gitignore():
    chemin = os.path.join(BASE_DIR, ".gitignore")
    if not os.path.exists(chemin):
        PROBLEMES.append("Aucun fichier .gitignore. Tout partirait sur GitHub.")
        return []
    with open(chemin, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def couvert_par_gitignore(nom, regles):
    """Approximation volontairement simple : on vérifie le nom, l'extension
    et le dossier parent. Git est plus subtil, mais cela suffit à repérer un
    oubli évident."""
    for regle in regles:
        regle = regle.rstrip("/")
        if regle.startswith("!"):
            continue
        if regle == nom or regle == os.path.basename(nom):
            return True
        if regle.startswith("*") and nom.endswith(regle[1:]):
            return True
        if regle and (nom.startswith(regle + "/") or f"/{regle}/" in f"/{nom}"):
            return True
    return False


def main():
    print("=" * 72)
    print("Vérification avant publication sur GitHub")
    print("=" * 72)

    regles = lire_gitignore()
    print(f"\n.gitignore : {len(regles)} règles actives")

    # ── 1. Fichiers interdits ───────────────────────────────────────────
    print("\n1. Fichiers sensibles")
    for nom, raison in INTERDITS.items():
        chemin = os.path.join(BASE_DIR, nom)
        existe = os.path.exists(chemin)
        protege = couvert_par_gitignore(nom, regles)
        if not existe:
            print(f"   ·  {nom} : absent")
        elif protege:
            print(f"   ok {nom} : présent mais ignoré par Git")
        else:
            PROBLEMES.append(f"{nom} partirait sur GitHub ({raison})")
            print(f"   NON {nom} : NON IGNORÉ — {raison}")

    dossier_historiques = os.path.join(BASE_DIR, "historiques")
    if os.path.isdir(dossier_historiques) and not couvert_par_gitignore("historiques", regles):
        PROBLEMES.append("le dossier historiques/ partirait sur GitHub")

    # ── 2. Taille des fichiers ──────────────────────────────────────────
    print("\n2. Fichiers volumineux")
    trouve = False
    for racine, dossiers, fichiers in os.walk(BASE_DIR):
        dossiers[:] = [d for d in dossiers
                       if d not in {".git", "__pycache__", ".venv", "venv"}]
        for fichier in fichiers:
            chemin = os.path.join(racine, fichier)
            relatif = os.path.relpath(chemin, BASE_DIR).replace("\\", "/")
            try:
                taille_mo = os.path.getsize(chemin) / 1048576
            except OSError:
                continue
            if taille_mo < LIMITE_CONSEILLEE_MO:
                continue
            trouve = True
            protege = couvert_par_gitignore(relatif, regles)
            etat = "ignoré par Git" if protege else "SERAIT PUBLIÉ"
            print(f"   {taille_mo:7.1f} Mo  {relatif}  ({etat})")
            if not protege:
                if taille_mo >= LIMITE_GITHUB_MO:
                    PROBLEMES.append(
                        f"{relatif} fait {taille_mo:.0f} Mo : GitHub refusera le push "
                        f"(limite de {LIMITE_GITHUB_MO} Mo par fichier)")
                else:
                    AVERTISSEMENTS.append(
                        f"{relatif} fait {taille_mo:.0f} Mo : lourd pour un dépôt")
    if not trouve:
        print(f"   aucun fichier au-dessus de {LIMITE_CONSEILLEE_MO} Mo")

    # ── 3. Secrets en clair dans les fichiers publiés ───────────────────
    print("\n3. Secrets en clair dans les fichiers destinés au dépôt")
    suspects = 0
    for racine, dossiers, fichiers in os.walk(BASE_DIR):
        dossiers[:] = [d for d in dossiers
                       if d not in {".git", "__pycache__", ".venv", "venv"}]
        for fichier in fichiers:
            if os.path.splitext(fichier)[1] not in EXTENSIONS_TEXTE:
                continue
            relatif = os.path.relpath(os.path.join(racine, fichier),
                                      BASE_DIR).replace("\\", "/")
            if couvert_par_gitignore(relatif, regles) or relatif.endswith(".env.example"):
                continue
            try:
                with open(os.path.join(racine, fichier), encoding="utf-8") as f:
                    contenu = f.read()
            except (UnicodeDecodeError, OSError):
                continue
            for motif, libelle in MOTIFS_SECRETS:
                if motif.search(contenu):
                    suspects += 1
                    PROBLEMES.append(f"{relatif} semble contenir un {libelle}")
                    print(f"   NON {relatif} : {libelle}")
    if not suspects:
        print("   aucun secret détecté")

    # ── 4. Fichiers attendus ────────────────────────────────────────────
    print("\n4. Fichiers attendus dans le dépôt")
    for nom, role in (("README.md", "mode d'emploi"),
                      (".env.example", "modèle de configuration"),
                      ("requirements.txt", "dépendances"),
                      ("MODIFICATIONS.md", "journal des modifications")):
        present = os.path.exists(os.path.join(BASE_DIR, nom))
        print(f"   {'ok ' if present else 'NON'} {nom} ({role})")
        if not present:
            AVERTISSEMENTS.append(f"{nom} manquant : {role}")

    # ── Bilan ───────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    if PROBLEMES:
        print(f"{len(PROBLEMES)} problème(s) bloquant(s)")
        for p in PROBLEMES:
            print(f"   - {p}")
    else:
        print("Aucun problème bloquant.")
    if AVERTISSEMENTS:
        print(f"\n{len(AVERTISSEMENTS)} avertissement(s)")
        for a in AVERTISSEMENTS:
            print(f"   - {a}")
    print("=" * 72)

    if PROBLEMES:
        print("\nCorrigez avant de publier. Un secret poussé une fois reste dans")
        print("l'historique Git, même supprimé au commit suivant : il faudrait")
        print("réécrire l'historique et révoquer le secret.")
    sys.exit(1 if PROBLEMES else 0)


if __name__ == "__main__":
    main()
