# MailGuard v8.1 — règles sûres sur les liens

- **Garde-fou liste blanche** : la liste blanche prouvée ne décide plus seule si le message contient un lien dangereux (liste noire, règle forte ou imitation CANINE). Le message poursuit la cascade normale.
- **Règle R1 (lien vers la liste noire)** : tout message contenant un lien dont l'hôte ou le domaine enregistré figure dans la liste noire (`self.noire_dom`) est immédiatement classé **FRAUDULEUX** (étape « 1. règle sûre », score affiché 1,0), quel que soit l'expéditeur.
- **Règle R2 (expéditeur de confiance + lien dangereux)** : si l'expéditeur est en liste blanche prouvée mais qu'un lien est piégé (imitation CANINE ≥ seuil_s1 ou règle forte), la décision est forcée au minimum à **SUSPECT** (étape « 1. règle sûre (expéditeur de confiance, lien dangereux) », score_final ≥ seuil suspect) pour signaler un piratage de compte potentiel.
- **Règle R3 (lien imitant une marque)** : tout lien dont le domaine imite une marque protégée (CANINE ≥ 0,44 sur domaine non officiel) est forcé au minimum à **SUSPECT** (étape « 1. règle sûre (lien imite une marque protégée) »), quel que soit l'expéditeur.
- **Raison des règles sûres** : le modèle de fusion appris possède un coefficient négatif (−0,62) pour le signal « S3 lien imite une marque ». Lorsque l'authentification est parfaite (S5 bas) et le texte anodin (S4 bas), le lien piégé seul ne pouvait pas franchir le seuil de suspicion. Les règles sûres corrigent cette faille sans toucher aux poids appris.
- **Cohérence de l'affichage** : `score_final` affiche `max(score_fusion, SEUIL_SUSPECT)` pour les décisions suspectes de l'étape 1, garantissant la cohérence entre le bandeau, la catégorisation et l'historique, tout en préservant le score réel dans `score_fusion`.
- **Validation** : 155 tests automatisés réussis (26/26 test_all, 71/71 test_auth, 26/26 test_pages, 12/12 cas_de_test, 20/20 verifier_logique).
- **Validation sur mails de test construits (fictifs, .eml)** : 19/20 conformes (12/12 légitimes, 0 faux positif, précision 100,0 %, rappel 87,5 %). Ces messages vérifient la logique de décision ; les performances des modèles sont celles mesurées sur les jeux de test des notebooks.
- **Limite documentée P05** : `P05_fraude_president.eml` (score fusion 0,8250, valeur brute 0,825044 < seuil 0,8252) : compte Gmail authentifié sans lien, seuls le texte et le Reply-To diffèrent. Documenté honnêtement comme faux négatif sans surapprentissage.

---

# MailGuard v8 — nouveaux modèles (5 signaux + fusion apprise)

- **Moteur remplacé.** `mailguard.py` rassemble les modèles finaux :
  S1 CANINE (0,44), S2 Gradient Boosting + règle « < 30 jours » (0,74),
  S3 règles + Gradient Boosting du chemin (0,894), S4 multilingual-e5 +
  régression logistique (0,391), S5 Gradient Boosting sur 17 indices + veto
  Nouvelair, fusion par régression logistique (0,825 suspect, 0,928 frauduleux).
  Sentence-BERT, DistilBERT et la forêt aléatoire ne sont plus chargés.
- **`mailguard_core.py` réécrit en pont** : mêmes fonctions qu'avant pour les
  pages (`analyser_email_complet`, `analyser_domaine_bert`, `etat_modeles`…),
  résultat enrichi (`etape_decision`, `raisons`, détail de la fusion).
- **Cascade** : liste noire → liste blanche seulement si le domaine est prouvé
  → règles sûres → score → raisons. Une règle sûre affiche un score de 1,0.
- **Listes de domaines** des pages d'administration relues par le moteur.
- **Seuils** : 0,25 / 0,50 remplacés partout par 0,825 / 0,928 ; les anciennes
  préférences enregistrées sont migrées à la connexion.
- **Message complet** transmis au moteur par la surveillance Gmail et le
  watcher : tous les en-têtes (Return-Path, Reply-To…) sont lus par S5.
- **Pages** : Accueil, Dashboard, Historique, Paramètres, Test manuel,
  Explain Detection, Model Monitoring, Calibration et Trusted Domains décrivent
  les nouveaux modèles. Le mode « simulation » d'Explain Detection (score
  inventé) est supprimé.
- **Test manuel** : en-tête d'authentification avec alignement, objet transmis,
  enregistrement dans l'historique corrigé (il échouait en silence).
- **Tests** réécrits pour le nouveau moteur ; `modeles_mailguard/` ajouté à
  `.gitignore` et au contrôle avant publication.

---

# MailGuard — refonte visuelle et correctifs

## Ce qui change dans l'interface

Le thème passe du sombre au clair. Fond `#F6F7FB`, surfaces blanches, filets
fins à `#E6E9F4`, un seul accent violet `#5B4BE8` doublé d'un sarcelle
`#00B39F` sur le filet d'en-tête. Les trois couleurs sémantiques ne servent
plus qu'à porter le risque : vert `#0E9F6E`, ambre `#E39F1C`, rouge `#E5484D`.
Elles ne décorent rien.

