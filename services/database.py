"""
services/database.py
=====================
Schéma relationnel et accès à la base de données.

Choix du moteur
---------------
SQLite par défaut : la base tient dans un fichier, ne demande aucun serveur, et
respecte les propriétés ACID. C'est le bon choix pour une application installée
sur un poste.

Le passage à MySQL ou PostgreSQL ne demande qu'une variable d'environnement,
parce que tout l'accès aux données passe par SQLAlchemy et qu'aucune requête
n'utilise de syntaxe propre à un moteur :

    MAILGUARD_DATABASE_URL=mysql+pymysql://user:motdepasse@serveur/mailguard
    MAILGUARD_DATABASE_URL=postgresql+psycopg2://user:motdepasse@serveur/mailguard

Le schéma
---------
Tables principales, en troisième forme normale :

    utilisateurs ──1:1── identifiants_gmail
         │       └─1:1── preferences
         └───────1:N──── analyses ──1:N── scores_signaux
                             ├──1:1── qualifications   (avis de l'administrateur)
                             └──1:1── etats_alertes    (vue / résolue)

Tables d'administration : administrateurs, domains_confiance,
domains_frauduleux, journal_audit.

Les scores des cinq signaux sont stockés en lignes plutôt qu'en colonnes. Cela
coûte une jointure, mais permet d'ajouter un sixième signal sans modifier le
schéma, et surtout d'agréger en SQL : la moyenne par signal du tableau de bord
devient un simple GROUP BY au lieu d'un parcours en Python.

Le détail brut de chaque analyse, dont la structure varie selon les signaux
calculés, est conservé dans une colonne JSON. C'est un choix assumé : ce contenu
n'est jamais interrogé, seulement réaffiché tel quel.

Intégrité
---------
Les clés étrangères sont déclarées avec suppression en cascade, et activées
explicitement sur SQLite où elles sont désactivées par défaut. Supprimer un
compte supprime donc ses analyses, ses scores, ses préférences et ses
identifiants Gmail, sans laisser d'orphelins.
"""

import json
import os
from datetime import datetime

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Index, Integer, String, Text,
    create_engine, event, func,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHEMIN_SQLITE = os.path.join(BASE_DIR, "mailguard.db")
URL_PAR_DEFAUT = f"sqlite:///{CHEMIN_SQLITE}"


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────────────────
# Tables
# ─────────────────────────────────────────────────────────────────────────

class Utilisateur(Base):
    __tablename__ = "utilisateurs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    identifiant = Column(String(32), unique=True, nullable=False, index=True)
    nom = Column(String(120), nullable=False, default="")

    # Empreinte PBKDF2-HMAC-SHA256 et sel, encodés en base64.
    # Le mot de passe lui-même n'est jamais stocké.
    empreinte = Column(String(64), nullable=False)
    sel = Column(String(32), nullable=False)

    cree_le = Column(DateTime, nullable=False, default=datetime.now)
    derniere_connexion = Column(DateTime, nullable=True)

    # Rôle : 'user' (défaut) ou 'admin'
    role = Column(String(16), nullable=False, default="user")
    # Statut : 'pending' (en attente de validation admin) ou 'active'
    statut = Column(String(16), nullable=False, default="pending")

    gmail = relationship("IdentifiantGmail", back_populates="utilisateur",
                         uselist=False, cascade="all, delete-orphan")
    preferences = relationship("Preference", back_populates="utilisateur",
                               uselist=False, cascade="all, delete-orphan")
    analyses = relationship("Analyse", back_populates="utilisateur",
                            cascade="all, delete-orphan",
                            passive_deletes=True)


class Administrateur(Base):
    """Table des comptes administrateurs MailGuard.

    Séparée de la table utilisateurs pour un cloisonnement clair des droits.
    Un admin peut valider des comptes utilisateurs et accéder au Security Center.
    """
    __tablename__ = "administrateurs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    identifiant = Column(String(32), unique=True, nullable=False, index=True)
    nom = Column(String(120), nullable=False, default="")

    empreinte = Column(String(64), nullable=False)
    sel = Column(String(32), nullable=False)

    cree_le = Column(DateTime, nullable=False, default=datetime.now)
    derniere_connexion = Column(DateTime, nullable=True)
    # 'active' ou 'suspended'
    statut = Column(String(16), nullable=False, default="active")


