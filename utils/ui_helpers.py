"""
utils/ui_helpers.py
====================
Système de design MailGuard.

Parti pris
----------
Blanc dominant, beaucoup d'air, texte bleu nuit profond plutôt que noir. Une
bande dégradée inclinée traverse le haut de chaque page : c'est la seule
fantaisie, et elle suffit à donner une identité. Tout le reste est calme,
large et régulier.

Les couleurs sémantiques ne servent qu'à porter le risque. Aucune couleur
n'est décorative. Les emojis ont disparu des titres : c'est ce qui faisait le
plus « projet d'école ».

Les chiffres portent l'information. Le score de risque s'affiche en très
grand, en chiffres tabulaires, parce que c'est la seule chose que l'on
regarde vraiment.

IMPORTANT — compatibilité
-------------------------
Les fonctions appelées par les pages existantes conservent le même nom et la
même signature : CSS_GLOBAL, afficher_badge_decision, afficher_alerte_securite,
afficher_barre_score, afficher_cards_signaux, afficher_workflow_etapes,
gauge_plotly.
"""

import streamlit as st
import plotly.graph_objects as go

from services.quarantine_service import get_badge_info, categoriser_email

# ─────────────────────────────────────────────────────────────────────────
# Jetons
# ─────────────────────────────────────────────────────────────────────────

COULEURS = {
    "fond": "#FFFFFF",
    "section": "#F6F9FC",
    "surface": "#FFFFFF",
    "encre": "#0A2540",
    "attenue": "#425466",
    "faible": "#8792A2",
    "filet": "#E3E8EE",
    "violet": "#635BFF",
    "violet_clair": "#F0EFFF",
    "cyan": "#00D4FF",
    "rose": "#FF5996",
    "sur": "#00A868",
    "sur_clair": "#E3F8EF",
    "veille": "#FF8F00",
    "veille_clair": "#FFF4E0",
    "menace": "#E25950",
    "menace_clair": "#FDECEB",
}

TONS = {
    "LÉGITIME": ("sur", "sur_clair", "Légitime"),
    "SUSPECT": ("veille", "veille_clair", "Suspect"),
    "DANGEREUX": ("menace", "menace_clair", "Frauduleux"),
}

ENCRE_TON = {"sur": "#00704A", "veille": "#9A5B00", "menace": "#A3352E"}


def couleur_du_score(score, seuil_suspect=0.825, seuil_dangereux=0.928):
    if score >= seuil_dangereux:
        return COULEURS["menace"]
    if score >= seuil_suspect:
        return COULEURS["veille"]
    return COULEURS["sur"]


CSS_GLOBAL = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');

:root {
  --mg-fond:#FFFFFF; --mg-section:#F6F9FC; --mg-surface:#FFFFFF;
  --mg-encre:#0A2540; --mg-attenue:#425466; --mg-faible:#8792A2;
  --mg-filet:#E3E8EE;
  --mg-violet:#635BFF; --mg-violet-clair:#F0EFFF; --mg-cyan:#00D4FF; --mg-rose:#FF5996;
  --mg-sur:#00A868; --mg-sur-clair:#E3F8EF;
  --mg-veille:#FF8F00; --mg-veille-clair:#FFF4E0;
  --mg-menace:#E25950; --mg-menace-clair:#FDECEB;
  --mg-r:16px;
  --mg-ombre:0 2px 5px -1px rgba(50,50,93,.09), 0 1px 3px -1px rgba(10,37,64,.07);
  --mg-ombre-h:0 13px 27px -5px rgba(50,50,93,.15), 0 8px 16px -8px rgba(10,37,64,.16);
}

.stApp { background:var(--mg-fond); color:var(--mg-encre); }

/* Bande dégradée inclinée : la signature visuelle */
.stApp::before {
  content:""; position:absolute; inset:0 0 auto 0; height:340px; z-index:0;
  background:linear-gradient(101deg,var(--mg-cyan) 0%,var(--mg-violet) 48%,var(--mg-rose) 100%);
  transform:skewY(-7deg); transform-origin:0 0; opacity:.10; pointer-events:none;
}
.block-container { position:relative; z-index:1; padding-top:3.2rem; padding-bottom:5rem;
                   max-width:1180px; }

/* Typographie */
html, body, [class*="css"], .stApp, button, input, textarea, select {
  font-family:'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
  -webkit-font-smoothing:antialiased; font-feature-settings:'tnum' 1;
}
h1,h2,h3,h4 { color:var(--mg-encre); letter-spacing:-0.028em; }
h1 { font-size:3.1rem; font-weight:800; line-height:1.06; letter-spacing:-0.045em; }
h2 { font-size:1.6rem; font-weight:700; margin-top:.4rem; }
h3 { font-size:1.18rem; font-weight:700; }
h4 { font-size:.98rem; font-weight:700; }
p, li, .stMarkdown { color:var(--mg-attenue); line-height:1.72; }
strong, b { color:var(--mg-encre); font-weight:600; }

code, .mg-mono { font-family:'JetBrains Mono', ui-monospace, monospace; }
code { background:var(--mg-violet-clair) !important; color:#4F46E5 !important;
       border-radius:6px; padding:.1rem .42rem; font-size:.86em; font-weight:600; }

/* En-tête de page */
.mg-entete { margin-bottom:2.6rem; max-width:62ch; }
.mg-entete h1 { margin:0 0 .7rem 0; }
.mg-entete p { font-size:1.12rem; color:var(--mg-attenue); margin:0; line-height:1.6; }
.mg-degrade { background:linear-gradient(101deg,var(--mg-violet),var(--mg-rose));
  -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }
