"""
pages/01_🏠_Accueil.py
========================
Explique le fonctionnement du filtre : les cinq signaux, la fusion apprise,
la cascade de décision, les trois issues possibles, et les limites assumées.

Page entièrement descriptive : aucune logique métier n'y figure.
"""

import pandas as pd
import streamlit as st

from utils.auth_ui import exiger_connexion, id_utilisateur
from utils.ui_helpers import (
    COULEURS,
    appliquer_signature,
    appliquer_theme,
    entete_page,
    titre_section,
)

appliquer_theme()
appliquer_signature()
exiger_connexion()

entete_page(
    titre="Cinq signaux, une fusion, deux seuils",
    sous_titre="Rien n'est mis en quarantaine sans que la raison soit affichée. "
               "Voici comment la décision se prend, du message reçu à l'action appliquée.",
    surtitre="Fonctionnement",
    mot_accent="un score",
)

# ─── Les cinq signaux ─────────────────────────────────────────────────────────
titre_section(
    "Les cinq signaux",
    "Chaque signal a son propre modèle, choisi pour le type de donnée qu'il lit, "
    "et son propre seuil, choisi sur la validation (au plus 2 % de faux positifs).",
)

SIGNAUX = [
    ("S1 · Domaine expéditeur", COULEURS["sur"],
     "CANINE lit le nom de domaine caractère par caractère et repère l'imitation "
     "d'une marque protégée : <span class='mg-mono'>nouvelairr.com</span>, "
     "<span class='mg-mono'>nouve1air.com</span>.",
     "CANINE · seuil 0,44"),
    ("S2 · Identité du domaine", COULEURS["rose"],
     "Âge au registre (RDAP) et historique des certificats (crt.sh), lus au jour du message. "
     "Un domaine de moins de 30 jours déclenche une alerte.",
     "Gradient Boosting monotone · seuil 0,74"),
    ("S3 · Liens", COULEURS["veille"],
     "Règles sûres (adresse IP, @ dans l'URL…), puis S1 et S2 appliqués au domaine "
     "du lien, puis un modèle qui lit le chemin de l'URL.",
     "règles + Gradient Boosting · seuil 0,894"),
    ("S4 · Contenu", COULEURS["cyan"],
     "multilingual-e5 transforme le texte en vecteur (français, anglais, arabe) ; "
     "une régression logistique reconnaît les tournures du phishing.",
     "e5 gelé + régression logistique · seuil 0,391"),
    ("S5 · Authentification", COULEURS["violet"],
     "SPF, DKIM, DMARC et surtout leur ALIGNEMENT avec le domaine affiché. "
     "Un message « Nouvelair » qui échoue DMARC est bloqué d'office.",
     "Gradient Boosting · 17 indices + veto Nouvelair"),
    ("Fusion", COULEURS["encre"],
     "Une régression logistique combine les cinq signaux avec des poids appris : "
     "authentification 5,55, contenu 4,81, chemin des liens 1,64, identité 1,61…",
     "suspect ≥ 0,825 · frauduleux ≥ 0,928"),
]

for debut in (0, 3):
    for colonne, (titre, accent, texte, cadence) in zip(st.columns(3, gap="medium"),
                                                        SIGNAUX[debut:debut + 3]):
        with colonne:
            st.markdown(
                f'<div class="mg-carte" style="border-top:3px solid {accent};">'
                f'<h4>{titre}</h4><p>{texte}</p>'
                f'<p style="margin-top:.9rem;font-size:.78rem;color:{accent};'
                f'font-weight:700;letter-spacing:.04em;">{cadence.upper()}</p></div>',
                unsafe_allow_html=True,
            )
    st.write("")

# ─── La cascade ───────────────────────────────────────────────────────────────
titre_section(
    "La cascade de décision",
    "Le message passe par quatre étapes, dans cet ordre. Dès qu'une étape décide, "
    "la décision est prise et la raison est affichée.",
)

gauche, droite = st.columns(2, gap="large")

with gauche:
    st.markdown(
        '<div class="mg-carte">'
        '<h4>0. Les listes de Nouvelair</h4>'
        '<p>Un expéditeur de la liste noire est frauduleux. Un partenaire de la liste '
        'blanche n\'est accepté que si son domaine est <b>prouvé</b> (DKIM aligné, ou SPF '
        'réussi et aligné) : un usurpateur ne peut donc pas profiter de la liste blanche.</p>'
        '<h4 style="margin-top:1.4rem;">1. Les règles sûres</h4>'
        '<ul><li>Un message au nom de Nouvelair qui échoue DMARC (usurpation).</li>'
        '<li>Un domaine expéditeur qui imite une marque protégée (S1 ≥ 0,44).</li></ul>'
        '</div>',
        unsafe_allow_html=True,
    )

