"""
utils/display_result.py  (version 2 : nouveaux modèles)
=======================================================
Affichage détaillé d'un résultat d'analyse.

Ordre de lecture : le verdict, puis l'étape qui a décidé et les raisons,
puis les cinq signaux, puis le détail par onglet.

La signature de `afficher_resultat_complet` est inchangée : les pages
existantes l'appellent sans modification. Les seuils de décision sont ceux
du modèle de fusion (lus dans le résultat), et non plus 0,25 / 0,50.
"""

import pandas as pd
import streamlit as st

from services.quarantine_service import formater_age
from utils.ui_helpers import (
    COULEURS,
    afficher_cards_signaux,
    anatomie_message,
    bandeau_verdict,
    comparateur_domaines,
)

NOMS = {
    "domaine_bert": "S1 · Domaine (CANINE)",
    "domaine_randomforest": "S2 · Identité du domaine",
    "liens": "S3 · Liens",
    "contenu": "S4 · Contenu (e5)",
    "authentification": "S5 · Authentification",
}


def _etat_auth(valeur: str) -> str:
    """Vignette colorée pour un résultat SPF, DKIM ou DMARC."""
    tons = {
        "pass": (COULEURS["sur_clair"], "#00704A", "réussi"),
        "fail": (COULEURS["menace_clair"], "#A3352E", "échoué"),
    }
    fond, encre, libelle = tons.get(valeur, (COULEURS["veille_clair"], "#9A5B00", valeur))
    return (f'<div style="background:{fond};border-radius:14px;padding:.85rem 1rem;">'
            f'<div style="color:{encre};font-weight:700;font-size:1rem;">{libelle}</div>'
            f'<div style="color:{encre};opacity:.72;font-size:.76rem;margin-top:.15rem;">'
            f'résultat brut : {valeur}</div></div>')


# Couleur de la décision : la même partout (étape, raisons)
_TON = {"FRAUDULEUX": ("menace", "#A3352E", "✗"), "SUSPECT": ("veille", "#9A5B00", "⚠"),
        "LÉGITIME": ("sur", "#00704A", "✓")}


def _etape(resultat: dict):
    """Montre quelle étape de la cascade a rendu la décision (couleur = décision)."""
    etape = resultat.get("etape_decision", "")
    cle, encre, _ = _TON.get(resultat.get("categorie", "LÉGITIME"), _TON["SUSPECT"])
    etapes = [("0. Listes", etape.startswith("0.")),
              ("1. Règles sûres", etape.startswith("1.")),
              ("2. Score de la fusion", etape.startswith("2."))]
    cases = "".join(
        f'<span style="display:inline-block;padding:.35rem .8rem;margin:.15rem;border-radius:999px;'
        f'font-size:.85rem;font-weight:{700 if actif else 400};'
        f'background:{COULEURS[cle + "_clair"] if actif else "#EEF2F7"};color:{encre if actif else "#64748B"};">'
        f'{nom}</span>' for nom, actif in etapes)
    st.markdown(f'<div style="margin:.2rem 0 .4rem 0;">Étape qui a décidé : {cases}</div>', unsafe_allow_html=True)
    st.caption(etape)


def _officiel_le_plus_proche(marque, domaine, defaut):
    """Parmi les domaines officiels de la marque imitée, celui qui ressemble le plus au domaine reçu
    (ex. nouvelair.com plutôt que nouvelair.aero), pour une comparaison caractère par caractère lisible."""
    import difflib
    try:
        import mailguard_core as mg
        officiels = mg._MODELES["moteur"].texte_marque.get(marque, "").split()
    except Exception:
        officiels = []
    domaine = (domaine or "").split("@")[-1].lower()
    if not officiels or not domaine:
        return defaut
    return max(officiels, key=lambda o: difflib.SequenceMatcher(None, o, domaine).ratio())


