# MailGuard — journal des modifications

Ce document liste **toutes** les modifications apportées au projet. Rien
d'autre n'a été touché.

## Avertissement d'installation

**Supprimez d'abord les fichiers parasites d'une éventuelle installation
précédente.** Une première version de cette archive portait des noms de pages
altérés, du type `05_#L01f4dc_Historique.py` au lieu de `05_📜_Historique.py`.
Extraite par-dessus le projet, elle ajoutait six pages en double au lieu d'en
remplacer six, ce qui faisait échouer Streamlit avec l'erreur
`Multiple Pages specified with URL pathname`.

Si le dossier `pages` contient des fichiers dont le nom comporte un dièse `#`,
supprimez-les avant d'extraire cette archive. La présente version porte les
noms d'origine avec emojis et remplace bien les fichiers existants.

## Ce qui n'a pas changé

Aucun fichier n'a été renommé, déplacé ou supprimé. L'arborescence est
identique à l'originale, y compris les noms de pages avec emojis.

Aucune logique métier n'a été réécrite. Les seuils, les poids appris, la
structure de la cascade, le format de l'historique et les trois modèles sont
inchangés. `historique_analyses.json`, `decision_poids_finale.json`,
`random_forest_model_FINAL.pkl`, `gmail_watcher.py` et le dossier
`distilbert_multilingual_v3_final` sont strictement identiques.

Un seul fichier a été ajouté : `.streamlit/config.toml`, qui fixe le thème
clair de Streamlit.

## Ampleur des modifications, fichier par fichier

| Fichier | Lignes touchées | Nature |
| --- | --- | --- |
| `utils/ui_helpers.py` | réécrit | design |
| `utils/display_result.py` | réécrit | design + correctif 1 |
| `pages/01_🏠_Accueil.py` | 86 | couleurs uniquement |
| `pages/04_📊_Dashboard.py` | 52 | couleurs uniquement |
| `pages/05_📜_Historique.py` | 40 | couleurs + correctifs 1 et 6 |
| `app.py` | 32 | couleurs uniquement |
| `pages/02_📥_Surveillance_Gmail.py` | 28 | couleurs uniquement |
| `app_dashboard.py` | 26 | couleurs uniquement |
| `mailguard_core.py` | 83 | correctifs 2, 3, 4 et 8 |
| `services/quarantine_service.py` | 28 | correctif 1 |
| `pages/03_🧪_Test_Manuel.py` | 8 | couleurs + correctif 5 |
| `services/imap_service.py` | 7 | correctif 7 |
| `requirements.txt` | 4 | versions épinglées |
| `config_mailguard.json` | 4 | paramètre ajouté |

Chaque correctif est signalé dans le code par un commentaire commençant par
`CORRECTIF n :`. Une recherche du mot `CORRECTIF` dans le projet les retrouve
tous.

---

# Partie 1 — Le design

## Le parti pris

Blanc dominant, beaucoup d'air, texte bleu nuit `#0A2540` plutôt que noir. Une
bande dégradée inclinée traverse le haut de chaque page, cyan vers violet vers
rose, à 10 % d'opacité. C'est la seule fantaisie décorative de tout le système.

Les emojis ont disparu des titres et des intitulés de champs. C'était le
principal responsable de l'aspect « projet d'école ». Les noms de fichiers,
eux, gardent leurs emojis : ils sont inchangés.

## Les trois composants signature

Ce sont les éléments inventés pour ce projet précis. Ils ne décorent rien, ils
montrent ce que le code fait.

**Le comparateur de caractères.** Le domaine officiel et le domaine reçu sont
alignés l'un sous l'autre, une lettre par case. Le caractère fautif de
`nouvelairr.com` apparaît isolé en rouge. Tout le projet tient dans cette
lettre, et rien ne la montrait jusqu'ici. Implémenté avec `difflib`, il gère
les ajouts, les suppressions et les substitutions.

**La barre de construction du score.** Une seule barre où chaque signal occupe
une largeur égale à sa contribution réelle, c'est-à-dire son score multiplié
par son poids. On voit la décision s'assembler et franchir les seuils. Quand un
court-circuit de sécurité relève le score au-delà de la somme pondérée, l'écart
apparaît en hachuré : la règle a repris la main sur la moyenne.