with droite:
    st.markdown(
        '<div class="mg-carte">'
        '<h4>2. Le score de la fusion</h4>'
        '<p>Les cinq signaux sont combinés par la régression logistique. Le score est '
        'comparé aux deux seuils appris : 0,825 (suspect) et 0,928 (frauduleux).</p>'
        '<h4 style="margin-top:1.4rem;">3. Les raisons</h4>'
        '<p>Chaque décision est accompagnée de ses raisons en français : marque imitée, '
        'âge du domaine, lien au chemin suspect, texte de phishing, échec d\'authentification.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

# ─── Les trois issues ─────────────────────────────────────────────────────────
seuil_suspect = st.session_state.get("seuil_suspect", 0.825)
seuil_dangereux = st.session_state.get("seuil_dangereux", 0.928)

titre_section("Les trois issues possibles",
              "Les seuils sont modifiables depuis la page Paramètres.")

ISSUES = [
    ("Légitime", f"score inférieur à {seuil_suspect:.3f}",
     "Le message reste dans la boîte de réception. Rien n'est signalé à l'utilisateur.",
     "sur"),
    ("Suspect", f"entre {seuil_suspect:.3f} et {seuil_dangereux:.3f}",
     "Le message part dans MailGuard/Suspects, consultable à tout moment.", "veille"),
    ("Frauduleux", f"score ≥ {seuil_dangereux:.3f}, liste noire ou règle sûre",
     "Le message est déplacé dans MailGuard/Quarantaine et une alerte s'affiche.", "menace"),
]

for colonne, (titre, plage, effet, ton) in zip(st.columns(3, gap="medium"), ISSUES):
    with colonne:
        st.markdown(
            f'<div class="mg-carte" style="border-top:3px solid {COULEURS[ton]};">'
            f'<h4 style="color:{COULEURS[ton]};font-size:1.3rem;">{titre}</h4>'
            f'<p class="mg-mono" style="font-size:.82rem;color:{COULEURS["faible"]};'
            f'margin-top:.2rem;">{plage}</p>'
            f'<p style="margin-top:.8rem;">{effet}</p></div>',
            unsafe_allow_html=True,
        )

# ─── Détail technique ─────────────────────────────────────────────────────────
titre_section("Le détail technique")

with st.expander("Poids appris, modèles déployés et limites connues"):
    st.markdown("**Poids appris par la fusion (régression logistique)**")
    st.dataframe(
        pd.DataFrame([
            {"Indice": "S5 authentification", "Poids": 5.55},
            {"Indice": "S4 texte (e5)", "Poids": 4.81},
            {"Indice": "S3 chemin des liens", "Poids": 1.64},
            {"Indice": "S2 domaine jeune", "Poids": 1.61},
            {"Indice": "S3 domaine du lien jeune", "Poids": 1.23},
            {"Indice": "S1 imitation (CANINE)", "Poids": 0.24},
            {"Indice": "S3 lien douteux (raccourcisseur…)", "Poids": 0.15},
            {"Indice": "S3 règle forte", "Poids": 0.12},
            {"Indice": "S3 lien imite une marque", "Poids": -0.62},
            {"Indice": "Constante", "Poids": -3.99},
        ]),
        width="stretch", hide_index=True,
    )
    st.caption("Le poids faible de S1 ne veut pas dire qu'il est inutile : une imitation "
               "avérée est décidée avant la fusion, par une règle sûre.")

    st.markdown("**Modèles déployés**")
    st.markdown(
        "- S1 : `google/canine-s` affiné sur des domaines (imitation de marques), 516 Mo\n"
        "- S2 : Gradient Boosting à contraintes monotones (âge RDAP, certificats crt.sh)\n"
        "- S3 : règles + Gradient Boosting sur le chemin des URL\n"
        "- S4 : `intfloat/multilingual-e5-base` gelé + régression logistique\n"
        "- S5 : Gradient Boosting sur 17 indices d'en-têtes + veto DMARC Nouvelair\n"
        "- Fusion : régression logistique, seuils choisis sur la validation"
    )

    st.markdown("**Méthode et limites assumées**")
    st.markdown(
        "Les seuils sont choisis sur un jeu de validation séparé, découpé par expéditeur "
        "(GroupKFold) pour éviter la fuite de données : un même expéditeur ne se trouve "
        "jamais à la fois dans l'entraînement et dans le test.\n\n"
        "S2 dépend des registres publics (RDAP, crt.sh) : s'ils ne répondent pas, le "
        "signal est muet et vaut 0, il ne charge pas le message. S4 lit au plus 256 jetons : "
        "un texte très long n'est lu qu'en partie."
    )
