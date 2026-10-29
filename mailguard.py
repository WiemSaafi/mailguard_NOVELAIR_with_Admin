 # =====================================================================
# MailGuard — le module complet : UN mail (.eml) → légitime / suspect / frauduleux + les raisons
# =====================================================================
# Rien n'est réentraîné : ce module RASSEMBLE les modèles finaux des 5 signaux et de la fusion.
# La cascade de décision :
#   0. Listes de l'encadreur
#        - liste noire (adresse ou domaine)                              → FRAUDULEUX
#        - liste blanche / domaines officiels, SEULEMENT si le domaine est PROUVÉ (DKIM ou SPF aligné)
#                                                                         → LÉGITIME
#          (sans preuve, la liste blanche ne protège pas : un fraudeur pourrait usurper le domaine)
#   1. Règles sûres : usurpation d'un domaine Nouvelair (DMARC) · l'expéditeur imite une marque protégée → FRAUDULEUX
#   2. Score de la fusion (régression logistique, 9 indices, poids appris)
#        ≥ seuil frauduleux (≤ 0,5 % de vrais mails accusés) → FRAUDULEUX
#        ≥ seuil suspect    (≤ 2 %)                          → SUSPECT
#        sinon                                               → LÉGITIME
#   3. Les raisons, signal par signal
# Utilisation (Colab, compte qui voit les 5 signaux) :
#   from mailguard import MailGuard
#   mg = MailGuard()                       # charge tout une seule fois (≈ 1 min)
#   r = mg.analyser("mon_mail.eml")        # ou mg.analyser(octets_du_mail)
#   r = mg.analyser_parties("a@x.com", texte, liens, entetes)   # depuis l'application web
#   print(r["decision"], r["score"], r["raisons"])
# =====================================================================
import email, glob, html, json, math, os, re, sys, time
from collections import Counter
from email import policy
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, parse_qsl, unquote
import joblib, numpy as np, pandas as pd, requests, tldextract, torch

EXT = tldextract.TLDExtract(suffix_list_urls=())
UA = {"User-Agent": "MailGuard-projet-etudiant"}
MAX_LIENS = 15

def org(dom):
    r = EXT((dom or "").strip().strip(".>").lower())
    return f"{r.domain}.{r.suffix}" if r.domain and r.suffix else ""
