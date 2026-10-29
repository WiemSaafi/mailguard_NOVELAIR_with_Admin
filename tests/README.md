# Banc d'essai MailGuard (5 signaux + fusion)

## Lancement

Depuis la racine du projet :

    python tests/test_all.py      # logique de l'application + moteur réel
    python tests/test_pages.py    # rendu réel de toutes les pages Streamlit
    python tests/test_auth.py     # comptes, mots de passe, préférences
    python tests/cas_de_test.py   # plan de test : 12 messages, attendu vs obtenu

## Ce qui est testé

- **Partie A de test_all** (sans modèle) : seuils de la fusion (0,825 / 0,928),
  migration des anciens seuils 0,25 / 0,50, catégories, respect d'une décision
  prise par une liste ou une règle sûre, explications signal par signal.
- **Partie B de test_all** (avec le dossier `modeles_mailguard/`) : la cascade
  sur des cas sûrs — usurpation de nouvelair.com, typosquat, liste noire,
  partenaire authentifié, liste blanche non prouvée.

## stubs.py

Les tests utilisent les vrais modèles. `stubs.py` pose seulement
`MAILGUARD_INTERNET=0` : le signal 2 (RDAP, crt.sh) devient muet, donc les
résultats sont reproductibles hors ligne.

`MAILGUARD_FAUX_E5=1` remplace l'encodeur e5 par un vecteur aléatoire, pour
vérifier que les pages s'affichent sur une machine sans ce modèle. Le signal 4
n'a alors aucun sens : ne jamais l'utiliser pour mesurer la qualité.