**L'anatomie du message.** L'email est redessiné comme un objet, avec
l'expéditeur étiqueté et surtout la colonne des liens : ce que le message
annonce à gauche, l'endroit où il mène réellement à droite. La tromperie est
montrée plutôt que décrite.

Ces trois composants vivent dans `utils/ui_helpers.py` sous les noms
`comparateur_domaines()`, `barre_construction()` et `anatomie_message()`. Leur
CSS est séparé, dans `CSS_SIGNATURE`, activé par `appliquer_signature()`.

## Le verdict

Purement typographique : l'état en très grand à gauche, le score en chiffres
monospace de 4,4 rem à droite, et en dessous une règle en quarante segments qui
se colorent progressivement, avec un curseur qui pointe la position exacte du
score entre les deux seuils.

## Typographie

| Usage | Police |
| --- | --- |
| Titres | **Inter** 800, interlettrage resserré à -0,045 em, jusqu'à 3,1 rem |
| Texte et interface | **Inter** 400 à 600 |
| Domaines, URL, scores | **JetBrains Mono** |

Le monospace n'est pas décoratif : le typosquatting se joue au caractère près,
et `nouvelairr.com` ne se distingue de `nouvelair.com` que si les glyphes sont
alignés. Les chiffres sont en chasse tabulaire pour que les scores s'alignent
d'une ligne à l'autre.

## Palette

| Rôle | Valeur |
| --- | --- |
| Fond | `#FFFFFF`, sections `#F6F9FC` |
| Texte | `#0A2540`, atténué `#425466`, faible `#8792A2` |
| Filets | `#E3E8EE` |
| Accent | `#635BFF`, secondaires `#00D4FF` et `#FF5996` |
| Sans risque | `#00A868` |
| À surveiller | `#FF8F00` |
| Menace | `#E25950` |

Les couleurs sémantiques ne servent qu'à porter le risque. Aucune couleur n'est
décorative, à l'exception de la bande dégradée en haut de page.

## Pages refondues

Les sept écrans ont été repris : `app.py` et les six pages. La logique métier,
les clés de `session_state`, les appels aux services et le format de
l'historique sont inchangés. Seule la présentation a été réécrite.

Le mot de confirmation pour effacer l'historique reste `CONFIRMER` sur la page
Paramètres, comme dans la version d'origine.

## Widgets natifs de Streamlit

Retravaillés au CSS : boutons principaux en violet plein avec ombre colorée et
léger soulèvement au survol, anneau de focus violet sur les champs, onglets à
soulignement fin, cartes de statistiques surélevées avec valeurs en 2,3 rem,
tableaux à coins arrondis.

## Accessibilité

Toutes les animations se désactivent si le système demande la réduction des
animations, via `prefers-reduced-motion`. Les tailles s'adaptent en dessous de
760 px. Les boutons ont un anneau de focus visible au clavier.

## Thème Streamlit

`.streamlit/config.toml` fixe le thème clair et la couleur principale. Sans ce
fichier, Streamlit resterait sur son thème sombre par défaut.

---

# Partie 2 — Les huit correctifs

## Correctif 1 — `applymap` supprimé dans pandas 3

**Fichiers :** `utils/display_result.py`, `pages/05_📜_Historique.py`,
`services/quarantine_service.py`

`Styler.applymap` a été supprimé dans pandas 3, où la méthode s'appelle
désormais `map`. Sur toute machine ayant pandas 3, l'application plantait avec
`AttributeError: 'Styler' object has no attribute 'applymap'` à l'ouverture du
tableau récapitulatif et de la page Historique.

Effet secondaire important : dans la page Test Manuel, le plantage survenait
**avant** la ligne de sauvegarde. Les analyses n'étaient donc jamais
enregistrées, et le Dashboard restait vide.

Corrigé : 2 occurrences remplacées dans la page Historique, et
`display_result.py` réécrit sans `applymap`.

Second volet du même correctif, dans `services/quarantine_service.py` : le code
appliquait le format `:.0f` à la chaîne `'?'` lorsque l'étage 2 avait échoué,
ce qui levait une `ValueError`. Une fonction `formater_age()` a été ajoutée,
elle renvoie « inconnu » quand la valeur est absente.

## Correctif 2 — une panne réseau rendait un domaine « sain »

**Fichier :** `mailguard_core.py`

