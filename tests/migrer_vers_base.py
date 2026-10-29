"""
migrer_vers_base.py — importe les anciens fichiers JSON dans la base.

    python tests/migrer_vers_base.py            # aperçu, sans rien écrire
    python tests/migrer_vers_base.py --appliquer

Sont repris, s'ils existent encore :

  - comptes_utilisateurs.json  -> tables utilisateurs, preferences,
                                  identifiants_gmail
  - historique_analyses.json   -> tables analyses et scores_signaux, sans
                                  rattachement à un compte
  - historiques/<id>.json      -> tables analyses et scores_signaux, rattachées
                                  au compte correspondant

Le script est idempotent : relancé, il ne crée pas de doublons. Les fichiers
d'origine ne sont ni modifiés ni supprimés ; à vous de les archiver une fois la
migration vérifiée.
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.database import (  # noqa: E402
    Analyse, IdentifiantGmail, Preference, ScoreSignal, Utilisateur, session,
)
from services.history_service import SIGNAUX  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPTES_JSON = os.path.join(BASE_DIR, "comptes_utilisateurs.json")
HISTORIQUE_JSON = os.path.join(BASE_DIR, "historique_analyses.json")
DOSSIER_HISTORIQUES = os.path.join(BASE_DIR, "historiques")

APPLIQUER = "--appliquer" in sys.argv


def lire(chemin, defaut):
    if not os.path.exists(chemin):
        return defaut
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  fichier illisible, ignoré : {chemin} ({exc})")
        return defaut


def horodatage(valeur):
    try:
        return datetime.fromisoformat(str(valeur))
    except (TypeError, ValueError):
        return datetime.now()


def importer_analyses(s, entrees, utilisateur_id, origine):
    """Renvoie (importees, ignorees). Le doublon se reconnait au couple
    horodatage + domaine expediteur pour un meme compte."""
    importees = ignorees = 0

    for entree in entrees:
        if not isinstance(entree, dict):
            continue
        moment = horodatage(entree.get("timestamp"))
        domaine = entree.get("domaine_expediteur") or ""

        existe = (s.query(Analyse)
                  .filter(Analyse.utilisateur_id == utilisateur_id,
                          Analyse.horodatage == moment,
                          Analyse.domaine_expediteur == domaine)
                  .first())
        if existe:
            ignorees += 1
            continue

        score = entree.get("score_final", 0) or 0
        categorie = entree.get("categorie")
        if not categorie:
            from services.quarantine_service import categoriser_email
            categorie = categoriser_email(score)

        analyse = Analyse(
            utilisateur_id=utilisateur_id,
            horodatage=moment,
            domaine_expediteur=domaine,
            sujet=(entree.get("sujet") or "")[:500],
            texte_apercu=(entree.get("texte_apercu") or "")[:300],
            nb_liens=entree.get("nb_liens", 0) or 0,
            score_final=float(score),
            categorie=categorie,
            etage=entree.get("etage", 1) or 1,
            signaux_calcules=entree.get("signaux_calcules", 4) or 4,
            duree_analyse_ms=float(entree.get("duree_analyse_ms", 0) or 0),
            action_appliquee=entree.get("action_appliquee") or "aucune",
            source=entree.get("source") or origine,
            uid_imap=str(entree.get("uid") or ""),
            details_json=json.dumps(entree.get("details", {}),
                                    ensure_ascii=False, default=str),
            explication=entree.get("explication") or "",
        )
        s.add(analyse)
        s.flush()

        scores = entree.get("scores_detail") or {}
        if isinstance(scores, dict):
            for signal in SIGNAUX:
                if signal in scores:
                    valeur = scores[signal]
                    s.add(ScoreSignal(
                        analyse_id=analyse.id, signal=signal,
                        valeur=None if valeur is None else float(valeur),
                    ))
        importees += 1

    return importees, ignorees


def main():
    print("=" * 72)
    print("Migration des fichiers JSON vers la base de données")
    print("=" * 72)
    if not APPLIQUER:
        print("\nMode aperçu : rien ne sera écrit. Ajoutez --appliquer pour migrer.\n")

    comptes = lire(COMPTES_JSON, {})
    historique_global = lire(HISTORIQUE_JSON, [])
    fichiers_utilisateurs = []
    if os.path.isdir(DOSSIER_HISTORIQUES):
        fichiers_utilisateurs = [f for f in sorted(os.listdir(DOSSIER_HISTORIQUES))
                                 if f.endswith(".json")]

    print(f"comptes_utilisateurs.json : {len(comptes)} compte(s)")
    print(f"historique_analyses.json  : {len(historique_global)} analyse(s)")
    print(f"historiques/              : {len(fichiers_utilisateurs)} fichier(s)")

    if not comptes and not historique_global and not fichiers_utilisateurs:
        print("\nRien à migrer : aucun ancien fichier trouvé.")
        return

    with session() as s:
        comptes_crees = comptes_existants = 0
        correspondance = {}

        for email, donnees in comptes.items():
            existant = s.query(Utilisateur).filter_by(email=email).first()
            if existant:
                correspondance[donnees.get("identifiant")] = existant.id
                comptes_existants += 1
                continue

            utilisateur = Utilisateur(
                email=email,
                identifiant=donnees.get("identifiant") or "",
                nom=donnees.get("nom") or email.split("@")[0],
                empreinte=donnees.get("empreinte") or "",
                sel=donnees.get("sel") or "",
                cree_le=horodatage(donnees.get("cree_le")),
                derniere_connexion=(horodatage(donnees["derniere_connexion"])
                                    if donnees.get("derniere_connexion") else None),
            )
            utilisateur.preferences = Preference(
                seuil_suspect=donnees.get("seuil_suspect", 0.825),
                seuil_dangereux=donnees.get("seuil_dangereux", 0.928),
                action_config=donnees.get("action_config", "quarantaine"),
            )
            utilisateur.gmail = IdentifiantGmail(
                adresse=donnees.get("gmail_address", ""),
                mot_de_passe_chiffre=donnees.get("gmail_password_chiffre", ""),
            )
            s.add(utilisateur)
            s.flush()
            correspondance[utilisateur.identifiant] = utilisateur.id
            comptes_crees += 1

        print(f"\nComptes : {comptes_crees} a creer, {comptes_existants} deja presents")

        total_importees = total_ignorees = 0
        if historique_global:
            i, j = importer_analyses(s, historique_global, None, "manuel")
            total_importees += i
            total_ignorees += j
            print(f"Historique general : {i} importee(s), {j} deja presente(s)")

        for fichier in fichiers_utilisateurs:
            identifiant = fichier[:-5]
            utilisateur_id = correspondance.get(identifiant)
            if utilisateur_id is None:
                trouve = s.query(Utilisateur).filter_by(identifiant=identifiant).first()
                utilisateur_id = trouve.id if trouve else None
            if utilisateur_id is None:
                print(f"  {fichier} : aucun compte correspondant, ignore")
                continue
            entrees = lire(os.path.join(DOSSIER_HISTORIQUES, fichier), [])
            i, j = importer_analyses(s, entrees, utilisateur_id, "manuel")
            total_importees += i
            total_ignorees += j
            print(f"  {fichier} : {i} importee(s), {j} deja presente(s)")

        print(f"\nTotal : {total_importees} analyse(s) a importer, "
              f"{total_ignorees} ignoree(s)")

        if APPLIQUER:
            s.commit()
            print("\nMigration appliquee.")
            print("Les fichiers JSON d'origine sont intacts : archivez-les une "
                  "fois la verification faite.")
        else:
            s.rollback()
            print("\nAucune ecriture. Relancez avec --appliquer pour migrer.")


if __name__ == "__main__":
    main()