class IdentifiantGmail(Base):
    """Séparé de la table des utilisateurs : ce sont des données sensibles,
    facultatives, et dont la durée de vie est indépendante du compte."""
    __tablename__ = "identifiants_gmail"

    id = Column(Integer, primary_key=True, autoincrement=True)
    utilisateur_id = Column(Integer,
                            ForeignKey("utilisateurs.id", ondelete="CASCADE"),
                            unique=True, nullable=False)
    # Protocole choisi par l'utilisateur : imap, pop3 ou graph.
    protocole = Column(String(16), nullable=False, default="imap")
    adresse = Column(String(255), nullable=False, default="")

    # IMAP et POP3
    # Chiffré avec Fernet. La clé vit dans .env, jamais en base.
    mot_de_passe_chiffre = Column(Text, nullable=False, default="")
    serveur = Column(String(255), nullable=False, default="")
    port = Column(Integer, nullable=False, default=0)

    # Microsoft Graph : le secret client est chiffré au même titre qu'un mot
    # de passe ; le locataire et l'identifiant client ne sont pas secrets.
    tenant_id = Column(String(120), nullable=False, default="")
    client_id = Column(String(120), nullable=False, default="")
    client_secret_chiffre = Column(Text, nullable=False, default="")

    maj_le = Column(DateTime, nullable=False, default=datetime.now)

    utilisateur = relationship("Utilisateur", back_populates="gmail")


class Preference(Base):
    __tablename__ = "preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    utilisateur_id = Column(Integer,
                            ForeignKey("utilisateurs.id", ondelete="CASCADE"),
                            unique=True, nullable=False)
    seuil_suspect = Column(Float, nullable=False, default=0.825)
    seuil_dangereux = Column(Float, nullable=False, default=0.928)
    action_config = Column(String(32), nullable=False, default="quarantaine")

    utilisateur = relationship("Utilisateur", back_populates="preferences")