Dans `get_domain_whois_features()`, la ligne `import whois` était placée **hors
du bloc `try`**. Sans la bibliothèque `python-whois`, ou en cas de coupure
réseau, l'exception remontait jusqu'à `calculer_score_cascade`, qui la
rattrapait en affectant `0.0` au signal de vérification du domaine. Or `0.0`
signifie « domaine parfaitement sain ». Une panne jouait donc en faveur de
l'attaquant.

Deux changements. L'import est passé dans le `try`. Et surtout, quand le signal
reste indisponible, il vaut désormais `None` : il est retiré du calcul et les
poids restants sont renormalisés, au lieu d'être compté comme favorable.

Mesure sur un cas de test : le score passe de `0.230` en fail-open à `0.292`
avec la renormalisation. Le résultat porte en plus un champ `rf_disponible`, et
`signaux_calcules` annonce 4 au lieu de 5.

## Correctif 3 — un domaine créé aujourd'hui héritait de l'âge médian

**Fichier :** `mailguard_core.py`

L'écriture `age_jours if age_jours else mediane_age` pose problème parce que
Python considère le nombre zéro comme faux. Un domaine enregistré le jour même
a un âge de 0, il se voyait donc attribuer la médiane de la base, soit **5806
jours**, presque seize ans d'ancienneté.

Le signal le plus discriminant du RandomForest était ainsi neutralisé
exactement sur le cas le plus dangereux, un domaine tout frais fabriqué pour
l'occasion.

Corrigé en `is not None`, sur `age_jours`, `duree_enregistrement_jours` et
`ssl_age_jours`. Vérifié par test : un domaine d'âge 0 conserve bien 0, et le
RandomForest le classe en frauduleux.

## Correctif 4 — une absence d'en-tête valait un échec avéré

**Fichiers :** `mailguard_core.py`, `config_mailguard.json`

Un message sans en-tête `Authentication-Results` recevait `0.5`, exactement
comme un message dont le SPF a échoué. Ce sont deux situations très
différentes : l'une est une absence d'information, l'autre une preuve à charge.

Une constante `SCORE_AUTH_ABSENT` a été introduite, lisible depuis
`config_mailguard.json`.

**La valeur par défaut est 0.5, soit exactement le comportement d'origine. La
calibration reste donc valable et aucun résultat ne change.** La passer à 0.35
cesse de traiter une absence comme une charge, mais impose de rejouer la
calibration. C'est un choix à faire en connaissance de cause.

## Correctif 5 — les boutons « Exemples rapides » ne faisaient rien

**Fichier :** `pages/03_🧪_Test_Manuel.py`

Les trois boutons écrivaient bien les valeurs dans
`st.session_state["ex_domaine"]` et `st.session_state["ex_texte"]`, mais aucun
champ du formulaire n'allait lire ces clés. Le clic ne produisait aucun effet
visible et aucun message d'erreur.

Les noms de clés étaient corrects, seule la liaison manquait. Deux lignes
ajoutées : `value=st.session_state.get("ex_domaine", "")` sur le champ du
domaine, et l'équivalent sur la zone de texte.

## Correctif 6 — la suppression de l'historique était inatteignable

**Fichier :** `pages/05_📜_Historique.py`

Le `st.popover` de confirmation était imbriqué à l'intérieur du
`if st.button(...)` qui le déclenchait. Streamlit réexécute la page à chaque
clic, donc la confirmation disparaissait aussitôt apparue.

L'intention de suppression est désormais mémorisée dans
`st.session_state["confirmer_effacement"]`, ce qui lui permet de survivre au
rechargement. Un bouton d'annulation a été ajouté.

## Correctif 7 — `ImapService(address="")` retombait sur le `.env`

**Fichier :** `services/imap_service.py`

Même piège que le zéro du correctif 3 : dans `address or os.getenv(...)`, une
chaîne vide est considérée fausse, donc passer explicitement `""` faisait
quand même lire le fichier `.env`. On distingue maintenant « non fourni »
(`None`) de « fourni vide » (`""`).

## Correctif 8 — un typosquat préfixé passait au travers

**Fichier :** `mailguard_core.py`

`extraire_partie_principale()` coupait au premier point puis au premier tiret.
`mail-nouvelairr.com` était donc réduit à `mail`, et le typosquat n'était
jamais comparé aux domaines de confiance.

Une fonction `extraire_parties_candidates()` teste désormais chaque
sous-domaine et chaque segment séparé par un tiret.
`extraire_partie_principale()` est conservée telle quelle pour compatibilité,
elle renvoie le segment le plus long.