def hote(url):
    h = (urlsplit(str(url)).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h

# ---------------------------------------------------------------------
# Lecture d'un mail (identique à l'étape 1 de la fusion)
# ---------------------------------------------------------------------
def _corps(m):
    texte, pages = [], []
    for p in m.walk():
        if p.get_content_maintype() == "multipart" or p.get_filename():
            continue
        try:
            c = p.get_content()
        except Exception:
            continue
        if isinstance(c, str):
            if p.get_content_type() == "text/plain": texte.append(c)
            elif p.get_content_type() == "text/html": pages.append(c)
    return "\n".join(texte), "\n".join(pages)

def _html_texte(h):
    h = re.sub(r"(?is)<(script|style).*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", h)
    return html.unescape(re.sub(r"<[^>]+>", " ", h))

def _liens(texte, page):
    l = re.findall(r"""(?i)href\s*=\s*["']?(https?://[^"'\s>]+)""", page)
    l += re.findall(r"(?i)https?://[^\s<>\"')\]]+", texte)
    l += re.findall(r"(?i)https?://[^\s<>\"')\]]+", re.sub(r"<[^>]+>", " ", page))
    vus, out = set(), []
    for u in l:
        u = html.unescape(u).rstrip(".,;:!?)»")
        if u not in vus:
            vus.add(u); out.append(u)
    return out[:MAX_LIENS]

def lire_mail(source):
    b = open(source, "rb").read() if isinstance(source, str) else source
    m = email.message_from_bytes(b, policy=policy.default)
    f = str(m.get("From", "") or "")
    adrs = re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", f)
    adresse = adrs[-1].lower() if adrs else ""
    h = adresse.split("@")[-1].strip(".>") if adresse else ""
    t, page = _corps(m)
    try:
        date = pd.Timestamp(parsedate_to_datetime(str(m.get("Date", ""))))
        date = date.tz_localize("UTC") if date.tzinfo is None else date.tz_convert("UTC")
    except Exception:
        date = pd.NaT
    entetes = "\n".join(f"{k}: {str(v)}" for k, v in m.items()
                        if k.lower() not in ("x-gmail-labels", "x-gm-thrid", "dkim-signature", "arc-seal", "arc-message-signature"))
    return {"adresse": adresse, "hote_expediteur": h[4:] if h.startswith("www.") else h, "expediteur": org(h), "date": date,
            "sujet": str(m.get("Subject", "") or "")[:200], "entetes": entetes[:20000],
            "texte": (str(m.get("Subject", "") or "") + "\n" + (t if t.strip() else _html_texte(page)))[:6000],
            "liens": _liens(t, page)}

def mail_depuis_parties(expediteur, texte="", liens=None, entetes="", sujet="", date=None):
    """Construit la même structure que lire_mail() à partir des champs déjà extraits
    par l'application web (test manuel, ou message dont on n'a pas les octets)."""
    adresse = (expediteur or "").strip().lower()
    if "@" not in adresse:
        adresse = f"contact@{adresse}" if adresse else ""
    h = adresse.split("@")[-1].strip(".>") if adresse else ""
    e = entetes or ""
    if e and not re.search(r"(?im)^authentication-results\s*:", e):
        e = "Authentication-Results: " + e          # on n'a reçu que la valeur de l'en-tête
    if adresse and not re.search(r"(?im)^from\s*:", e):
        e = f"From: <{adresse}>\n" + e
    try:
        d = pd.Timestamp(date) if date is not None else pd.Timestamp.now(tz="UTC")
        d = d.tz_localize("UTC") if d.tzinfo is None else d.tz_convert("UTC")
    except Exception:
        d = pd.Timestamp.now(tz="UTC")
    urls = []
    for l in liens or []:
        u = l.get("url_reelle") if isinstance(l, dict) else l
        if u and str(u).lower().startswith(("http://", "https://")) and u not in urls:
            urls.append(str(u))
    return {"adresse": adresse, "hote_expediteur": h[4:] if h.startswith("www.") else h, "expediteur": org(h), "date": d,
            "sujet": (sujet or "")[:200], "entetes": e[:20000],
            "texte": ((sujet or "") + "\n" + (texte or ""))[:6000], "liens": urls[:MAX_LIENS]}

# ---------------------------------------------------------------------
# Signal 3 : règles A v2 et indices du chemin (identiques au signal 3 final)
# ---------------------------------------------------------------------
RACC = {"bit.ly", "tinyurl.com", "is.gd", "cutt.ly", "rebrand.ly", "ow.ly", "shorturl.at", "rb.gy", "tiny.cc", "s.id", "t.ly",
        "shorturl.gg", "qrco.de", "bl.ink", "t.me", "1url.at", "shorten.tv", "urlz.fr", "lnkd.in", "cutt.us", "v.gd", "u.to",
        "tinu.be", "short.gy"}
MARQUES_CIBLES = ["paypal", "apple", "icloud", "microsoft", "office365", "outlook", "onedrive", "sharepoint", "netflix",
                  "amazon", "dhl", "fedex", "usps", "allegro", "facebook", "instagram", "whatsapp", "google", "chase",
                  "wellsfargo", "coinbase", "metamask", "binance", "adobe", "docusign", "linkedin", "dropbox",
                  "wetransfer", "roblox", "xfinity", "steam", "telegram", "yahoo", "nouvelair", "airbus"]
RE_MARQUE = re.compile(r"(?<![a-z])(" + "|".join(MARQUES_CIBLES) + ")")
MOTS = ["login", "signin", "logon", "verify", "account", "update", "secure", "confirm", "password",
        "wallet", "unlock", "suspend", "billing", "payment", "webscr", "authenticate", "recover", "invoice"]
EXT_RISQUEES = (".exe", ".zip", ".rar", ".scr", ".apk", ".js", ".vbs", ".iso", ".msi")
MOTS_SENSIBLES = ["login", "signin", "sign-in", "logon", "verify", "verif", "account", "update", "secure", "confirm", "password",
                  "passwd", "wallet", "unlock", "suspend", "billing", "payment", "webscr", "authenticate", "validation",
                  "recover", "reset", "invoice", "refund"]
MARQUES = ["paypal", "apple", "icloud", "microsoft", "office", "outlook", "onedrive", "sharepoint", "netflix", "amazon", "dhl",
           "fedex", "ups", "usps", "allegro", "facebook", "instagram", "whatsapp", "google", "chase", "wellsfargo", "bank",
           "coinbase", "metamask", "binance", "adobe", "docusign", "nouvelair"]
GRATUITS = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "yahoo.com", "yahoo.fr", "aol.com", "icloud.com",
            "gmx.com", "gmx.de", "mail.ru", "yandex.ru", "protonmail.com", "proton.me", "hotmail.fr", "laposte.net", "msn.com"}