Typographie : **Manrope** pour toute l'interface, **JetBrains Mono** pour les
domaines, les URL et les scores. Le monospace n'est pas là pour le style : le
typosquatting se joue au caractère près, et `nouvelairr.com` ne se distingue
de `nouvelair.com` que si les glyphes sont alignés.

L'élément fort est le **bandeau de verdict**. Il remplace le duo jauge plus
badge : score en très grand sur une règle de risque qui montre où il tombe
entre les deux seuils, avec l'expéditeur, l'étage qui a tranché et l'action
appliquée sur la même ligne. Le reste de l'écran est délibérément calme.

Second repère propre au projet : le **rail de cascade**, deux segments dont
seul celui qui a tranché s'allume. Le tableau de bord en tire le chiffre
d'ouverture, la part de messages traités sans le moindre appel réseau.

Les libellés ont été réécrits du point de vue de l'utilisateur. « Sans
risque », « À surveiller », « Menace » remplacent LÉGITIME, SUSPECT et
DANGEREUX à l'affichage ; les valeurs internes ne bougent pas, l'historique
existant reste lisible.

Le thème Streamlit est fixé dans `.streamlit/config.toml`. Les pages ont été
renommées en ASCII : les anciens noms contenaient des emojis encodés qui
rendaient l'arborescence illisible hors de Streamlit.

| Avant | Après |
| --- | --- |
| `01_🏠_Accueil.py` | `1_Comment_ca_marche.py` |
| `02_📥_Surveillance_Gmail.py` | `2_Surveillance.py` |
| `03_🧪_Test_Manuel.py` | `3_Analyser_un_message.py` |
| `04_📊_Dashboard.py` | `4_Tableau_de_bord.py` |
| `05_📜_Historique.py` | `5_Historique.py` |
| `06_⚙️_Paramètres.py` | `6_Reglages.py` |

`app_dashboard.py` a été supprimé : cette version mono-page faisait double
emploi avec les pages 2 à 5.

## Les huit correctifs

**1. `construire_explication()` plantait après un échec de l'étage 2.**
Le f-string appliquait `:.0f` à la chaîne `'?'`. Une fonction `formater_age()`
tolère maintenant une valeur absente et renvoie « inconnu ».

**2. Le signal réseau tombait à 0,0 en cas de panne.**
`import whois` était hors du `try` : sans `python-whois`, l'exception remontait
et tout l'étage 2 retombait sur « domaine sain ». Une panne réseau jouait donc
en faveur de l'attaquant. L'import est maintenant dans le `try`, et si le
signal reste indisponible il vaut `None` : il est retiré du calcul et les
poids restants sont renormalisés. Le résultat porte un champ `rf_disponible`
et l'interface le signale au lieu de le taire.

**3. Un domaine créé aujourd'hui héritait de l'âge médian.**
`age_jours if age_jours else mediane_age` : un âge de 0 est falsy, donc un
domaine enregistré le jour même se voyait attribuer 5806 jours. Le signal le
plus discriminant était neutralisé exactement sur le cas le plus dangereux.
Corrigé en `is not None`, sur `age_jours`, `duree_enregistrement_jours` et
`ssl_age_jours`.

**4. Une absence d'en-tête valait un échec SPF.**
Les deux cas donnaient 0,5. Ils sont désormais distincts via
`SCORE_AUTH_ABSENT`, exposé dans `config_mailguard.json`. La valeur par défaut
reste 0,5, donc la calibration est préservée. La passer à 0,35 cesse de traiter
une absence d'en-tête comme une preuve à charge, mais demande de rejouer la
calibration.

**5. Les exemples ne remplissaient pas le formulaire.**
Les boutons écrivaient `ex_domaine` et `ex_texte` dans le `session_state`,
qu'aucun champ ne lisait. Les champs portent maintenant des clés explicites
et les exemples écrivent dedans. Les trois exemples couvrent un phishing
complet, un cas limite et un message légitime.

**6. La suppression de l'historique était inatteignable.**
Le `st.popover` de confirmation était imbriqué dans un `if st.button(...)` et
disparaissait au rechargement. La confirmation passe par un indicateur de
session, avec un bouton d'annulation.

**7. `ImapService(address="")` retombait sur le `.env`.**
Une chaîne vide est falsy dans `address or os.getenv(...)`. On distingue
maintenant « non fourni » (`None`) de « fourni vide ».

**8. Un typosquat préfixé passait au travers.**
`extraire_partie_principale` coupait au premier point puis au premier tiret :
`mail-nouvelairr.com` renvoyait `mail`. `extraire_parties_candidates()` teste
désormais chaque sous-domaine et chaque segment séparé par un tiret.

## Autre

`scikit-learn` est épinglé à `1.6.1`, la version qui a produit
`random_forest_model_FINAL.pkl`. Une autre version déclenche un
`InconsistentVersionWarning` et peut modifier les prédictions.

L'API `use_container_width`, dépréciée depuis Streamlit 1.63, a été remplacée
par `width="stretch"` partout.

## Vérification

Le dossier `tests/` contient deux bancs d'essai :

    python tests/test_all.py     # 112 vérifications sur la logique
    python tests/test_pages.py   # rendu réel des 7 pages via AppTest

Les tests marqués « Correctif » vérifient que chacun des huit défauts ne se
reproduit plus. `test_pages.py` rejoue en plus deux parcours complets : le
pré-remplissage puis la soumission du formulaire d'analyse, et l'effacement
de l'historique en deux temps.