Vérifié : `mail-nouvelairr.com` et `secure.nouvelairr.co.uk` sont maintenant
détectés.

---

# Partie 3 — Versions épinglées

**Fichier :** `requirements.txt`

`pandas<3`, parce que pandas 3 supprime `Styler.applymap`. Même avec le
correctif 1 appliqué, mieux vaut fixer la version pour éviter d'autres
surprises.

`scikit-learn==1.6.1`, la version qui a produit
`random_forest_model_FINAL.pkl`. Une autre version déclenche un
`InconsistentVersionWarning` et peut modifier les prédictions du modèle.

---

# Partie 4 — Vérification

Le dossier `tests/` contient deux bancs d'essai.

    python tests/test_all.py           # 129 vérifications de logique
    python tests/test_auth.py          # 67 vérifications : comptes, base, protocoles
    python tests/migrer_vers_base.py   # migration des anciens fichiers JSON
    python tests/cas_de_test.py        # les 12 cas du plan de test
    python tests/test_pages.py         # rendu réel des 7 pages via AppTest
    python tests/diagnostic_modele.py  # comportement réel du modèle de contenu

`diagnostic_modele.py` fait passer au classifieur quinze messages
professionnels banals et huit messages de phishing qu'il n'a jamais vus, puis
mesure le taux de faux positifs, la distribution des probabilités et le seuil
qui offre le meilleur compromis. Il n'entraîne rien et ne modifie rien.
Contrairement aux deux autres, il a besoin des vrais modèles installés.

Résultat sur cette version : **114 sur 114**, et les sept pages se rendent sans
erreur. Deux parcours complets sont rejoués : le pré-remplissage puis la
soumission du formulaire d'analyse, et l'effacement de l'historique en deux
temps.

Quinze de ces vérifications portent spécifiquement sur les huit correctifs et
servent de garde-fou : si l'un d'eux était annulé par erreur, le test
correspondant échouerait.

`tests/stubs.py` remplace `torch`, `transformers` et `sentence-transformers`
par des substituts déterministes, afin que les tests tournent sans télécharger
les modèles. Le RandomForest, lui, est le vrai modèle chargé depuis le `.pkl`.

---

# Partie 2 bis — Quatre correctifs issus du plan de test des 12 cas

Le plan de test fourni par l'autrice a fait apparaître trois défauts de fond,
invisibles jusque-là. Un quatrième correctif accompagne le premier.

## Correctif 10 — l'étage 2 abaissait les scores au lieu de les affiner

**Fichier :** `mailguard_core.py`

Les poids de l'étage 1 somment à 1 sur quatre signaux, ceux de l'étage 2 sur
cinq, dont 0,213 pour la vérification réseau. Quand ce cinquième signal valait
0, les quatre autres ne pesaient plus que 78,7 % de leur poids initial :
**tout score recalculé à l'étage 2 perdait 21 %.**

Conséquence mesurée : un message dont le seul signal de contenu était au
maximum sortait à 0,301 à l'étage 1, donc SUSPECT. Ce score tombant dans la
zone ambiguë, l'étage 2 se déclenchait, recalculait, et donnait 0,237, donc
LÉGITIME. **L'étage 2 annulait une détection correcte.** Tout score d'étage 1
compris entre 0,25 et 0,318 subissait ce sort, c'est-à-dire tout message dont
un seul signal était au maximum.

L'étage 2 est là pour lever un doute, pas pour disculper. Il peut désormais
aggraver le verdict, jamais l'alléger :
`score_final = max(score_final, score_rapide)`.

Cas 3, 4 et 9 du plan de test corrigés.

## Correctif 11 — un lien trompeur seul était indétectable

**Fichiers :** `mailguard_core.py`, `config_mailguard.json`

Le poids des liens vaut 0,116 à l'étage 1 et 0,091 à l'étage 2. Même à 1,00,
ce signal ne pouvait mathématiquement jamais atteindre le seuil de 0,25 : un
lien qui annonce un domaine et mène ailleurs passait inaperçu s'il était le
seul indice. Le cas 5 sortait à 0,091.

Ce poids vient d'un plancher posé à la main, faute de cas de liens trompeurs
dans le jeu de calibration, comme le documente `decision_poids_finale.json`.

Un lien trompeur est une tromperie délibérée : il reçoit maintenant le même
traitement qu'un échec d'authentification, via `SCORE_PLANCHER_LIENS = 0.30`,
exposé dans la configuration.