def _entropie(t):
    if not t: return 0.0
    c = Counter(t); n = len(t)
    return -sum(v / n * math.log2(v / n) for v in c.values())

def _indices_chemin(chemin, requete):
    ch, rq = unquote(chemin).lower(), unquote(requete).lower()
    tout = ch + "?" + rq if rq else ch
    seg = [s for s in ch.split("/") if s]
    return {"longueur_chemin": len(ch), "profondeur": len(seg), "longueur_requete": len(rq),
            "nb_parametres": len(parse_qsl(requete, keep_blank_values=True)),
            "part_chiffres": sum(c.isdigit() for c in tout) / max(len(tout), 1),
            "nb_caracteres_speciaux": sum(tout.count(c) for c in "-_=%~&.@!"), "entropie_chemin": round(_entropie(tout), 3),
            "plus_long_segment": max((len(s) for s in seg), default=0), "nb_mots_sensibles": sum(m in tout for m in MOTS_SENSIBLES),
            "marque_dans_chemin": int(any(m in tout for m in MARQUES)),
            "redirection_cachee": int(bool(re.search(r"(https?:|www\.|=http|url=|redirect|goto=|next=)", tout))),
            "arobase_dans_chemin": int("@" in tout), "double_slash": int("//" in ch), "fichier_php": int(".php" in ch),
            "fichier_html": int(".htm" in ch), "fichier_dangereux": int(ch.endswith(EXT_RISQUEES)),
            "dossier_wordpress": int(bool(re.search(r"wp-(content|admin|includes)", ch))),
            "suivi_marketing": int(bool(re.search(r"(utm_|fbclid|gclid|mc_eid)", rq))),
            "encodage_pourcent": tout.count("%") + chemin.count("%")}