.mg-surtitre { font-size:.78rem; font-weight:700; letter-spacing:.09em;
  text-transform:uppercase; color:var(--mg-violet); margin-bottom:.7rem; }

/* Sections */
.mg-section-titre { font-size:1.45rem; font-weight:700; color:var(--mg-encre);
  letter-spacing:-.03em; margin:3rem 0 .4rem 0; }
.mg-section-intro { color:var(--mg-attenue); margin:0 0 1.4rem 0; max-width:60ch; }

/* Cartes */
.mg-carte, .mg-info-card { background:var(--mg-surface); border:1px solid var(--mg-filet);
  border-radius:var(--mg-r); padding:1.7rem 1.8rem; box-shadow:var(--mg-ombre);
  transition:box-shadow .25s ease, transform .25s ease; height:100%; }
.mg-carte:hover, .mg-info-card:hover { box-shadow:var(--mg-ombre-h); transform:translateY(-2px); }
.mg-carte h4, .mg-info-card h4 { margin:0 0 .6rem 0; }
.mg-carte p, .mg-info-card p { margin:0; font-size:.96rem; }
.mg-carte ul { margin:.5rem 0 0 0; padding-left:1.15rem; line-height:2; font-size:.96rem;
               color:var(--mg-attenue); }

/* Verdict */
.mg-verdict { background:var(--mg-surface); border:1px solid var(--mg-filet);
  border-radius:22px; padding:2.4rem 2.6rem; box-shadow:var(--mg-ombre-h);
  position:relative; overflow:hidden; }
.mg-verdict::before { content:""; position:absolute; inset:0 0 auto 0; height:4px;
  background:linear-gradient(101deg,var(--mg-c),var(--mg-c2)); }
.mg-verdict-haut { display:flex; align-items:flex-end; justify-content:space-between;
  gap:2rem; flex-wrap:wrap; }
.mg-verdict-etat { font-size:2.6rem; font-weight:800; letter-spacing:-.045em;
  color:var(--mg-c); line-height:1; }
.mg-verdict-meta { color:var(--mg-faible); font-size:.92rem; margin-top:.75rem; }
.mg-verdict-meta .mg-mono { color:var(--mg-encre); font-weight:700; }
.mg-verdict-score { text-align:right; }
.mg-verdict-chiffre { font-family:'JetBrains Mono',monospace; font-size:4.4rem; font-weight:700;
  letter-spacing:-.06em; line-height:.9; color:var(--mg-encre); }
.mg-verdict-legende { font-size:.78rem; color:var(--mg-faible); margin-top:.5rem;
  letter-spacing:.05em; text-transform:uppercase; font-weight:600; }

/* Règle de risque segmentée */
.mg-regle { display:flex; gap:3px; margin-top:2rem; }
.mg-regle-seg { height:8px; flex:1; border-radius:99px; background:var(--mg-filet); }
.mg-regle-curseur { position:relative; height:1.4rem; margin-top:.55rem; font-size:.75rem;
  color:var(--mg-faible); }
.mg-regle-curseur span { position:absolute; transform:translateX(-50%); white-space:nowrap; }
.mg-regle-curseur .actif { color:var(--mg-c); font-weight:700; }

/* Pastilles */
.mg-pastille { display:inline-flex; align-items:center; gap:.45rem; border-radius:99px;
  padding:.3rem .85rem; font-size:.82rem; font-weight:600; }
.mg-point { width:7px; height:7px; border-radius:99px; display:inline-block; }

/* Signaux */
.mg-signal { background:var(--mg-surface); border:1px solid var(--mg-filet);
  border-radius:var(--mg-r); padding:1.4rem 1.5rem; height:100%; box-shadow:var(--mg-ombre);
  transition:box-shadow .25s ease, transform .25s ease; }
.mg-signal:hover { box-shadow:var(--mg-ombre-h); transform:translateY(-2px); }
.mg-signal-titre { font-size:.95rem; font-weight:700; color:var(--mg-encre); }
.mg-signal-detail { color:var(--mg-faible); font-size:.8rem; margin-top:.3rem; line-height:1.5; }
.mg-signal-valeur { font-family:'JetBrains Mono',monospace; font-size:2.1rem; font-weight:700;
  letter-spacing:-.05em; margin-top:1rem; line-height:1; }
.mg-signal-piste { height:5px; border-radius:99px; background:var(--mg-filet); margin-top:.9rem; }
.mg-signal-jauge { height:5px; border-radius:99px; }

/* Rail de cascade */
.mg-rail { display:flex; gap:6px; margin:.4rem 0 .7rem 0; }
.mg-rail-seg { flex:1; border-radius:99px; height:6px; background:var(--mg-filet); }
.mg-rail-seg.actif { background:linear-gradient(101deg,var(--mg-violet),var(--mg-cyan)); }
.mg-rail-txt { color:var(--mg-faible); font-size:.88rem; }

/* Alertes */
.mg-alert { border-radius:var(--mg-r); padding:1.2rem 1.45rem; margin:.8rem 0;
  border:1px solid; font-size:.96rem; line-height:1.75; }