def afficher_resultat_complet(
    resultat: dict,
    domaine: str = "",
    sujet: str = "",
    show_gauge: bool = True,
    seuil_suspect: float = 0.825,
    seuil_dangereux: float = 0.928,
    prefix: str = "",
    action: str = "",
):
    scores = resultat.get("scores_detail", {}) or {}
    details = resultat.get("details", {}) or {}
    score_final = resultat.get("score_final", 0)
    etage = resultat.get("etage", 1)
    # Les seuils viennent du modèle de fusion (0,825 et 0,928), pas des anciens réglages.
    seuil_suspect = resultat.get("seuil_suspect", seuil_suspect)
    seuil_dangereux = resultat.get("seuil_frauduleux", seuil_dangereux)
    categorie = resultat.get("categorie", "LÉGITIME")

    # ── Verdict ────────────────────────────────────────────────────────
    bandeau_verdict(
        score_final, action=action, domaine=domaine,
        seuil_suspect=seuil_suspect, seuil_dangereux=seuil_dangereux,
        etape=resultat.get("etape_decision"), categorie=categorie,
    )
    st.write("")
    _etape(resultat)

    # ── Les raisons de la décision ─────────────────────────────────────
    raisons = resultat.get("raisons", [])
    st.markdown("### Pourquoi cette décision")
    if raisons:
        cle, _, icone = _TON.get(categorie, _TON["SUSPECT"])
        for r in raisons:
            st.markdown(f'<div style="color:{COULEURS[cle]};font-size:.95rem;padding:.14rem 0;">{icone} {r}</div>',
                        unsafe_allow_html=True)
    else:
        st.markdown(f'<div style="color:{COULEURS["sur"]};font-size:.95rem;">✓ Aucun indice suspect : '
                    f'le score de la fusion reste sous le seuil {seuil_suspect:.3f}.</div>', unsafe_allow_html=True)

    # ── Le domaine, caractère par caractère (seulement en cas d'imitation) ─
    d_bert = details.get("domaine_bert", {})
    reference = _officiel_le_plus_proche(d_bert.get("marque"), domaine or d_bert.get("domaine", ""),
                                         d_bert.get("plus_proche"))
    if domaine and reference and d_bert.get("distance") is not None:
        st.write("")
        comparateur_domaines(domaine, reference, d_bert.get("distance"))

    # ── Anatomie du message ────────────────────────────────────────────
    liens_bruts = details.get("liens", [])
    if sujet or liens_bruts:
        st.write("")
        st.markdown("### Le message, pièces à conviction")
        anatomie_message(
            domaine=domaine or d_bert.get("domaine", "inconnu"),
            sujet=sujet,
            texte=resultat.get("texte_apercu", ""),
            liens=liens_bruts,
            domaine_suspect=bool(d_bert.get("score") is not None and d_bert.get("score", 0) >= d_bert.get("seuil", 0.44)),
        )

    # ── Les cinq signaux ───────────────────────────────────────────────
    if scores:
        st.write("")
        st.markdown("### Les cinq signaux")
        afficher_cards_signaux(scores)   # un signal muet (None) est affiché « muet »
    else:
        st.info("Décision prise par les listes de Nouvelair : les cinq signaux n'ont pas eu besoin d'être calculés.")

    # ── Détail par signal ──────────────────────────────────────────────
    st.write("")
    st.markdown("### Le détail, signal par signal")
    o1, o2, o3, o4, o5 = st.tabs(["S1 Domaine", "S2 Identité", "S3 Liens", "S4 Contenu", "S5 Authentification"])

    with o1:
        d = details.get("domaine_bert", {})
        if not d:
            st.info("Signal non calculé (décision prise par les listes).")
        else:
            gauche, droite = st.columns([1, 1], gap="large")
            with gauche:
                st.markdown(
                    f'<div class="mg-carte"><h4>Domaine analysé</h4>'
                    f'<div class="mg-mono" style="font-size:1.2rem;font-weight:700;">'
                    f'{domaine or d.get("domaine", "inconnu")}</div>'
                    f'<p style="margin-top:.75rem;">Marque la plus proche : '
                    f'<span class="mg-mono">{d.get("marque") or "—"}</span></p></div>',
                    unsafe_allow_html=True,
                )
            with droite:
                if "FRAUDULEUX" in d.get("verdict", ""):
                    st.error(d.get("verdict"))
                else:
                    st.success(d.get("verdict", "Aucune imitation"))
                st.metric("Score d'imitation (CANINE)", f"{d.get('score', 0):.3f}",
                          help=f"Probabilité que le domaine imite une marque protégée. "
                               f"Au-dessus de {d.get('seuil', 0.44):.2f} : imitation (règle sûre).")

    with o2:
        rf = details.get("domaine_randomforest", {})
        if scores.get("domaine_randomforest") is not None:
            c1, c2, c3 = st.columns(3)
            c1.metric("Score d'identité", f"{scores['domaine_randomforest']:.2f}")
            c2.metric("Âge du domaine", formater_age(rf.get("age_jours")))
            c3.metric("Alerte", "oui" if rf.get("alerte") else "non",
                      help=f"Alerte si score ≥ {rf.get('seuil', 0.74):.2f} ou domaine de moins de 30 jours.")
        else:
            st.info(rf.get("note", "Signal non calculé.") + " Un signal muet vaut 0 : il ne charge pas le message.")

    with o3:
        liens = details.get("liens", [])
        if not liens:
            st.info("Ce message ne contient aucun lien.")
        else:
            c1, c2 = st.columns(2)
            c1.metric("Liens analysés", len(liens))
            c2.metric("Liens suspects", sum(1 for lien in liens if lien.get("suspect")))
            st.write("")
            for numero, lien in enumerate(liens, 1):
                url = lien.get("url", "inconnue")
                classe = "mg-alert-danger" if lien.get("suspect") else "mg-alert-ok"
                st.markdown(
                    f'<div class="mg-alert {classe}">Lien {numero} : '
                    f'<span class="mg-mono">{url}</span><br>'
                    f'{" · ".join(lien.get("raisons", []))}</div>',
                    unsafe_allow_html=True)

    with o4:
        c = details.get("contenu", {})
        probabilite = c.get("probabilite")
        if probabilite is None:
            st.info(c.get("note") or "Contenu non analysé.")
        else:
            gauche, droite = st.columns([1, 1], gap="large")
            with gauche:
                st.metric("Probabilité de phishing (e5)", f"{probabilite * 100:.1f} %")
                st.metric("Langue détectée", c.get("langue_detectee", "indéterminée"))
            with droite:
                st.progress(min(probabilite, 1.0))
                if c.get("suspect"):
                    st.error(f"Le texte ressemble à du phishing (seuil {c.get('seuil', 0.391):.3f}).")
                else:
                    st.success("Le texte ne ressemble pas à du phishing.")

    with o5:
        a = details.get("authentification", {})
        for colonne, nom in zip(st.columns(3), ("spf", "dkim", "dmarc")):
            with colonne:
                st.markdown(f"**{nom.upper()}**")
                st.markdown(_etat_auth(a.get(nom, "absent")), unsafe_allow_html=True)
        st.write("")
        decision = a.get("decision")
        texte = " · ".join(a.get("raisons", []))
        if decision == "frauduleux":
            st.error(texte or "Usurpation d'un domaine Nouvelair.")
        elif decision == "suspect":
            st.warning(texte or "Authentification faible.")
        elif decision == "inconnu":
            st.info("Pas d'en-tête Authentication-Results : signal neutre.")
        else:
            st.success(texte or "L'expéditeur est bien celui qu'il prétend être.")

    # ── Tableau récapitulatif ──────────────────────────────────────────
    with st.expander("Voir le tableau des scores et la logique de décision"):
        if scores:
            tableau = pd.DataFrame([{"Signal": NOMS.get(k, k), "Score": v}
                                    for k, v in scores.items() if v is not None])
            st.dataframe(tableau.style.format({"Score": "{:.3f}"}), width="stretch", hide_index=True)
        contrib = details.get("fusion", {}).get("contributions", {})
        if contrib:
            st.caption("Contribution de chaque indice dans la fusion (poids appris × valeur) : "
                       + ", ".join(f"{k} {v:+.2f}" for k, v in sorted(contrib.items(), key=lambda kv: -kv[1])))
        st.caption(resultat.get("explication", ""))
        score_fusion = resultat.get("score_fusion", score_final)
        note = ("" if abs(score_fusion - score_final) < 1e-6 else
                f" Score affiché {score_final:.3f}, car la décision vient de l'étape « {resultat.get('etape_decision', '')} ».")
        st.caption(
            f"Score de la fusion {score_fusion:.3f}. Seuil suspect {seuil_suspect:.3f}, "
            f"seuil frauduleux {seuil_dangereux:.3f}. Décision retenue : {categorie.lower()}.{note}"
        )