class Analyse(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    utilisateur_id = Column(Integer,
                            ForeignKey("utilisateurs.id", ondelete="CASCADE"),
                            nullable=True, index=True)

    horodatage = Column(DateTime, nullable=False, default=datetime.now, index=True)
    domaine_expediteur = Column(String(255), nullable=False, default="", index=True)
    sujet = Column(String(500), nullable=False, default="")
    texte_apercu = Column(Text, nullable=False, default="")
    nb_liens = Column(Integer, nullable=False, default=0)

    score_final = Column(Float, nullable=False, default=0.0)
    categorie = Column(String(20), nullable=False, default="LÉGITIME", index=True)
    etage = Column(Integer, nullable=False, default=1)
    signaux_calcules = Column(Integer, nullable=False, default=4)
    duree_analyse_ms = Column(Float, nullable=False, default=0.0)

    action_appliquee = Column(String(120), nullable=False, default="aucune")
    source = Column(String(20), nullable=False, default="manuel")
    uid_imap = Column(String(64), nullable=False, default="")

    # Détail brut des signaux : structure variable, jamais interrogée en SQL.
    details_json = Column(Text, nullable=False, default="{}")
    explication = Column(Text, nullable=False, default="")

    utilisateur = relationship("Utilisateur", back_populates="analyses")
    scores = relationship("ScoreSignal", back_populates="analyse",
                          cascade="all, delete-orphan", passive_deletes=True)


class ScoreSignal(Base):
    """Un signal par ligne. Permet d'agréger en SQL et d'ajouter un signal
    sans toucher au schéma."""
    __tablename__ = "scores_signaux"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analyse_id = Column(Integer, ForeignKey("analyses.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    signal = Column(String(40), nullable=False, index=True)
    # NULL signifie « signal non calculé », par exemple la vérification réseau
    # quand la décision a été prise à l'étage 1. À ne pas confondre avec 0.0,
    # qui signifie « calculé, et favorable ».
    valeur = Column(Float, nullable=True)

    analyse = relationship("Analyse", back_populates="scores")



class DomainConfiance(Base):
    """Domaines de confiance (whitelist) — gérés par l'admin."""
    __tablename__ = "domains_confiance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    domaine = Column(String(255), unique=True, nullable=False, index=True)
    statut = Column(String(20), nullable=False, default="pending_validation")
    commentaire = Column(Text, nullable=False, default="")
    ajoute_le = Column(DateTime, nullable=False, default=datetime.now)
    valide_par_bert = Column(String(10), nullable=True)  # "oui"/"non"/None


class DomainFrauduleux(Base):
    """Domaines frauduleux (blacklist) — gérés par l'admin."""
    __tablename__ = "domains_frauduleux"

    id = Column(Integer, primary_key=True, autoincrement=True)
    domaine = Column(String(255), unique=True, nullable=False, index=True)
    raison = Column(String(255), nullable=False, default="")
    score_estime = Column(Float, nullable=False, default=0.8)
    commentaire = Column(Text, nullable=False, default="")
    statut = Column(String(20), nullable=False, default="active")
    ajoute_le = Column(DateTime, nullable=False, default=datetime.now)

class QualificationAnalyse(Base):
    """Avis d'un administrateur sur une analyse (« human in the loop »).

    Sert à mesurer les erreurs du filtre en exploitation : une analyse classée
    frauduleuse puis qualifiée « légitime » est un faux positif.
    """
    __tablename__ = "qualifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analyse_id = Column(Integer, ForeignKey("analyses.id", ondelete="CASCADE"),
                        nullable=False, unique=True, index=True)
    qualification = Column(String(20), nullable=False)          # LÉGITIME / SUSPECT / FRAUDULEUX
    commentaire = Column(Text, nullable=False, default="")
    admin = Column(String(255), nullable=False, default="")
    qualifie_le = Column(DateTime, nullable=False, default=datetime.now)


class EtatAlerte(Base):
    """Suivi d'une alerte (analyse suspecte ou frauduleuse) : nouvelle, vue, résolue."""
    __tablename__ = "etats_alertes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analyse_id = Column(Integer, ForeignKey("analyses.id", ondelete="CASCADE"),
                        nullable=False, unique=True, index=True)
    statut = Column(String(20), nullable=False, default="vue")  # vue / resolue
    admin = Column(String(255), nullable=False, default="")
    maj_le = Column(DateTime, nullable=False, default=datetime.now)


class JournalAudit(Base):
    """Journal d'audit : chaque action d'administration, horodatée, avec son auteur.

    On n'y écrit que des faits réels, au moment où l'action a lieu. Aucune ligne
    n'est jamais modifiée ni supprimée par l'application.
    """
    __tablename__ = "journal_audit"

    id = Column(Integer, primary_key=True, autoincrement=True)
    horodatage = Column(DateTime, nullable=False, default=datetime.now, index=True)
    acteur = Column(String(255), nullable=False, default="système")
    action = Column(String(40), nullable=False, index=True)
    entite_type = Column(String(40), nullable=False, default="")
    entite_id = Column(String(255), nullable=False, default="")
    details = Column(Text, nullable=False, default="")


# Valeurs de la colonne « categorie » qui signifient « frauduleux ».
# Le service de quarantaine enregistre la clé interne « DANGEREUX » ; d'anciennes
# analyses peuvent porter « FRAUDULEUX ». Les requêtes doivent accepter les deux.
CATEGORIES_FRAUDE = ("DANGEREUX", "FRAUDULEUX")


def libelle_categorie(categorie: str) -> str:
    """Nom affiché d'une catégorie enregistrée."""
    return "FRAUDULEUX" if categorie in CATEGORIES_FRAUDE else (categorie or "")


Index("ix_analyses_utilisateur_horodatage",
      Analyse.utilisateur_id, Analyse.horodatage.desc())


# ─────────────────────────────────────────────────────────────────────────
# Moteur et sessions
# ─────────────────────────────────────────────────────────────────────────

_moteur = None
_Session = None


@event.listens_for(Engine, "connect")
def _activer_cles_etrangeres(connexion, _record):
    """SQLite désactive les clés étrangères par défaut. Sans cette ligne, la
    suppression en cascade ne s'appliquerait pas et laisserait des orphelins."""
    if connexion.__class__.__module__.startswith("sqlite3"):
        curseur = connexion.cursor()
        curseur.execute("PRAGMA foreign_keys=ON")
        curseur.close()


def url_base() -> str:
    return os.getenv("MAILGUARD_DATABASE_URL", "").strip() or URL_PAR_DEFAUT


def moteur():
    global _moteur, _Session
    if _moteur is None:
        url = url_base()
        options = {"future": True}
        if url.startswith("sqlite"):
            # Streamlit sert les pages depuis plusieurs threads.
            options["connect_args"] = {"check_same_thread": False}
        _moteur = create_engine(url, **options)
        Base.metadata.create_all(_moteur)
        _ajouter_colonnes_manquantes(_moteur)
        _Session = sessionmaker(bind=_moteur, expire_on_commit=False, future=True)
    return _moteur


def _ajouter_colonnes_manquantes(moteur_actuel):
    """Migration legere : ajoute les colonnes apparues apres la creation de la base.

    Une base creee par une version anterieure ne contient pas les colonnes de
    protocole. Plutot que d'imposer une suppression de la base, on les ajoute
    a la volee. SQLite, MySQL et PostgreSQL acceptent tous ALTER TABLE ADD
    COLUMN avec une valeur par defaut.
    """
    from sqlalchemy import inspect, text

    inspecteur = inspect(moteur_actuel)
    for table in Base.metadata.tables.values():
        if not inspecteur.has_table(table.name):
            continue
        presentes = {c["name"] for c in inspecteur.get_columns(table.name)}
        for colonne in table.columns:
            if colonne.name in presentes:
                continue
            type_sql = colonne.type.compile(moteur_actuel.dialect)
            defaut = colonne.default.arg if colonne.default is not None else None
            clause = f'ALTER TABLE {table.name} ADD COLUMN {colonne.name} {type_sql}'
            if isinstance(defaut, str):
                clause += f" DEFAULT '{defaut}'"
            elif isinstance(defaut, (int, float)):
                clause += f" DEFAULT {defaut}"
            with moteur_actuel.begin() as connexion:
                connexion.execute(text(clause))


def session():
    moteur()
    return _Session()


def reinitialiser_moteur(url: str = None):
    """Utilisé par les tests pour basculer sur une base jetable."""
    global _moteur, _Session
    if _moteur is not None:
        _moteur.dispose()
    _moteur = None
    _Session = None
    if url is not None:
        os.environ["MAILGUARD_DATABASE_URL"] = url
    return moteur()


# ─────────────────────────────────────────────────────────────────────────
# Utilitaires
# ─────────────────────────────────────────────────────────────────────────

def charger_json(texte: str, defaut):
    try:
        valeur = json.loads(texte or "")
        return valeur if valeur is not None else defaut
    except (json.JSONDecodeError, TypeError):
        return defaut


def informations_base() -> dict:
    """Résumé affiché dans la page Paramètres."""
    url = url_base()
    with session() as s:
        infos = {
            "moteur": url.split("://")[0],
            "url": url if not url.startswith("sqlite") else CHEMIN_SQLITE,
            "utilisateurs": s.query(func.count(Utilisateur.id)).scalar() or 0,
            "analyses": s.query(func.count(Analyse.id)).scalar() or 0,
            "scores": s.query(func.count(ScoreSignal.id)).scalar() or 0,
        }
    if url.startswith("sqlite") and os.path.exists(CHEMIN_SQLITE):
        infos["taille_ko"] = round(os.path.getsize(CHEMIN_SQLITE) / 1024, 1)
    return infos