Cas 5 du plan de test corrigé.

## Correctif 12 — les chiffres à la place des lettres n'étaient pas détectés

**Fichier :** `mailguard_core.py`

Le modèle sémantique repère `nouvelairr.com` à une distance de 0,0782, mais pas
`n0uvelair.com`, qui ressortait à 0,00 sur le signal domaine. La raison est
technique : un mot contenant un chiffre est découpé par le tokenizer en
morceaux sans rapport avec le mot d'origine, et la similarité s'effondre.

Or la substitution d'homoglyphes est la forme la plus répandue de
typosquatting : `0` pour `o`, `1` pour `l`, `3` pour `e`, `5` pour `s`.

Le domaine est désormais comparé sous ses deux formes, brute et normalisée, et
la plus faible des deux distances est retenue. Quand la forme normalisée tombe
exactement sur un domaine de confiance, le verdict est immédiat, sans même
interroger le modèle. Le verdict précise alors « caractères substitués ».

Cas 2 du plan de test corrigé.

## Correctif 13 — conséquence du correctif 10 sur l'absence d'en-tête

**Fichier :** `config_mailguard.json`

Une fois le correctif 10 en place, `SCORE_AUTH_ABSENT = 0.5` suffisait à lui
seul à classer SUSPECT tout message dépourvu d'en-tête `Authentication-Results`,
y compris venant d'un domaine de confiance : 0,5 × 0,583 = 0,292, au-dessus du
seuil de 0,25.

La valeur est abaissée à **0,35**. Une absence d'en-tête ne suffit plus à
elle seule (0,204), alors qu'un échec SPF avéré (0,5) déclenche toujours.
Remettre 0.5 dans la configuration rétablit l'ancien comportement, en une
ligne.

## Résultat sur le plan de test

Avant ces correctifs : 7 cas conformes sur 12.
Après : **12 sur 12.**

---

# Partie 5 — Comptes utilisateurs

Demande de l'encadrant : chaque utilisateur se connecte avec sa propre adresse
email. L'application est désormais multi-comptes.

## Ce qui a été ajouté

| Fichier | Rôle |
| --- | --- |
| `services/auth_service.py` | Inscription, connexion, chiffrement, préférences |
| `utils/auth_ui.py` | Écrans de connexion et d'inscription, verrou d'accès |
| `tests/test_auth.py` | 47 vérifications du service de comptes |
| `comptes_utilisateurs.json` | Magasin des comptes, créé au premier usage |
| `historiques/` | Un fichier d'historique par compte |

Les deux derniers sont ajoutés à `.gitignore` : ce sont des données
personnelles.

## Sécurité des mots de passe

Le mot de passe n'est jamais stocké. Seule une empreinte **PBKDF2-HMAC-SHA256**
est conservée, avec **240 000 itérations** et un **sel aléatoire de 16 octets**
propre à chaque compte. Deux comptes ayant le même mot de passe ont donc des
empreintes différentes.

La vérification utilise `hmac.compare_digest`, une comparaison en temps
constant : la durée de la réponse ne trahit pas le nombre de caractères
corrects.

Une tentative de connexion sur une adresse inexistante déclenche quand même un
hachage complet, mesuré à 60 ms, afin que la durée ne révèle pas quelles
adresses possèdent un compte. Le message d'erreur est d'ailleurs identique dans
les deux cas d'échec.

## Le mot de passe d'application Gmail

Celui-ci ne peut pas être haché : il doit être restitué en clair au moment de la
connexion IMAP. Il est donc **chiffré avec Fernet** (AES-128-CBC authentifié par
HMAC). La clé vit dans `.env` sous `MAILGUARD_SECRET_KEY`, générée
automatiquement au premier lancement, et n'est jamais écrite dans le magasin de
comptes : quelqu'un qui récupérerait le seul fichier JSON ne pourrait rien en
tirer.

Le fichier `.env` ne contient donc plus d'identifiants Gmail. Chaque utilisateur
relie sa propre boîte depuis la page Paramètres, et peut l'oublier d'un clic.

## Cloisonnement

Chaque compte reçoit un identifiant de 16 caractères, dérivé de son adresse par
SHA-256. Cet identifiant nomme son fichier d'historique, ce qui évite de mettre
une adresse email en clair dans un nom de fichier.