class MailGuard:
    def __init__(self, racine="/content/drive/MyDrive", internet=True, e5="intfloat/multilingual-e5-base"):
        t0 = time.time()
        self.R, self.internet = racine, internet
        self.app = "cuda" if torch.cuda.is_available() else "cpu"
        d1 = os.path.dirname(self._trouver("marques_protegees.csv"))
        dc = os.path.dirname(self._trouver("modeles/CANINE/config.json"))
        d3 = os.path.dirname(self._trouver("modeles_signal3_final.joblib"))
        d4 = os.path.dirname(self._trouver("s4_modele_final/logistique_e5.joblib"))
        d5 = os.path.dirname(self._trouver("s5_modele_final/modele_auth.joblib"))
        df = os.path.dirname(self._trouver("fusion_modele/fusion.joblib"))
        # --- listes de l'encadreur ---
        mq = pd.read_csv(f"{d1}/marques_protegees.csv")
        self.texte_marque = {l.marque: " ".join(sorted(l.domaines_officiels.split(" ; "))) for l in mq.itertuples()}
        self.officiels = {x.strip().lower() for l in mq.itertuples() for x in l.domaines_officiels.split(" ; ")}
        self.blanche_adr, self.blanche_dom = set(), set(self.officiels)
        self.noire_adr, self.noire_dom = set(), set()
        for fichier, adr, dom in [("whitelist_propre.csv", self.blanche_adr, self.blanche_dom),
                                  ("blacklist_propre.csv", self.noire_adr, self.noire_dom)]:
            f = self._trouver(fichier, obligatoire=False)
            if f:
                for l in pd.read_csv(f).itertuples():
                    if l.niveau == "adresse":
                        adr.add(str(l.entree).lower())
                    else:
                        dom.add(str(l.domaine).lower())
        # --- signal 1 : CANINE ---
        from transformers import AutoTokenizer, AutoModelForSequenceClassification, AutoModel
        self.seuil_s1 = float(pd.read_csv(f"{dc}/seuil.csv")["seuil"][0])
        self.tok1 = AutoTokenizer.from_pretrained(dc)
        self.canine = AutoModelForSequenceClassification.from_pretrained(dc).to(self.app).eval()
        # --- signaux 2 et 3 ---
        self.s3 = joblib.load(f"{d3}/modeles_signal3_final.joblib")
        self.m2 = joblib.load(f"{d3}/modeles_signal2_v2.joblib")
        self.seuil_s2 = self.m2["seuils"]["Gradient Boosting v2"]
        self.connus = set(pd.read_csv(f"{d3}/tranco_top1m.csv")["domaine"].str.lower())
        self.hebergeurs = tuple(self.s3["hebergeurs_gratuits"]) + ("wasmer.app", "hackmd.io", "sharemyhtml.com", "cprapid.com",
            "usercontent.com", "demoitusercontent.com", "googleusercontent.com", "ipfs.w3s.link", "pinata.cloud", "canva.site",
            "yolasite.com", "webwave.dev", "wixstudio.com", "tilda.ws", "site123.me", "odoo.com")
        self._rdap, self._cache2 = None, {}
        # --- signal 4 : e5 + logistique ---
        sys.path.insert(0, d4)
        from s4_outils import preparer
        self.preparer = preparer
        self.lr4 = joblib.load(f"{d4}/logistique_e5.joblib")
        self.seuil_s4 = json.load(open(f"{d4}/parametres.json"))["seuil"]
        self.tok4 = AutoTokenizer.from_pretrained(e5)
        self.e5 = AutoModel.from_pretrained(e5).to(self.app).eval()
        # --- signal 5 ---
        sys.path.insert(0, d5)
        import detecteur_auth
        self.det5 = detecteur_auth.DetecteurAuth(d5)
        # --- fusion ---
        f = joblib.load(f"{df}/fusion.joblib")
        self.lr, self.ind = f["logistique"], f["indices"]
        p = json.load(open(f"{df}/parametres.json"))
        self.seuil_suspect, self.seuil_fraude = p["seuil_suspect"], p["seuil_frauduleux"]
        print(f"MailGuard prêt en {time.time() - t0:.0f} s ({self.app}) · liste blanche {len(self.blanche_adr)} adresses + "
              f"{len(self.blanche_dom)} domaines · liste noire {len(self.noire_adr)} adresses + {len(self.noire_dom)} domaines")

    def _trouver(self, motif, obligatoire=True):
        for prof in ["", "*/", "*/*/", "*/*/*/"]:
            r = glob.glob(f"{self.R}/{prof}{motif}")
            if r:
                return r[0]
        if obligatoire:
            raise FileNotFoundError(motif)
        return None

    @staticmethod
    def _dans(dom, ensemble):
        return any(dom == d or dom.endswith("." + d) for d in ensemble)

    def _gratuit(self, url):
        h = hote(url)
        return any(h == x or h.endswith("." + x) for x in self.hebergeurs)

    # ----------------------------- signal 1 -----------------------------
    @torch.no_grad()
    def _canine(self, hotes):
        hotes = [h for h in dict.fromkeys(hotes) if h and org(h) not in self.officiels]
        paires = [(m, h) for h in hotes for m in self.texte_marque]
        sc = []
        for i in range(0, len(paires), 128):
            lot = paires[i:i + 128]
            enc = self.tok1([self.texte_marque[m] for m, _ in lot], [h for _, h in lot], padding="max_length", truncation=True,
                            max_length=128, return_tensors="pt").to(self.app)
            sc += torch.softmax(self.canine(**enc).logits.float(), -1)[:, 1].cpu().tolist()
        res = {}
        for (m, h), s in zip(paires, sc):
            if s > res.get(h, (0, ""))[0]:
                res[h] = (s, m)
        return res

    # ----------------------------- signal 2 -----------------------------
    def _signal2(self, domaine, jour):
        if not self.internet or not domaine or domaine in self.connus or domaine in GRATUITS:
            return None
        if domaine not in self._cache2:
            x = {}
            try:
                if self._rdap is None:
                    boot = requests.get("https://data.iana.org/rdap/dns.json", headers=UA, timeout=20).json()
                    self._rdap = {t: next((u for u in us if u.startswith("https")), us[0]).rstrip("/") for tlds, us in boot["services"] for t in tlds}
                base = self._rdap.get(domaine.rsplit(".", 1)[-1])
                if base:
                    r = requests.get(f"{base}/domain/{domaine}", headers=UA, timeout=10)
                    if r.ok:
                        ev = {e.get("eventAction"): e.get("eventDate") for e in r.json().get("events", [])}
                        x["creation"] = ev.get("registration")
            except Exception:
                pass
            try:
                r = requests.get("https://crt.sh/", params={"q": domaine, "output": "json"}, headers=UA, timeout=20)
                if r.ok:
                    x["certs"] = sorted({c["not_before"][:10] for c in r.json()})
            except Exception:
                pass
            self._cache2[domaine] = x
        x = self._cache2[domaine]
        jour = jour if pd.notna(jour) else pd.Timestamp.now(tz="UTC")
        creation = pd.to_datetime(x.get("creation"), utc=True, errors="coerce")
        if pd.isna(creation) or creation > jour:
            return None
        age = (jour - creation).total_seconds() / 86400
        if "certs" not in x:
            return {"score": 1.0 if age < 30 else 0.0, "age": age, "alerte": age < 30}
        avant = [c for c in x["certs"] if pd.Timestamp(c, tz="UTC") <= jour]
        premier = pd.Timestamp(avant[0], tz="UTC") if avant else pd.NaT
        f = {"age_domaine_jours": age, "age_premier_certificat_jours": (jour - premier).total_seconds() / 86400 if avant else np.nan,
             "nb_certificats": len(avant), "jours_creation_a_certificat": (premier - creation).total_seconds() / 86400 if avant else np.nan}
        s = float(self.m2["boosting"].predict_proba(pd.DataFrame([f])[self.m2["indices"]])[0, 1])
        return {"score": s, "age": age, "alerte": s >= self.seuil_s2 or age < 30}

    # ----------------------------- signal 3 -----------------------------
    def _regles(self, url):
        s = urlsplit(str(url)); h = (s.hostname or "").lower(); bas = unquote(str(url)).lower()
        fortes, moyennes = [], []
        if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", h): fortes.append("adresse IP")
        if "@" in s.netloc: fortes.append("@ avant le domaine")
        if "xn--" in h: fortes.append("punycode")
        if s.path.lower().endswith(EXT_RISQUEES): fortes.append("fichier dangereux")
        gr = self._gratuit(url)
        if org(h) in RACC: moyennes.append("raccourcisseur")
        if gr and any(m in bas for m in MOTS): moyennes.append("hébergeur gratuit + mot sensible")
        if s.scheme == "http" and any(m in bas for m in MOTS): moyennes.append("http + mot sensible")
        inconnu = gr or org(h) not in self.connus
        texte = bas.replace(org(h), " ") if gr else bas
        m = RE_MARQUE.search(texte)
        if inconnu and m: fortes.append(f"marque {m.group(1)} sur un domaine qui n'est pas le sien")
        if "_" in h: fortes.append("_ dans le nom d'hôte")
        if re.search(r"(?<!\d)\d{1,3}-\d{1,3}-\d{1,3}-\d{1,3}(?!\d)", h): fortes.append("IP cachée dans le nom")
        if gr and not moyennes: moyennes.append("hébergeur gratuit")
        return fortes, moyennes

    # ----------------------------- garde-fou liste blanche -------------
    def _lien_dangereux(self, urls):
        """Renvoie la première URL dangereuse, ou None.

        Un lien est « dangereux » si son domaine n'est pas officiel ET :
        - il est dans la liste noire, OU
        - il déclenche une règle forte (_regles), OU
        - son hôte imite une marque protégée (CANINE ≥ seuil_s1).
        """
        bruts = [u for u in urls if hote(u)]
        a_tester = []
        for u in bruts:
            h_l = hote(u)
            if org(h_l) in self.officiels:
                continue
            if self._dans(h_l, self.noire_dom):
                return u
            fortes, _ = self._regles(u)
            if fortes:
                return u
            a_tester.append((u, h_l))
        if a_tester:
            c1 = self._canine([h for _, h in a_tester])
            for u, h_l in a_tester:
                s, _ = c1.get(h_l, (0.0, ""))
                if s >= self.seuil_s1:
                    return u
        return None

    # ----------------------------- analyse -----------------------------
    def analyser(self, source):
        """source = chemin d'un .eml ou octets d'un mail."""
        return self.analyser_mail(lire_mail(source))

    def analyser_parties(self, expediteur, texte="", liens=None, entetes="", sujet="", date=None):
        """Même analyse à partir des champs déjà extraits (application web)."""
        return self.analyser_mail(mail_depuis_parties(expediteur, texte, liens, entetes, sujet, date))

    def officiel_de(self, marque):
        """Premier domaine officiel d'une marque protégée (pour l'affichage)."""
        t = self.texte_marque.get(marque, "")
        return t.split()[0] if t else ""

    def analyser_mail(self, M):
        t0 = time.time()
        exp, adr, h_exp = M["expediteur"], M["adresse"], M["hote_expediteur"]
        r5 = self.det5.analyser(M["entetes"])
        d5 = r5.get("details", {})
        prouve = bool(d5.get("dkim_aligne")) or (d5.get("spf") == "pass" and bool(d5.get("spf_aligne")))
        sortie = {"expediteur": adr, "sujet": M["sujet"], "date": str(M["date"])[:19], "nb_liens": len(M["liens"]),
                  "details": {"auth": d5, "auth_decision": r5.get("decision"), "auth_raisons": r5.get("raisons", []),
                              "auth_score": r5.get("score")}}

        # ---- étape 0 : listes de l'encadreur ----
        if adr in self.noire_adr or self._dans(h_exp, self.noire_dom):
            return {**sortie, "decision": "frauduleux", "score": 1.0, "etape": "0. liste noire",
                    "raisons": ["expéditeur dans la liste noire de Nouvelair"], "duree_s": round(time.time() - t0, 2)}
        en_blanche = adr in self.blanche_adr or self._dans(h_exp, self.blanche_dom)
        lien_piege = None
        if en_blanche and prouve and r5.get("decision") != "frauduleux":
            lien_piege = self._lien_dangereux(M["liens"])
            if not lien_piege:
                return {**sortie, "decision": "légitime", "score": 0.0, "etape": "0. liste blanche (domaine prouvé)",
                        "raisons": ["partenaire de la liste blanche, authentifié (DKIM ou SPF aligné)"], "duree_s": round(time.time() - t0, 2)}

        # ---- les 5 signaux ----
        liens = [u for u in M["liens"] if hote(u)]
        c1 = self._canine([h_exp] + [hote(u) for u in liens])
        s1, marque = c1.get(h_exp, (0.0, ""))
        s1_alerte = s1 >= self.seuil_s1 and exp not in self.officiels
        r2 = self._signal2(exp, M["date"])
        A, B1, B2, Cmax, susp, rais3, nb_chemins = False, False, False, 0.0, False, [], 0
        detail_liens = []
        for u in liens:
            dom, h = org(hote(u)), hote(u)
            dl = {"url": u, "suspect": False, "douteux": False, "raisons": [], "chemin": None}
            detail_liens.append(dl)
            if dom in self.officiels:
                dl["raisons"].append("domaine officiel d'une marque protégée")
                continue
            fortes, moyennes = self._regles(u)
            if fortes: A = True; rais3.append("lien : " + fortes[0]); dl["suspect"] = True; dl["raisons"] += fortes
            if moyennes: susp = True; dl["douteux"] = True; dl["raisons"] += moyennes
            b1, mb = c1.get(h, (0.0, ""))
            if b1 >= self.seuil_s1:
                B1 = True; rais3.append(f"lien imite {mb}"); dl["suspect"] = True; dl["raisons"].append(f"imite la marque {mb} ({b1:.2f})")
            if dom not in self.connus and not self._gratuit(u):
                rb = self._signal2(dom, M["date"])
                if rb and rb["alerte"]:
                    B2 = True; rais3.append(f"lien vers un domaine de {rb['age']:.0f} jours")
                    dl["suspect"] = True; dl["raisons"].append(f"domaine créé il y a {rb['age']:.0f} jours")
            p = urlsplit(u)
            if not (p.path in ("", "/") and p.query == "") and (self._gratuit(u) or dom not in self.connus):
                c = float(self.s3["boosting"].predict_proba(pd.DataFrame([_indices_chemin(p.path, p.query)])[self.s3["indices"]])[0, 1])
                Cmax = max(Cmax, c); dl["chemin"] = round(c, 3)
                if c >= self.s3["seuil"]:
                    nb_chemins += 1; dl["suspect"] = True; dl["raisons"].append(f"chemin suspect ({c:.2f})")
        texte = self.preparer(M["texte"])
        if len(texte) < 30:
            s4 = 0.0
        else:
            with torch.no_grad():
                b = self.tok4(["query: " + texte], truncation=True, max_length=256, padding=True, return_tensors="pt").to(self.app)
                hd = self.e5(**b).last_hidden_state.float()
                mk = b["attention_mask"].unsqueeze(-1).float()
                v = torch.nn.functional.normalize((hd * mk).sum(1) / mk.sum(1), dim=-1).cpu().numpy()
            s4 = float(self.lr4.predict_proba(v)[0, 1])
        s5 = r5["score"] if r5["score"] is not None else 0.0

        # ---- étape 1 : règles sûres ----
        veto5 = r5.get("decision") == "frauduleux"
        raisons = []
        if veto5: raisons.append("usurpation d'un domaine Nouvelair (DMARC échoue)")
        if s1_alerte: raisons.append(f"l'expéditeur imite la marque {marque} ({s1:.2f})")
        # ── R1 : lien vers la liste noire (tout expéditeur) ──
        lien_noire = None
        for u in liens:
            h_l = hote(u)
            if self._dans(h_l, self.noire_dom):
                lien_noire = u; break
        if lien_noire:
            raisons.append(f"lien vers un domaine de la liste noire : {lien_noire}")
        # ---- étape 2 : score de la fusion ----
        x = pd.DataFrame([{"S1 imitation (CANINE)": s1, "S2 domaine jeune": r2["score"] if r2 else 0.0,
                           "S3 règle forte (lien)": float(A), "S3 lien imite une marque": float(B1),
                           "S3 domaine du lien jeune": float(B2), "S3 chemin (score max)": Cmax,
                           "S3 lien douteux (raccourcisseur…)": float(susp), "S4 texte (e5)": s4, "S5 authentification": s5}])[self.ind]
        score = float(self.lr.predict_proba(x)[0, 1])
        if veto5 or s1_alerte:
            decision, etape = "frauduleux", "1. règle sûre"
        elif lien_noire:
            decision, etape = "frauduleux", "1. règle sûre"
        elif score >= self.seuil_fraude:
            decision, etape = "frauduleux", "2. score ≥ seuil frauduleux"
        elif score >= self.seuil_suspect:
            decision, etape = "suspect", "2. score ≥ seuil suspect"
        else:
            decision, etape = "légitime", "2. score sous les seuils"
        # ── R2 : expéditeur de confiance + lien dangereux → au minimum suspect ──
        if decision == "légitime" and lien_piege and en_blanche and prouve:
            decision, etape = "suspect", "1. règle sûre (expéditeur de confiance, lien dangereux)"
            raisons.append(f"expéditeur authentifié mais lien dangereux : {lien_piege} (compte peut-être piraté)")
        # ── R3 : lien imite une marque protégée → au minimum suspect (tout expéditeur) ──
        if decision == "légitime" and B1:
            decision, etape = "suspect", "1. règle sûre (lien imite une marque protégée)"
        # ---- étape 3 : raisons ----
        if r2 and r2["alerte"]: raisons.append(f"domaine de l'expéditeur créé il y a {r2['age']:.0f} jours")
        raisons += list(dict.fromkeys(rais3))[:3]
        if nb_chemins:
            raisons.append(f"{nb_chemins} lien(s) au chemin suspect (max {Cmax:.2f})")
        if s4 >= self.seuil_s4: raisons.append(f"texte de phishing ({s4:.2f})")
        rs5 = [x_ for x_ in r5.get("raisons", []) if "authentifié (domaine prouvé)" not in x_]   # on ne garde que ce qui est suspect
        if r5.get("decision") == "suspect" or s5 >= 0.5:
            raisons += [f"authentification : {x_}" for x_ in rs5[:2]] or [f"authentification faible (score {s5:.2f})"]
        if en_blanche and not prouve: raisons.append("domaine de la liste blanche, mais NON authentifié")
        if decision != "légitime" and not raisons:
            contrib = (x.iloc[0] * self.lr.coef_[0]).sort_values(ascending=False)
            raisons.append("plusieurs indices faibles ensemble : " + ", ".join(contrib.index[:2]))
        sortie["details"].update({
            "s1": {"score": round(s1, 3), "marque": marque, "domaine_officiel": self.officiel_de(marque) if marque else "",
                   "seuil": self.seuil_s1, "alerte": s1_alerte, "domaine": h_exp},
            "s2": ({**r2, "seuil": self.seuil_s2} if r2 else None),
            "liens": detail_liens,
            "s4": {"score": round(s4, 3), "seuil": self.seuil_s4, "alerte": s4 >= self.seuil_s4, "longueur": len(texte)},
            "fusion": {"score": round(score, 3), "seuil_suspect": self.seuil_suspect, "seuil_frauduleux": self.seuil_fraude,
                       "contributions": {k: round(float(v), 3) for k, v in (x.iloc[0] * self.lr.coef_[0]).items()},
                       "constante": round(float(self.lr.intercept_[0]), 3)}})
        return {**sortie, "decision": decision, "score": round(score, 3), "etape": etape, "raisons": raisons,
                "signaux": {"S1": round(s1, 3), "S2": (round(r2["score"], 3) if r2 else "muet"), "S3_chemin": round(Cmax, 3),
                            "S3_regle": A, "S4": round(s4, 3), "S5": round(s5, 3)},
                "duree_s": round(time.time() - t0, 2)}
