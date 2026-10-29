# 🛡️ MailGuard — Détection de Phishing pour Nouvelair

**MailGuard** est une application de détection de phishing basée sur le **Machine Learning**, développée pour la compagnie aérienne **Nouvelair**. Elle analyse les emails en temps réel via 5 signaux complémentaires et un modèle de fusion appris, et offre un panneau d'administration complet pour la gestion de la sécurité.

![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![PyTorch](https://img.shields.io/badge/PyTorch-EE4C2C?style=for-the-badge&logo=pytorch&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white)

---

## 📋 Table des matières

- [Architecture](#-architecture)
- [Les 5 Signaux de Détection](#-les-5-signaux-de-détection)
- [Prérequis](#-prérequis)
- [Installation Pas à Pas](#-installation-pas-à-pas)
- [Lancement de l'Application](#-lancement-de-lapplication)
- [Comptes et Authentification](#-comptes-et-authentification)
- [Guide d'Utilisation](#-guide-dutilisation)
- [Pages de l'Application](#-pages-de-lapplication)
- [Configuration Gmail / IMAP](#-configuration-gmail--imap)
- [Configuration Avancée](#-configuration-avancée)
- [Structure du Projet](#-structure-du-projet)
- [Tests](#-tests)
- [Dépannage](#-dépannage)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                 Interface Streamlit                  │
│    (app.py → pages 01-06 User / 07-19 Admin)        │
├─────────────────────────────────────────────────────┤
│              Moteur MailGuard Core                    │
│     (mailguard_core.py — 5 signaux + fusion)         │
├──────────┬──────────┬──────────┬──────────┬─────────┤
│ Signal 1 │ Signal 2 │ Signal 3 │ Signal 4 │Signal 5 │
│  CANINE  │  RDAP/   │ Liens /  │ Contenu  │  Auth   │
│ (domaine)│  crt.sh  │  URLs    │ (e5+LR)  │(SPF/    │
│          │          │          │          │DKIM/    │
│          │          │          │          │DMARC)   │
├──────────┴──────────┴──────────┴──────────┴─────────┤
│        Modèle de Fusion (Régression Logistique)      │
├─────────────────────────────────────────────────────┤
│    SQLite / MySQL / PostgreSQL (via SQLAlchemy)       │
└─────────────────────────────────────────────────────┘
```

## 🔍 Les 5 Signaux de Détection

| Signal | Nom | Description | Modèle |
|--------|-----|-------------|--------|
| **S1** | Domaine (CANINE) | Détecte le typosquatting de marques protégées | CANINE (Transformer) |
| **S2** | Identité (RDAP/crt.sh) | Vérifie l'âge du domaine et les certificats | GradientBoosting |
| **S3** | Liens (URLs) | Analyse les URLs dans le corps de l'email | GradientBoosting |
| **S4** | Contenu textuel | Analyse sémantique du contenu | multilingual-e5 + Régression Logistique |
| **S5** | Authentification | Vérifie SPF, DKIM, DMARC | Modèle dédié |

---

## 📦 Prérequis

- **Python 3.11** ou supérieur
- **pip** (gestionnaire de paquets Python)
- **Git**
- **Connexion Internet** (pour le téléchargement initial du modèle e5 et les vérifications RDAP/crt.sh)

> ⚠️ **Modèles ML** : Les fichiers de modèles (`.safetensors`, `.joblib`) sont volumineux et ne sont **PAS inclus** dans ce dépôt GitHub. Ils doivent être obtenus séparément et placés dans le dossier `modeles_mailguard/`.

---

## 🚀 Installation Pas à Pas

### Étape 1 — Cloner le dépôt

```bash
git clone https://github.com/WiemSaafi/mailguard_NOVELAIR_with_Admin.git
cd mailguard_NOVELAIR_with_Admin
```

### Étape 2 — Créer un environnement virtuel

**Windows (PowerShell) :**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Windows (CMD) :**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

**Linux / macOS :**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Étape 3 — Installer les dépendances

```bash
pip install -r requirements.txt
```

> ⏳ L'installation de `torch` et `transformers` peut prendre plusieurs minutes.

### Étape 4 — Configurer le fichier `.env`

```bash
# Copier le fichier d'exemple
cp .env.example .env
```

**Contenu du fichier `.env` :**
```env
# --- Modèles MailGuard ---
# Chemin vers le dossier des modèles (par défaut : modeles_mailguard/ à la racine)
# MAILGUARD_MODELES=C:\chemin\vers\modeles_mailguard

# --- Base de données ---
# SQLite par défaut (aucune configuration requise)
# Pour MySQL :
# MAILGUARD_DATABASE_URL=mysql+pymysql://utilisateur:motdepasse@serveur/mailguard
# Pour PostgreSQL :
# MAILGUARD_DATABASE_URL=postgresql+psycopg2://utilisateur:motdepasse@serveur/mailguard

# --- Clé de chiffrement ---
# Générée automatiquement au premier lancement. Ne pas supprimer !
# MAILGUARD_SECRET_KEY=

# --- Mode hors ligne (optionnel) ---
# Mettre 0 pour désactiver les vérifications RDAP/crt.sh (signal 2)
# MAILGUARD_INTERNET=1
```

> 💡 **La clé de chiffrement** (`MAILGUARD_SECRET_KEY`) est **générée automatiquement** au premier lancement. Elle chiffre les mots de passe d'application Gmail stockés en base.

### Étape 5 — Placer les modèles ML

Placez les fichiers de modèles dans le dossier `modeles_mailguard/` avec la structure suivante :

```
modeles_mailguard/
├── modeles/
│   └── CANINE/
│       ├── config.json
│       ├── model.safetensors
│       ├── tokenizer_config.json
│       └── seuil.csv
├── fusion_modele/
│   ├── fusion.joblib
│   └── parametres.json
├── s4_modele_final/
│   ├── logistique_e5.joblib
│   ├── parametres.json
│   └── s4_outils.py
├── s5_modele_final/
│   ├── detecteur_auth.py
│   ├── modele_auth.joblib
│   ├── parametres.json
│   └── requirements.txt
├── modeles_signal2_v2.joblib
├── modeles_signal3_final.joblib
├── blacklist_propre.csv
├── whitelist_propre.csv
├── marques_protegees.csv
└── tranco_top1m.csv
```

---

## ▶️ Lancement de l'Application

### Commande principale

```bash
streamlit run app.py
```

L'application se lance par défaut sur **http://localhost:8501**.

### Options de lancement utiles

```bash
# Lancer sur un port spécifique
streamlit run app.py --server.port 8080

# Lancer accessible depuis le réseau local
streamlit run app.py --server.address 0.0.0.0

# Lancer sans ouvrir le navigateur automatiquement
streamlit run app.py --server.headless true

# Combiné : port personnalisé + réseau + sans navigateur
streamlit run app.py --server.port 8080 --server.address 0.0.0.0 --server.headless true
```

### Vérification

Une fois lancé, ouvrez votre navigateur à l'adresse :
```
http://localhost:8501
```

---

## 🔐 Comptes et Authentification

### Compte Administrateur par défaut

> ⚠️ **IMPORTANT** : Changez le mot de passe administrateur immédiatement après la première connexion !

| Champ | Valeur |
|-------|--------|
| **Email** | `admin@nouvelair.com` |
| **Mot de passe** | `Admin2024!` |
| **Rôle** | Administrateur |

L'administrateur par défaut est **créé automatiquement** au premier lancement si aucun admin n'existe dans la base de données.

### Créer un compte Utilisateur

1. Ouvrez l'application dans votre navigateur
2. Sur l'écran de connexion, cliquez sur **« S'inscrire »**
3. Remplissez le formulaire :
   - **Email** : votre adresse email (format valide requis)
   - **Mot de passe** : minimum 8 caractères, au moins 1 chiffre et 1 lettre
   - **Nom** : votre nom d'affichage (optionnel)
4. ⏳ **Votre compte sera en statut `pending`** (en attente)
5. Un **administrateur** doit **valider votre compte** depuis la page *ADMIN → Utilisateurs*

### Règles de mot de passe

- Minimum **8 caractères**
- Au moins **1 chiffre**
- Au moins **1 lettre**

### Processus de validation des comptes

```
Inscription utilisateur → Statut "pending" → Validation par admin → Statut "active" → Connexion autorisée
```

### Gestion des administrateurs

L'admin principal peut :
- **Créer** d'autres administrateurs (page *ADMIN → Administrateurs*)
- **Activer / Suspendre** des comptes admin
- **Supprimer** des admins (il doit rester au moins 1 admin actif)

---

## 📖 Guide d'Utilisation

### Pour les Utilisateurs

1. **Connexion** : Entrez vos identifiants sur l'écran d'authentification
2. **Test Manuel** : Analysez un email en collant son contenu ou en important un fichier `.eml`
3. **Surveillance Gmail** : Configurez votre boîte Gmail pour une surveillance en temps réel
4. **Dashboard** : Consultez les statistiques et tendances de vos analyses
5. **Historique** : Retrouvez toutes vos analyses passées
6. **Paramètres** : Ajustez vos seuils de détection et votre configuration de messagerie

### Pour les Administrateurs

En plus des pages utilisateur, l'administrateur accède au **Security Center** :

| Page | Fonction |
|------|----------|
| 🔐 Security Center | Vue d'ensemble de la sécurité |
| 👥 Utilisateurs | Valider, suspendre, supprimer les comptes |
| 🛡️ Administrateurs | Gérer les comptes admin |
| 🌐 Trusted Domains | Gérer la whitelist (vérification CANINE) |
| 🚫 Fraudulent Domains | Gérer la blacklist |
| 🔍 Review Detections | Qualifier les détections (faux positifs/négatifs) |
| 🧠 Explain Detection | Comprendre une détection en détail |
| 📈 Model Monitoring | Suivre les performances des modèles |
| ⚖️ Calibration | Ajuster les seuils de fusion |
| ⚔️ Attack Campaigns | Regrouper les attaques par campagne |
| 🚨 Security Alerts | Alertes de sécurité en temps réel |
| 📄 Reports | Générer des rapports |
| 📋 Audit Logs | Journal d'audit de toutes les actions |

---

## 📬 Configuration Gmail / IMAP

Pour la surveillance en temps réel de votre boîte mail :

### Gmail (IMAP)

1. Activez l'accès IMAP dans les paramètres Gmail
2. Créez un **mot de passe d'application** :
   - Allez dans *Compte Google → Sécurité → Mots de passe des applications*
   - Générez un mot de passe pour « Mail »
3. Dans MailGuard, page *Paramètres* :
   - Protocole : `IMAP`
   - Adresse : votre adresse Gmail
   - Mot de passe : le mot de passe d'application (16 caractères)
   - Serveur : `imap.gmail.com`
   - Port : `993`

### Outlook / Microsoft 365 (Graph API)

1. Enregistrez une application dans Azure AD
2. Dans MailGuard, page *Paramètres* :
   - Protocole : `Graph`
   - Tenant ID, Client ID, Client Secret

### Autre fournisseur (IMAP/POP3)

Renseignez le serveur et le port IMAP/POP3 de votre fournisseur.

> 🔒 Les mots de passe d'application et secrets clients sont **chiffrés** avec Fernet (AES-128-CBC + HMAC) avant d'être stockés en base.

---

## ⚙️ Configuration Avancée

### Seuils de détection

Les seuils par défaut (configurables dans l'interface) :

| Seuil | Valeur par défaut | Description |
|-------|-------------------|-------------|
| Suspect | `0.825` | Score au-dessus duquel un email est « à surveiller » |
| Frauduleux | `0.928` | Score au-dessus duquel un email est classé frauduleux |

### Base de données

Par défaut, MailGuard utilise **SQLite** (fichier `mailguard.db`). Pour passer à MySQL ou PostgreSQL, modifiez le `.env` :

```env
# MySQL
MAILGUARD_DATABASE_URL=mysql+pymysql://user:password@localhost/mailguard

# PostgreSQL
MAILGUARD_DATABASE_URL=postgresql+psycopg2://user:password@localhost/mailguard
```

N'oubliez pas d'installer le driver correspondant :
```bash
pip install pymysql        # pour MySQL
pip install psycopg2-binary  # pour PostgreSQL
```

---

## 📁 Structure du Projet

```
mailguard_modified/
├── .streamlit/
│   └── config.toml              # Thème et config Streamlit
├── modeles_mailguard/           # Modèles ML (NON versionné)
│   ├── modeles/CANINE/          # Signal 1 — Typosquatting
│   ├── fusion_modele/           # Modèle de fusion
│   ├── s4_modele_final/         # Signal 4 — Contenu
│   └── s5_modele_final/         # Signal 5 — Authentification
├── pages/                       # Pages Streamlit multipage
│   ├── 01-06_*.py               # Pages utilisateur
│   └── 07-19_ADMIN_*.py         # Pages administrateur
├── services/                    # Couche métier
│   ├── auth_service.py          # Authentification et comptes
│   ├── database.py              # Schéma et accès BDD (SQLAlchemy)
│   ├── history_service.py       # Historique des analyses
│   ├── imap_service.py          # Connexion IMAP/POP3
│   ├── mail_providers.py        # Configuration des fournisseurs
│   ├── quarantine_service.py    # Gestion de la quarantaine
│   └── audit_service.py         # Journal d'audit
├── utils/                       # Utilitaires UI
│   ├── auth_ui.py               # Interface d'authentification
│   ├── display_result.py        # Affichage des résultats
│   └── ui_helpers.py            # Helpers UI (thème, badges…)
├── tests/                       # Tests unitaires et fonctionnels
├── app.py                       # Point d'entrée principal
├── mailguard_core.py            # Moteur de détection (5 signaux)
├── mailguard.py                 # API simplifiée
├── gmail_watcher.py             # Script de surveillance sans UI
├── config_mailguard.json        # Configuration des seuils
├── requirements.txt             # Dépendances Python
├── .env.example                 # Template des variables d'environnement
└── .gitignore                   # Fichiers exclus du versionnement
```

---

## 🧪 Tests

```bash
# Lancer tous les tests
python -m pytest tests/

# Tests spécifiques
python tests/test_auth.py        # Tests d'authentification
python tests/test_admin.py       # Tests d'administration
python tests/test_pages.py       # Tests des pages Streamlit

# Vérification avant publication
python tests/verifier_avant_publication.py

# Vérification de la logique métier
python tests/verifier_logique.py
```

---

## 🔧 Dépannage

### L'application ne démarre pas

```bash
# Vérifier que l'environnement virtuel est activé
# Windows :
.\.venv\Scripts\Activate.ps1
# Linux/macOS :
source .venv/bin/activate

# Vérifier les dépendances
pip install -r requirements.txt
```

### Erreur « Modèle introuvable »

Vérifiez que le dossier `modeles_mailguard/` contient tous les fichiers nécessaires (voir [Étape 5](#étape-5--placer-les-modèles-ml)).

### Erreur de base de données

```bash
# Supprimer la base et relancer (les comptes seront perdus)
rm mailguard.db
streamlit run app.py
```

### Le signal 2 ne fonctionne pas

Vérifiez votre connexion Internet. Pour travailler hors ligne :
```env
MAILGUARD_INTERNET=0
```

### Mot de passe admin oublié

Supprimez la base de données et relancez l'application. L'admin par défaut sera recréé :
```bash
rm mailguard.db
streamlit run app.py
```
Identifiants : `admin@nouvelair.com` / `Admin2024!`

---

## 📝 Résumé des commandes

```bash
# 1. Cloner
git clone https://github.com/WiemSaafi/mailguard_NOVELAIR_with_Admin.git
cd mailguard_NOVELAIR_with_Admin

# 2. Environnement virtuel
python -m venv .venv
.\.venv\Scripts\Activate.ps1    # Windows PowerShell
# OU
source .venv/bin/activate        # Linux/macOS

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configurer
cp .env.example .env

# 5. Lancer
streamlit run app.py

# 6. Ouvrir dans le navigateur
# → http://localhost:8501

# 7. Se connecter en admin
# Email    : admin@nouvelair.com
# Mot de passe : Admin2024!
```

---

## 📄 Licence

Projet développé dans le cadre d'un stage chez **Nouvelair** — Usage interne.

---

> 🛡️ **MailGuard** — Protégez vos boîtes mail contre le phishing avec l'intelligence artificielle.