Sont propres à chaque compte : l'historique des analyses, les identifiants
Gmail, les deux seuils de décision et l'action automatique. Deux utilisateurs de
la même installation ne voient jamais les analyses l'un de l'autre, ce que
`tests/test_auth.py` vérifie explicitement.

Les fonctions du service d'historique acceptent un argument `identifiant`
**optionnel**. Sans lui, elles retombent sur le fichier unique d'origine : le
comportement antérieur et les 117 tests existants restent valables.

## Le verrou d'accès

Streamlit affiche toutes les pages du dossier `pages/` sans notion
d'autorisation. Le verrou est donc posé dans chaque page : un appel à
`exiger_connexion()` en tête de fichier interrompt le rendu et affiche le
formulaire tant que personne n'est authentifié.

La session vit dans `st.session_state` et se termine à la fermeture de l'onglet,
ce qui est le comportement attendu sur un poste partagé. La déconnexion efface
aussi le journal de surveillance et la dernière alerte, pour ne rien laisser au
compte suivant.

## Limites à mentionner en soutenance

Le magasin est un fichier JSON local, adapté à une démonstration et à une petite
équipe, pas à un déploiement en production où il faudrait une base de données et
une gestion de session côté serveur.

Il n'y a ni vérification d'adresse par email, ni récupération de mot de passe
oublié : un compte perdu doit être recréé. Il n'y a pas non plus de limitation
du nombre de tentatives de connexion, ce qui laisse la porte ouverte à une
attaque par force brute si l'application était exposée sur un réseau.

---

# Partie 6 — Base de données

Demande de l'encadrant : stocker les données dans une base. Les fichiers JSON
sont remplacés par un schéma relationnel.

## Moteur

SQLite par défaut : la base tient dans un fichier, ne demande aucun serveur et
respecte les propriétés ACID. C'est le bon choix pour une application installée
sur un poste.

Tout l'accès aux données passe par **SQLAlchemy**, et aucune requête n'utilise
de syntaxe propre à un moteur. Le passage à MySQL ou PostgreSQL ne demande donc
qu'une variable d'environnement dans `.env` :

    MAILGUARD_DATABASE_URL=mysql+pymysql://user:motdepasse@serveur/mailguard
    MAILGUARD_DATABASE_URL=postgresql+psycopg2://user:motdepasse@serveur/mailguard

## Le schéma

Cinq tables, en troisième forme normale.

    utilisateurs ──1:1── identifiants_gmail
         │       └─1:1── preferences
         └───────1:N──── analyses ──1:N── scores_signaux

| Table | Contenu |
| --- | --- |
| `utilisateurs` | email unique et indexé, identifiant public, nom, empreinte, sel, dates |
| `identifiants_gmail` | adresse et mot de passe d'application chiffré, un par compte |
| `preferences` | les deux seuils et l'action automatique, un jeu par compte |
| `analyses` | une ligne par email analysé, avec score, catégorie, étage et durée |
| `scores_signaux` | une ligne par signal et par analyse |

**Les scores sont stockés en lignes plutôt qu'en colonnes.** Cela coûte une
jointure, mais permet d'ajouter un sixième signal sans modifier le schéma, et
surtout d'agréger en SQL. La moyenne par signal du tableau de bord est devenue
un simple `GROUP BY` là où elle demandait auparavant de parcourir tout
l'historique en Python.

Une nuance importante y est préservée : la valeur `NULL` signifie « signal non
calculé », par exemple la vérification réseau quand la décision a été prise à
l'étage 1. Elle ne doit pas être confondue avec `0.0`, qui signifie « calculé,
et favorable ». C'est exactement la distinction introduite par le correctif 2.

Le détail brut de chaque analyse, dont la structure varie selon les signaux
calculés, reste dans une colonne JSON. Choix assumé : ce contenu n'est jamais
interrogé, seulement réaffiché.

## Intégrité

Les clés étrangères sont déclarées avec suppression en cascade, et **activées
explicitement sur SQLite**, où elles sont désactivées par défaut. Sans cette
ligne, supprimer un compte aurait laissé ses analyses orphelines.

Deux tests vérifient qu'après la suppression d'un compte il ne reste ni score
sans analyse, ni identifiant Gmail sans compte.

## Migration

`tests/migrer_vers_base.py` importe les anciens fichiers dans la base.

    python tests/migrer_vers_base.py              # aperçu, sans rien écrire
    python tests/migrer_vers_base.py --appliquer  # migration effective