.mg-alert-danger { background:var(--mg-menace-clair); border-color:#F6C3C0; color:#A3352E; }
.mg-alert-warn   { background:var(--mg-veille-clair); border-color:#FFD99C; color:#9A5B00; }
.mg-alert-ok     { background:var(--mg-sur-clair); border-color:#A9E6CB; color:#00704A; }

/* Statistiques natives */
[data-testid="stMetric"] { background:var(--mg-surface); border:1px solid var(--mg-filet);
  border-radius:var(--mg-r); padding:1.3rem 1.5rem; box-shadow:var(--mg-ombre); }
[data-testid="stMetricValue"] { font-size:2.3rem !important; font-weight:800 !important;
  letter-spacing:-.05em; color:var(--mg-encre) !important; }
[data-testid="stMetricLabel"] { color:var(--mg-faible) !important; font-weight:600;
  font-size:.8rem !important; letter-spacing:.03em; }

/* Contrôles */
.stButton > button { border-radius:10px; font-weight:600; font-size:.95rem;
  border:1px solid var(--mg-filet); background:var(--mg-surface); color:var(--mg-encre);
  padding:.6rem 1.25rem; box-shadow:var(--mg-ombre); transition:all .2s ease; }
.stButton > button:hover { transform:translateY(-1px); box-shadow:var(--mg-ombre-h);
  border-color:var(--mg-violet); color:var(--mg-violet); }
.stButton > button[kind="primary"], .stFormSubmitButton > button {
  background:var(--mg-violet); border:1px solid var(--mg-violet); color:#fff;
  box-shadow:0 4px 10px -2px rgba(99,91,255,.5); }
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button:hover {
  background:#5449F5; color:#fff; box-shadow:0 8px 18px -4px rgba(99,91,255,.6); }
.stButton > button:focus-visible { outline:3px solid #C7C3FF; outline-offset:2px; }

.stTextInput input, .stTextArea textarea, .stNumberInput input,
.stSelectbox div[data-baseweb="select"] > div {
  border-radius:10px !important; border-color:var(--mg-filet) !important;
  background:var(--mg-surface) !important; }
.stTextInput input:focus, .stTextArea textarea:focus { border-color:var(--mg-violet) !important;
  box-shadow:0 0 0 4px rgba(99,91,255,.14) !important; }
.stTextInput label, .stTextArea label, .stSelectbox label, .stRadio label,
.stSlider label, .stCheckbox label { font-weight:600 !important; color:var(--mg-encre) !important;
  font-size:.9rem !important; }
[data-testid="stForm"] { background:var(--mg-surface); border:1px solid var(--mg-filet);
  border-radius:20px; padding:2rem 2.1rem; box-shadow:var(--mg-ombre); }

.stTabs [data-baseweb="tab-list"] { gap:.2rem; border-bottom:1px solid var(--mg-filet); }
.stTabs [data-baseweb="tab"] { font-weight:600; color:var(--mg-faible); padding:.7rem 1.1rem; }
.stTabs [aria-selected="true"] { color:var(--mg-violet) !important; }
.stTabs [data-baseweb="tab-highlight"] { background:var(--mg-violet); height:2px; }

[data-testid="stExpander"] { border:1px solid var(--mg-filet); border-radius:var(--mg-r);
  background:var(--mg-surface); box-shadow:var(--mg-ombre); }
[data-testid="stExpander"] summary { font-weight:600; color:var(--mg-encre); }
[data-testid="stDataFrame"] { border:1px solid var(--mg-filet); border-radius:var(--mg-r);
  overflow:hidden; }
.stProgress > div > div > div { background:var(--mg-violet); }
hr { border-color:var(--mg-filet) !important; margin:2.2rem 0 !important; }

/* Barre latérale */
[data-testid="stSidebar"] { background:var(--mg-section); border-right:1px solid var(--mg-filet); }
[data-testid="stSidebarNav"] a { border-radius:9px; font-weight:600; }
[data-testid="stSidebarNav"] a[aria-current="page"] { background:var(--mg-violet-clair);
  color:#4F46E5; }

@media (prefers-reduced-motion: reduce) { * { transition:none !important; animation:none !important; } }
@media (max-width: 760px) {
  h1 { font-size:2.1rem; }
  .mg-verdict { padding:1.6rem; }
  .mg-verdict-chiffre { font-size:3rem; }
  .mg-verdict-etat { font-size:1.9rem; }
  .block-container { padding-left:1rem; padding-right:1rem; }
}
</style>
"""


# ─────────────────────────────────────────────────────────────────────────
# Structure
# ─────────────────────────────────────────────────────────────────────────

def appliquer_theme():
    st.markdown(CSS_GLOBAL, unsafe_allow_html=True)


def entete_page(titre: str, sous_titre: str = "", surtitre: str = "", mot_accent: str = ""):
    """En-tête large : surtitre discret, titre d'affichage, une phrase."""
    if mot_accent and mot_accent in titre:
        titre = titre.replace(mot_accent, f'<span class="mg-degrade">{mot_accent}</span>')
    haut = f'<div class="mg-surtitre">{surtitre}</div>' if surtitre else ""
    st.markdown(
        f'<div class="mg-entete">{haut}<h1>{titre}</h1><p>{sous_titre}</p></div>',
        unsafe_allow_html=True,
    )


def titre_section(titre: str, intro: str = ""):
    corps = f'<p class="mg-section-intro">{intro}</p>' if intro else ""
    st.markdown(f'<div class="mg-section-titre">{titre}</div>{corps}', unsafe_allow_html=True)


def pastille(texte: str, ton: str = "neutre") -> str:
    palettes = {
        "sur": (COULEURS["sur_clair"], "#00704A", COULEURS["sur"]),
        "veille": (COULEURS["veille_clair"], "#9A5B00", COULEURS["veille"]),
        "menace": (COULEURS["menace_clair"], "#A3352E", COULEURS["menace"]),
        "violet": (COULEURS["violet_clair"], "#4F46E5", COULEURS["violet"]),
        "neutre": (COULEURS["section"], COULEURS["attenue"], COULEURS["faible"]),
    }
    fond, encre, point = palettes.get(ton, palettes["neutre"])
    return (f'<span class="mg-pastille" style="background:{fond};color:{encre};">'
            f'<span class="mg-point" style="background:{point};"></span>{texte}</span>')


def carte(titre: str, corps_html: str, accent: str = None):
    bordure = f'border-top:3px solid {accent};' if accent else ""
    st.markdown(f'<div class="mg-carte" style="{bordure}"><h4>{titre}</h4>{corps_html}</div>',
                unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────
# Verdict
# ─────────────────────────────────────────────────────────────────────────

def bandeau_verdict(score: float, action: str = "", domaine: str = "",
                    seuil_suspect: float = 0.825, seuil_dangereux: float = 0.928,
                    etage: int = None, etape: str = None, categorie: str = None):
    """Verdict plein cadre : état, score en très grand, règle de risque segmentée.

    etape     : étape de la cascade qui a décidé (« 0. liste noire », « 1. règle sûre », « 2. score… »)
    categorie : décision du moteur (FRAUDULEUX / SUSPECT / LÉGITIME) ; sinon déduite du score
    """
    if categorie:
        categorie = "DANGEREUX" if categorie in ("FRAUDULEUX", "DANGEREUX") else categorie
    else:
        categorie = categoriser_email(score)
    cle, _, etiquette = TONS.get(categorie, TONS["SUSPECT"])
    couleur, encre_ton = COULEURS[cle], ENCRE_TON[cle]

    # 40 segments, coloriés jusqu'à la position du score
    total = 40
    remplis = max(1, min(total, round(score * total)))
    segments = "".join(
        f'<div class="mg-regle-seg" style="background:{couleur if i < remplis else COULEURS["filet"]};'
        f'{"opacity:" + str(round(0.45 + 0.55 * (i + 1) / remplis, 2)) + ";" if i < remplis else ""}">'
        f'</div>'
        for i in range(total)
    )
    reperes = (
        f'<span style="left:0;">0</span>'
        f'<span style="left:{seuil_suspect * 100 - 6:.0f}%;">suspect {seuil_suspect:.2f}</span>'
        f'<span style="left:{seuil_dangereux * 100:.0f}%;">fraude {seuil_dangereux:.2f}</span>'
        f'<span class="actif" style="left:{max(6, min(94, score * 100)):.0f}%;top:-2.6rem;">'
        f'▼</span>'
    )

    meta = []
    if domaine:
        meta.append(f'<span class="mg-mono">{domaine}</span>')
    if etape:
        meta.append(f"décidé à l'étape « {etape} »")
    if action:
        meta.append(action)

    st.markdown(
        f'<div class="mg-verdict" style="--mg-c:{couleur};--mg-c2:{encre_ton};">'
        f'<div class="mg-verdict-haut">'
        f'<div><div class="mg-verdict-etat">{etiquette}</div>'
        f'<div class="mg-verdict-meta">{" &nbsp;·&nbsp; ".join(meta)}</div></div>'
        f'<div class="mg-verdict-score"><div class="mg-verdict-chiffre">{score:.3f}</div>'
        f'<div class="mg-verdict-legende">score de risque</div></div>'
        f'</div>'
        f'<div class="mg-regle">{segments}</div>'
        f'<div class="mg-regle-curseur">{reperes}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def rail_cascade(etage: int = None, signaux_calcules: int = None, etape: str = None):
    """Rail de la cascade en 3 segments : listes → règles sûres → score de la fusion."""
    etape = etape or ""
    rang = 0 if etape.startswith("0.") else 1 if etape.startswith("1.") else 2
    segs = "".join(f'<div class="mg-rail-seg{" actif" if k <= rang else ""}"></div>' for k in range(3))
    texte = {0: "Décidé par les listes de Nouvelair (liste noire, ou liste blanche avec domaine prouvé).",
             1: "Décidé par une règle sûre : usurpation d'un domaine Nouvelair ou imitation d'une marque.",
             2: "Décidé par le score de la fusion des cinq signaux (régression logistique)."}[rang]
    compte = f" {signaux_calcules} signaux calculés." if signaux_calcules else ""
    st.markdown(
        f'<div class="mg-rail">{segs}</div>'
        f'<div class="mg-rail-txt">{texte}{compte}</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────
# Compatibilité avec les pages existantes
# ─────────────────────────────────────────────────────────────────────────

def afficher_badge_decision(categorie: str, score: float = None):
    cle, fond, etiquette = TONS.get(categorie, TONS["SUSPECT"])
    valeur = f' <span class="mg-mono">{score:.3f}</span>' if score is not None else ""
    st.markdown(
        f'<div style="background:{COULEURS[fond]};border:1px solid {COULEURS[cle]}44;'
        f'border-radius:14px;padding:.95rem 1.35rem;font-weight:800;font-size:1.2rem;'
        f'letter-spacing:-.02em;color:{ENCRE_TON[cle]};">{etiquette}{valeur}</div>',
        unsafe_allow_html=True,
    )


def afficher_barre_score(score: float, seuil_suspect: float = 0.825, seuil_dangereux: float = 0.928):
    couleur = couleur_du_score(score, seuil_suspect, seuil_dangereux)
    st.markdown(
        f'<div class="mg-carte"><p>Score de risque</p>'
        f'<div class="mg-mono" style="font-size:2.6rem;font-weight:700;letter-spacing:-.05em;'
        f'color:{couleur};margin-top:.3rem;">{score:.3f}</div>'
        f'<div class="mg-signal-piste"><div class="mg-signal-jauge" '
        f'style="width:{max(score * 100, 2):.1f}%;background:{couleur};"></div></div></div>',
        unsafe_allow_html=True,
    )


ETIQUETTES_SIGNAUX = {
    "domaine_bert": ("S1 · Domaine", "Imitation d'une marque (CANINE)"),
    "domaine_randomforest": ("S2 · Identité", "Âge et identité du domaine"),
    "liens": ("S3 · Liens", "Règles et chemin des liens"),
    "contenu": ("S4 · Contenu", "Texte classé par multilingual-e5"),
    "authentification": ("S5 · Authentification", "SPF, DKIM, DMARC et alignement"),
}

# Seuil propre à chaque signal (choisi sur la validation : au plus 2 % de faux positifs)
SEUILS_SIGNAUX = {"domaine_bert": 0.44, "domaine_randomforest": 0.74, "liens": 0.894,
                  "contenu": 0.391, "authentification": 0.5}


def afficher_cards_signaux(scores: dict, labels: dict = None):
    items = list(scores.items())
    if not items:
        return
    for colonne, (signal, valeur) in zip(st.columns(len(items)), items):
        titre, detail = ETIQUETTES_SIGNAUX.get(signal, (signal, ""))
        if labels and signal in labels:
            titre = labels[signal]
        if valeur is None:
            couleur, affichage, largeur = COULEURS["faible"], "n/a", 0.0
            detail = "Signal muet (vaut 0)"
        else:
            seuil = SEUILS_SIGNAUX.get(signal, 0.5)
            couleur = (COULEURS["menace"] if valeur >= seuil
                       else COULEURS["veille"] if valeur >= seuil / 2 else COULEURS["sur"])
            affichage, largeur = f"{valeur:.2f}", max(valeur * 100, 2.0)
        with colonne:
            st.markdown(
                f'<div class="mg-signal"><div class="mg-signal-titre">{titre}</div>'
                f'<div class="mg-signal-detail">{detail}</div>'
                f'<div class="mg-signal-valeur" style="color:{couleur};">{affichage}</div>'
                f'<div class="mg-signal-piste"><div class="mg-signal-jauge" '
                f'style="width:{largeur:.1f}%;background:{couleur};"></div></div></div>',
                unsafe_allow_html=True,
            )


def afficher_alerte_securite(domaine: str, score: float, action: str, sujet: str = "",
                             categorie: str = None):
    if categorie:
        categorie = "DANGEREUX" if categorie in ("FRAUDULEUX", "DANGEREUX") else categorie
    else:
        categorie = categoriser_email(score)
    if categorie == "LÉGITIME":
        return
    css = "mg-alert-danger" if categorie == "DANGEREUX" else "mg-alert-warn"
    titre = ("Message frauduleux, écarté de la boîte de réception"
             if categorie == "DANGEREUX" else "Message suspect, à ouvrir avec précaution")
    ligne_sujet = f"<br>Objet : {sujet}" if sujet else ""
    st.markdown(
        f'<div class="mg-alert {css}"><b>{titre}</b>'
        f'<br>Expéditeur : <span class="mg-mono">{domaine}</span>{ligne_sujet}'
        f'<br>Score de risque : <span class="mg-mono">{score:.3f}</span>'
        f'<br>Action : {action}</div>',
        unsafe_allow_html=True,
    )


def afficher_workflow_etapes(etapes_completees: list):
    etapes = ["Réception du message", "Analyse du domaine", "Analyse du contenu",
              "Analyse des liens", "Authentification SPF, DKIM, DMARC",
              "Identité du domaine (RDAP, certificats)", "Fusion des cinq signaux", "Décision"]
    for etape in etapes:
        fait = any(etape.lower()[:10] in e.lower() for e in etapes_completees)
        couleur = COULEURS["sur"] if fait else COULEURS["faible"]
        st.markdown(
            f'<div style="color:{couleur};padding:.18rem 0;font-size:.93rem;">'
            f'{"●" if fait else "○"}&nbsp;&nbsp;{etape}</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────
# Graphiques
# ─────────────────────────────────────────────────────────────────────────

PALETTE_DECISION = {
    "LÉGITIME": COULEURS["sur"],
    "SUSPECT": COULEURS["veille"],
    "DANGEREUX": COULEURS["menace"],
}


def mise_en_page_plotly(fig, hauteur: int = 330, legende: bool = True):
    fig.update_layout(
        height=hauteur, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"color": COULEURS["encre"], "family": "Inter, sans-serif", "size": 13},
        showlegend=legende, legend={"font": {"color": COULEURS["faible"]}},
        margin=dict(l=10, r=10, t=10, b=10),
    )
    for axe in (fig.update_xaxes, fig.update_yaxes):
        axe(gridcolor=COULEURS["filet"], color=COULEURS["faible"],
            linecolor=COULEURS["filet"], zerolinecolor=COULEURS["filet"])
    return fig


def gauge_plotly(score: float, seuil_suspect: float = 0.825, seuil_dangereux: float = 0.928) -> go.Figure:
    couleur = couleur_du_score(score, seuil_suspect, seuil_dangereux)
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=score,
        number={"valueformat": ".3f", "font": {"size": 32, "color": couleur}},
        gauge={"axis": {"range": [0, 1], "tickcolor": COULEURS["filet"],
                        "tickfont": {"color": COULEURS["faible"], "size": 11}},
               "bar": {"color": couleur, "thickness": 0.3},
               "bgcolor": COULEURS["section"], "borderwidth": 0,
               "steps": [
                   {"range": [0, seuil_suspect], "color": COULEURS["sur_clair"]},
                   {"range": [seuil_suspect, seuil_dangereux], "color": COULEURS["veille_clair"]},
                   {"range": [seuil_dangereux, 1], "color": COULEURS["menace_clair"]}]},
    ))
    fig.update_layout(height=230, margin=dict(l=20, r=20, t=10, b=10),
                      paper_bgcolor="rgba(0,0,0,0)",
                      font={"color": COULEURS["encre"], "family": "Inter, sans-serif"})
    return fig


# ═════════════════════════════════════════════════════════════════════════
# Composants signature
# ═════════════════════════════════════════════════════════════════════════
#
# Trois idées propres à MailGuard, pas des ornements génériques.
#
#   1. Le comparateur de caractères. Tout le projet repose sur un domaine qui
#      diffère d'une seule lettre. Personne ne montre jamais cette lettre.
#      Ici elle est isolée, alignée sous son sosie, et signalée.
#
#   2. La barre de construction du score. Au lieu de cinq scores côte à côte,
#      une seule barre où chaque signal apporte sa contribution réelle
#      (score × poids). On voit la décision s'assembler, et où elle franchit
#      le seuil.
#
#   3. L'anatomie du message. L'email est redessiné comme un objet, avec les
#      pièces à conviction annotées : l'expéditeur, et surtout l'écart entre
#      ce qu'un lien annonce et l'endroit où il mène.

import difflib

CSS_SIGNATURE = """
<style>
/* ── 1. Comparateur de caractères ───────────────────────────────── */
.mg-diff { display:flex; flex-direction:column; gap:.35rem; }
.mg-diff-ligne { display:flex; align-items:center; gap:.9rem; }
.mg-diff-etiquette { font-size:.72rem; color:var(--mg-faible); width:88px;
  text-align:right; font-weight:600; letter-spacing:.03em; flex-shrink:0; }
.mg-diff-suite { display:flex; gap:3px; }
.mg-diff-c { font-family:'JetBrains Mono',monospace; font-size:1.02rem; font-weight:700;
  width:1.55rem; height:2.05rem; display:grid; place-items:center; border-radius:7px;
  background:var(--mg-section); color:var(--mg-attenue); }
.mg-diff-c.vide { background:transparent; }
.mg-diff-c.egal { background:var(--mg-section); }
.mg-diff-c.faute { background:var(--mg-menace); color:#fff;
  box-shadow:0 4px 12px -3px rgba(226,89,80,.65); animation:mg-pop .45s ease-out backwards; }
.mg-diff-c.faute:nth-child(n) { animation-delay:.25s; }
@keyframes mg-pop { from { transform:scale(.5); opacity:0; } }
.mg-diff-verdict { margin-top:.9rem; font-size:.9rem; }

/* ── 2. Barre de construction du score ──────────────────────────── */
.mg-build { position:relative; margin:.4rem 0 0 0; }
.mg-build-barre { display:flex; height:44px; border-radius:12px; overflow:hidden;
  background:var(--mg-section); border:1px solid var(--mg-filet); }
.mg-build-part { display:grid; place-items:center; font-size:.72rem; font-weight:700;
  color:#fff; overflow:hidden; white-space:nowrap;
  animation:mg-pousse .7s cubic-bezier(.2,.85,.25,1) backwards; }
@keyframes mg-pousse { from { flex-basis:0 !important; } }
.mg-build-seuil { position:absolute; top:-6px; bottom:-6px; width:2px;
  background:var(--mg-encre); opacity:.35; }
.mg-build-seuil::after { content:attr(data-libelle); position:absolute; top:-1.35rem; left:50%;
  transform:translateX(-50%); font-size:.68rem; color:var(--mg-faible); white-space:nowrap; }
.mg-build-legende { display:flex; flex-wrap:wrap; gap:.4rem 1.1rem; margin-top:1.5rem; }
.mg-build-item { display:flex; align-items:center; gap:.45rem; font-size:.82rem;
  color:var(--mg-attenue); }
.mg-build-carre { width:10px; height:10px; border-radius:3px; flex-shrink:0; }
.mg-build-val { font-family:'JetBrains Mono',monospace; font-weight:700; color:var(--mg-encre); }

/* ── 3. Anatomie du message ─────────────────────────────────────── */
.mg-mail { background:var(--mg-surface); border:1px solid var(--mg-filet); border-radius:18px;
  overflow:hidden; box-shadow:var(--mg-ombre); }
.mg-mail-tete { padding:1.2rem 1.5rem; border-bottom:1px solid var(--mg-filet);
  background:var(--mg-section); }
.mg-mail-de { font-size:.75rem; color:var(--mg-faible); font-weight:600; letter-spacing:.04em; }
.mg-mail-adresse { font-family:'JetBrains Mono',monospace; font-size:1rem; font-weight:700;
  margin-top:.2rem; }
.mg-mail-objet { font-size:1.12rem; font-weight:700; color:var(--mg-encre); margin-top:.7rem;
  letter-spacing:-.02em; }
.mg-mail-corps { padding:1.3rem 1.5rem; font-size:.94rem; color:var(--mg-attenue);
  white-space:pre-wrap; line-height:1.7; max-height:190px; overflow:auto; }
.mg-mail-liens { border-top:1px solid var(--mg-filet); padding:1.1rem 1.5rem; }
.mg-lien { display:flex; align-items:center; gap:.8rem; flex-wrap:wrap; padding:.6rem 0; }
.mg-lien + .mg-lien { border-top:1px dashed var(--mg-filet); }
.mg-lien-affiche { font-size:.9rem; font-weight:600; color:var(--mg-encre); }
.mg-lien-fleche { color:var(--mg-faible); font-size:1.05rem; }
.mg-lien-cible { font-family:'JetBrains Mono',monospace; font-size:.85rem;
  padding:.2rem .55rem; border-radius:7px; }
.mg-lien-cible.ok { background:var(--mg-sur-clair); color:#00704A; }
.mg-lien-cible.ko { background:var(--mg-menace-clair); color:#A3352E; font-weight:700; }
.mg-etiq { font-size:.7rem; font-weight:700; padding:.15rem .5rem; border-radius:99px;
  letter-spacing:.03em; }

@media (prefers-reduced-motion: reduce) {
  .mg-diff-c.faute, .mg-build-part { animation:none !important; }
}
</style>
"""


def appliquer_signature():
    """CSS des trois composants signature. À appeler après appliquer_theme()."""
    st.markdown(CSS_SIGNATURE, unsafe_allow_html=True)


def comparateur_domaines(domaine: str, reference: str, distance: float = None):
    """Aligne le domaine analysé sous le domaine de confiance, caractère par
    caractère, et met en évidence ceux qui diffèrent.

    C'est le cœur du projet rendu visible : « nouvelairr.com » ne trahit sa
    nature qu'au dixième caractère.
    """
    if not domaine or not reference:
        return

    haut, bas, fautes = [], [], 0
    matcher = difflib.SequenceMatcher(None, reference, domaine)
    for operation, i1, i2, j1, j2 in matcher.get_opcodes():
        if operation == "equal":
            for a, b in zip(reference[i1:i2], domaine[j1:j2]):
                haut.append((a, "egal"))
                bas.append((b, "egal"))
        else:
            fautes += max(i2 - i1, j2 - j1)
            gauche, droite = reference[i1:i2], domaine[j1:j2]
            for k in range(max(len(gauche), len(droite))):
                haut.append((gauche[k] if k < len(gauche) else " ",
                             "egal" if k < len(gauche) else "vide"))
                bas.append((droite[k] if k < len(droite) else " ",
                            "faute" if k < len(droite) else "vide"))

    def suite(chars):
        return "".join(
            f'<div class="mg-diff-c {classe}">{c if c.strip() else "&nbsp;"}</div>'
            for c, classe in chars
        )

    if fautes == 0:
        verdict = (f'<span style="color:{COULEURS["sur"]};font-weight:700;">'
                   f'Correspondance exacte avec un domaine de confiance.</span>')
    elif fautes <= 3:
        mot = "caractère diffère" if fautes == 1 else "caractères diffèrent"
        verdict = (f'<span style="color:{COULEURS["menace"]};font-weight:700;">'
                   f'{fautes} {mot} du domaine officiel.</span> '
                   f'<span style="color:{COULEURS["attenue"]};">Assez peu pour tromper '
                   f'un lecteur pressé, assez pour mener ailleurs.</span>')
    else:
        marque = reference.split(".")[0]
        verdict = (f'<span style="color:{COULEURS["menace"]};font-weight:700;">'
                   f'Le nom reprend la marque « {marque} » en y ajoutant des mots.</span> '
                   f'<span style="color:{COULEURS["attenue"]};">C\'est du combosquatting : le domaine '
                   f'n\'appartient pas à la marque, même s\'il en porte le nom.</span>')

    mesure = ""
    if distance is not None:
        mesure = (f'<div style="margin-top:.5rem;font-size:.82rem;color:{COULEURS["faible"]};">'
                  f'Score d\'imitation mesuré par CANINE : '
                  f'<span class="mg-mono" style="color:{COULEURS["encre"]};font-weight:700;">'
                  f'{1 - distance:.3f}</span> (alerte à partir de 0,44)</div>')

    st.markdown(
        f'<div class="mg-carte"><h4>Le domaine, caractère par caractère</h4>'
        f'<div class="mg-diff" style="margin-top:1rem;">'
        f'<div class="mg-diff-ligne"><div class="mg-diff-etiquette">officiel</div>'
        f'<div class="mg-diff-suite">{suite(haut)}</div></div>'
        f'<div class="mg-diff-ligne"><div class="mg-diff-etiquette">reçu</div>'
        f'<div class="mg-diff-suite">{suite(bas)}</div></div></div>'
        f'<div class="mg-diff-verdict">{verdict}</div>{mesure}</div>',
        unsafe_allow_html=True,
    )


COULEUR_SIGNAL = {
    "authentification": "#635BFF",
    "contenu": "#00D4FF",
    "domaine_randomforest": "#FF5996",
    "liens": "#FF8F00",
    "domaine_bert": "#00A868",
}

NOM_SIGNAL = {
    "authentification": "S5 Authentification",
    "contenu": "S4 Contenu",
    "domaine_randomforest": "S2 Identité",
    "liens": "S3 Liens",
    "domaine_bert": "S1 Domaine",
}


def barre_construction(scores: dict, poids: dict, score_final: float,
                       seuil_suspect: float = 0.825, seuil_dangereux: float = 0.928):
    """Montre le score en train de s'assembler.

    Chaque signal occupe une largeur égale à sa contribution réelle,
    c'est-à-dire son score multiplié par son poids. Si un court-circuit a
    relevé le score au-delà de la somme pondérée, l'écart apparaît comme un
    segment distinct : c'est la règle de sécurité qui a pris la main.
    """
    parts, legende, cumul = [], [], 0.0

    for signal, poids_signal in sorted(poids.items(), key=lambda kv: -kv[1]):
        valeur = scores.get(signal)
        if valeur is None:
            continue
        contribution = valeur * poids_signal
        cumul += contribution
        couleur = COULEUR_SIGNAL.get(signal, COULEURS["faible"])
        nom = NOM_SIGNAL.get(signal, signal)
        if contribution > 0.001:
            largeur = contribution * 100
            texte = f"{contribution:.3f}" if largeur > 9 else ""
            parts.append(
                f'<div class="mg-build-part" style="flex:0 0 {largeur:.2f}%;'
                f'background:{couleur};">{texte}</div>'
            )
        legende.append(
            f'<div class="mg-build-item">'
            f'<span class="mg-build-carre" style="background:{couleur};"></span>'
            f'{nom} <span class="mg-build-val">{contribution:.3f}</span>'
            f'<span style="color:{COULEURS["faible"]};">({valeur:.2f} × {poids_signal:.3f})</span>'
            f'</div>'
        )

    court_circuit = max(0.0, score_final - cumul)
    if court_circuit > 0.005:
        parts.append(
            f'<div class="mg-build-part" style="flex:0 0 {court_circuit * 100:.2f}%;'
            f'background:repeating-linear-gradient(135deg,{COULEURS["menace"]},'
            f'{COULEURS["menace"]} 6px,#C4453D 6px,#C4453D 12px);">'
            f'{f"{court_circuit:.3f}" if court_circuit > 0.09 else ""}</div>'
        )
        legende.append(
            f'<div class="mg-build-item">'
            f'<span class="mg-build-carre" style="background:repeating-linear-gradient('
            f'135deg,{COULEURS["menace"]},{COULEURS["menace"]} 3px,#C4453D 3px,#C4453D 6px);">'
            f'</span>Règle de sécurité '
            f'<span class="mg-build-val">{court_circuit:.3f}</span></div>'
        )

    reste = max(0.0, 1.0 - max(score_final, cumul))
    if reste > 0:
        parts.append(f'<div class="mg-build-part" style="flex:0 0 {reste * 100:.2f}%;"></div>')

    seuils = "".join(
        f'<div class="mg-build-seuil" data-libelle="{libelle} {s:.2f}" '
        f'style="left:{s * 100:.2f}%;"></div>'
        for s, libelle in ((seuil_suspect, "suspect"), (seuil_dangereux, "fraude"))
    )

    st.markdown(
        f'<div class="mg-carte"><h4>Comment le score a été assemblé</h4>'
        f'<p style="margin-bottom:1.6rem;">Chaque signal pèse à hauteur de son score '
        f'multiplié par son poids. La barre est la somme, les repères sont les seuils.</p>'
        f'<div class="mg-build"><div class="mg-build-barre">{"".join(parts)}</div>{seuils}</div>'
        f'<div class="mg-build-legende">{"".join(legende)}</div></div>',
        unsafe_allow_html=True,
    )


def anatomie_message(domaine: str, sujet: str, texte: str, liens: list,
                     domaine_suspect: bool = False):
    """Redessine l'email comme un objet, avec les pièces à conviction annotées.

    Le plus parlant est la colonne des liens : ce que le message annonce à
    gauche, l'endroit où il mène réellement à droite.
    """
    etiquette_exp = (
        f'<span class="mg-etiq" style="background:{COULEURS["menace_clair"]};color:#A3352E;">'
        f'expéditeur douteux</span>' if domaine_suspect else
        f'<span class="mg-etiq" style="background:{COULEURS["sur_clair"]};color:#00704A;">'
        f'expéditeur connu</span>'
    )
    couleur_adresse = COULEURS["menace"] if domaine_suspect else COULEURS["encre"]

    bloc_liens = ""
    if liens:
        rangs = []
        for lien in liens:
            affiche = lien.get("texte_affiche") or lien.get("texte") or "(sans texte)"
            cible = lien.get("url_reelle") or lien.get("url") or "inconnue"
            suspect = bool(lien.get("suspect"))
            rangs.append(
                f'<div class="mg-lien">'
                f'<span class="mg-lien-affiche">« {affiche} »</span>'
                f'<span class="mg-lien-fleche">mène en réalité à</span>'
                f'<span class="mg-lien-cible {"ko" if suspect else "ok"}">{cible}</span>'
                f'</div>'
            )
        bloc_liens = f'<div class="mg-mail-liens">{"".join(rangs)}</div>'

    apercu = (texte or "(message sans texte)").strip()
    if len(apercu) > 700:
        apercu = apercu[:700] + " […]"

    st.markdown(
        f'<div class="mg-mail">'
        f'<div class="mg-mail-tete">'
        f'<div class="mg-mail-de">DE &nbsp;{etiquette_exp}</div>'
        f'<div class="mg-mail-adresse" style="color:{couleur_adresse};">{domaine}</div>'
        f'<div class="mg-mail-objet">{sujet or "(sans objet)"}</div></div>'
        f'<div class="mg-mail-corps">{apercu}</div>'
        f'{bloc_liens}</div>',
        unsafe_allow_html=True,
    )