Le script est **idempotent** : relancé, il ne crée pas de doublons, le doublon
se reconnaissant au couple horodatage et domaine expéditeur. Les fichiers
d'origine ne sont ni modifiés ni supprimés.

## Compatibilité

Les signatures des fonctions de `history_service` sont inchangées. Les pages
n'ont pas eu à être modifiées, à l'exception du tableau de bord qui profite
désormais de l'agrégation SQL. Les 117 vérifications antérieures continuent de
passer, complétées par cinq nouvelles portant sur la base.

## Ce qu'il faut retenir pour la soutenance

Le passage en base n'est pas qu'un changement de rangement. Il apporte
l'intégrité référentielle, qui garantit qu'aucune donnée orpheline ne subsiste ;
les contraintes d'unicité, qui empêchent deux comptes sur la même adresse au
niveau du moteur et non plus seulement du code ; les index sur l'email, la
catégorie et l'horodatage ; les transactions, qui évitent qu'une analyse soit
enregistrée à moitié ; et la capacité d'agréger côté serveur.

---

# Partie 7 — Démonstration avec l'encadrant

Trois exigences, dont une qui évitait un incident de démonstration.

## Correctif 14 — l'expéditeur interne authentifié

**Le risque.** L'encadrant travaille chez Nouvelair. Il enverra donc un message
depuis une adresse `@nouvelair.com`, correctement authentifiée, avec un texte
professionnel banal. Or le classifieur de contenu se trompe sur 53 % de ces
messages, avec une certitude de 1,000. Le calcul était sans appel : 1,00 × 0,301
donne **0,301**, au-dessus du seuil de 0,25. **Son propre email serait parti en
quarantaine devant lui.**

**La règle.** Un message venant exactement d'un domaine de confiance, dont SPF,
DKIM et DMARC passent tous les trois, et qui ne contient aucun lien trompeur, ne
peut plus être classé suspect sur sa seule rédaction. Son score est plafonné à
`PLAFOND_EXPEDITEUR_AUTHENTIFIE`, réglé à 0,20.

**Ce que la règle ne couvre pas, volontairement.** Un lien trompeur, un
typosquat, un échec d'authentification ou un domaine douteux au registre
continuent de déclencher normalement. Seule la rédaction cesse d'être une preuve
suffisante à elle seule.

**La décision est rendue dès l'étage 1**, sans appel réseau. C'était nécessaire :
lors des essais, une panne WHOIS faisait remonter le signal réseau à 1,00 et
levait le plafond. Le verdict d'un email interne ne dépend donc plus de l'état
du réseau.

**La contrepartie, à assumer devant le jury.** Un compte interne compromis, qui
passe donc l'authentification, ne sera pas détecté sur le seul contenu. C'est le
compromis classique du courrier interne authentifié, et il vaut mieux que
l'inverse tant que le modèle de contenu n'est pas réentraîné. Le cas 3 du plan
de test change de verdict à cause de cette règle, et le fichier de test
l'explique en commentaire. Mettre `PLAFOND_EXPEDITEUR_AUTHENTIFIE` à 1.0 dans la
configuration rétablit l'ancien comportement.

## Chargement unique des modèles

Les trois modèles pèsent environ 1 Go et prennent une trentaine de secondes à
charger. Ils sont désormais chargés par `charger_modeles()`, **une seule fois par
processus**, et partagés par toutes les sessions ouvertes : un nouvel
utilisateur qui se connecte ne déclenche aucun rechargement.

Un verrou protège le cas où deux utilisateurs arrivent exactement en même temps
sur un serveur qui démarre ; sans lui, deux threads pourraient lancer le
chargement en parallèle et occuper le double de mémoire. L'inférence, elle,
n'est pas verrouillée : PyTorch et scikit-learn sont sûrs en lecture
concurrente, et sérialiser les analyses ferait attendre les utilisateurs les uns
derrière les autres.

La page Paramètres affiche la durée du chargement, le processus et l'heure, ce
qui rend la démonstration vérifiable.

## Trois protocoles au choix

`services/mail_providers.py` place IMAP, POP3 et Microsoft Graph derrière une
interface commune. Le reste de l'application ne voit qu'un objet exposant
toujours les mêmes méthodes ; ajouter un quatrième protocole ne demanderait de
toucher ni aux pages, ni au moteur.

| Protocole | Déplacement possible | Ce qu'il faut |
| --- | --- | --- |
| IMAP | oui | adresse, mot de passe d'application, serveur, port |
| POP3 | **non** | adresse, mot de passe d'application, serveur, port |
| Microsoft Graph | oui | adresse, locataire, identifiant client, secret client |

**POP3 ne connaît pas la notion de dossier.** La mise en quarantaine y est
impossible : MailGuard peut analyser et alerter, mais pas ranger. C'est une
limite du protocole, pas de l'application, et aucun contournement n'existe.
L'interface le signale avant le démarrage de la surveillance.

**Microsoft Graph** convient à une boîte Outlook professionnelle, mais exige une
application enregistrée dans Azure Active Directory avec la permission
`Mail.ReadWrite` accordée par un administrateur. Microsoft a supprimé
l'authentification par simple mot de passe pour ce type d'accès. Sans l'accord
du service informatique, ce protocole ne peut pas fonctionner.

Les secrets des trois protocoles sont chiffrés avant d'être écrits en base, et
un champ laissé vide conserve la valeur précédente.

## Migration du schéma

La table des identifiants a reçu six colonnes : protocole, serveur, port,
locataire, identifiant client et secret client chiffré. Une base créée par une
version antérieure est mise à jour automatiquement au démarrage, par ajout des
colonnes manquantes. Aucune suppression de base n'est nécessaire.

---

# Partie 8 — Les notebooks

`tests/cellule_sync_notebooks.py` contient une cellule à coller en dernière
position dans les deux notebooks, puis à exécuter. Elle remplace les définitions
périmées par celles de l'application.

Ce qu'elle corrige :

- **Les poids.** Les manuels (0,30 / 0,20 / 0,20 / 0,15 / 0,15) sont remplacés
  par les poids appris. Le notebook 1 démontre lui-même, cellule 517, que les
  manuels donnent un F2 de 0,2756 contre 0,95 d'exactitude pour les appris.
- **Le seuil de typosquat.** 0,393 devient 0,125. À 0,393, `airfrance.com`, dont
  la distance mesurée est de 0,3311 en cellule 429, serait déclaré typosquat de
  `nouvelair.com`.
- **La cascade à deux étages**, qui n'existait dans aucun notebook. Elle n'y
  figurait que sous forme de texte, cellules 442 à 446 du notebook 1.
- **Les court-circuits et planchers** : typosquat 0,75, liens 0,30,
  authentification 0,30, plancher d'étage, plafond interne.
- **Les homoglyphes** et le test de chaque segment du domaine.

Le notebook 2 reste par ailleurs fidèle à l'application sur le modèle de
contenu : même chemin, même seuil, même troncature à 256 tokens.

Une divergence subsiste et n'est pas corrigeable par cette cellule : le notebook
2 convertit le modèle en ONNX et mesure le gain, alors que l'application charge
le modèle PyTorch. Ce travail doit être présenté comme une piste mesurée mais
non intégrée, ou bien branché dans l'application.

---

# Un neuvième constat, non corrigé volontairement

`config_mailguard.json` contient `SEUIL_CONTENU = 0.526`, chargé au démarrage
dans la variable `SEUIL_CONTENU` de `mailguard_core.py`. Mais
`analyser_contenu_distilbert()` utilise `SEUIL_CONTENU_DISTILBERT = 0.5`, écrit
en dur trois lignes plus bas. **La valeur calibrée n'est donc jamais
appliquée.**

Je n'y ai pas touché : passer de 0.5 à 0.526 modifie les décisions du filtre,
et ce choix revient à l'autrice du modèle. Le script de diagnostic signale
l'écart à chaque exécution.

---

# Ce qui n'est pas corrigé, et qui compte

Le modèle de contenu classe la phrase « Bonjour, veuillez trouver ci-joint le
document demandé lors de notre dernier échange. Cordialement. » à **100 % de
probabilité de phishing**. C'est une formule administrative parfaitement
banale.

Ce n'est pas un défaut de code, c'est une limite du modèle entraîné, et aucun
correctif logiciel ne peut le résoudre. Le corpus d'entraînement contient
probablement beaucoup de phishing rédigé dans un registre formel français, et
pas assez de vrais messages professionnels légitimes.

En usage réel, ce serait le problème le plus visible pour les utilisateurs, et
c'est la piste d'amélioration la plus rentable du projet.
