"""Qualitative Analyse ohne Zusatzkosten (Abschnitt 15) - reine Logik, ohne Netz und ohne Streamlit.

- Abschnitte aus dem 10-K (SEC EDGAR): Item 1 "Business" (inkl. "Competition"), Item 1A "Risk Factors",
  Angaben zu Grosskunden (> 10 % des Umsatzes).
- Regelbasierte Textanalyse: Haeufigkeit der Burggraben-Woerter je 10.000 Woerter, Vergleich mit dem Sektor.
- KI-Antwort (Gemini/Groq oder Claude per Copy-Paste): Prompt bauen, JSON robust herauslesen und pruefen.
- Moat-Score: Kennzahlen-Proxy + Textanalyse + KI, die eigene Einschaetzung ueberschreibt.
"""
import json
import re
import statistics

import investor_config as C

# ---------------------------------------------------------------------------
# 10-K-Text
# ---------------------------------------------------------------------------
def text_aus_html(html):
    """10-K-HTML -> Fliesstext (Tabellen und Inline-XBRL-Tags werden zu Text, Leerraum zusammengefasst)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html or "", "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    for t in soup.find_all(style=re.compile(r"display:\s*none", re.I)):    # versteckte XBRL-Kopfdaten
        t.decompose()
    text = soup.get_text(" ")
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


_ITEM = r"item\s*{nr}\s*[\.:\-–—]?\s*"


def _abschnitt(text, start_muster, ende_muster):
    """Laengster Treffer zwischen Start- und Endmarke - so faellt das Inhaltsverzeichnis (kurz) heraus."""
    beste = ""
    for m in re.finditer(start_muster, text, re.I):
        rest = text[m.end():]
        e = re.search(ende_muster, rest, re.I)
        stueck = rest[:e.start()] if e else rest[:200000]
        if len(stueck) > len(beste):
            beste = stueck
    return beste.strip()


def abschnitte(text):
    """-> {"business", "competition", "risiken"} aus dem 10-K-Text (leer, wenn nicht gefunden)."""
    business = _abschnitt(text, _ITEM.format(nr="1") + r"business", _ITEM.format(nr=r"1a") + r"risk\s*factors")
    risiken = _abschnitt(text, _ITEM.format(nr=r"1a") + r"risk\s*factors",
                         _ITEM.format(nr=r"(?:1b|1c|2)") + r"(?:unresolved|cybersecurity|properties)")
    comp = ""
    m = re.search(r"\bcompetition\b", business, re.I)
    if m:
        comp = business[m.start():m.start() + 6000]
    return {"business": business, "competition": comp, "risiken": risiken}


def wortzahl(text):
    return len(re.findall(r"[A-Za-z]{2,}", text or ""))


def zaehlen(text, woerter):
    t = (text or "").lower()
    return {w: t.count(w.lower()) for w in woerter}


def moat_dichte(text, woerterbuch=None, min_woerter=200):
    """Treffer je Burggraben-Typ je 10.000 Woerter (zu kurze Texte -> {}, kein belastbarer Wert)."""
    woerterbuch = woerterbuch or C.MOAT_WOERTER
    n = wortzahl(text)
    if n < min_woerter:
        return {}
    return {typ: round(sum(zaehlen(text, w).values()) * 10000 / n, 2) for typ, w in woerterbuch.items()}


def risiko_treffer(text):
    return {w: n for w, n in zaehlen(text, C.RISIKO_WOERTER).items() if n}


_SATZ = re.compile(r"[^.;]*\b(?:customer|client|distributor|purchaser)s?\b[^.;]*", re.I)
_PROZENT = re.compile(r"(\d{1,2}(?:\.\d)?)\s*(?:%|percent)", re.I)


def grosskunden(text, schwelle=None):
    """Saetze, in denen ein Kunde mit >= schwelle % des Umsatzes genannt wird. -> [(prozent, satz)]"""
    schwelle = C.GROSSKUNDE_SCHWELLE if schwelle is None else schwelle
    aus = []
    for m in _SATZ.finditer(text or ""):
        s = m.group(0).strip()
        if not re.search(r"revenue|net sales|sales|total", s, re.I):
            continue
        werte = [float(p) for p in _PROZENT.findall(s)]
        if werte and max(werte) >= schwelle and len(s) < 600:
            aus.append((max(werte), s))
    aus.sort(key=lambda x: -x[0])
    gesehen, eindeutig = set(), []
    for p, s in aus:
        if s not in gesehen:
            gesehen.add(s)
            eindeutig.append((p, s))
    return eindeutig[:5]


def peer_mediane(dichten):
    """dichten: [ {typ: wert} ] eines Sektors -> {typ: Median} (nur Typen mit mind. 3 Werten)."""
    je = {}
    for d in dichten:
        for typ, w in (d or {}).items():
            je.setdefault(typ, []).append(w)
    return {t: round(statistics.median(v), 2) for t, v in je.items() if len(v) >= 3}


def text_score(dichte, peers):
    """Textanalyse -> (Score 0-100, betonte Typen, Verhaeltnis je Typ). Verhaeltnis = Dichte / Sektor-Median.
    Score = Durchschnitt der drei staerksten Verhaeltnisse (je hoechstens 2) x 50: Sektor-Durchschnitt = 50."""
    if not dichte:
        return None, [], {}
    verh = {}
    for typ, w in dichte.items():
        m = (peers or {}).get(typ)
        if m and m > 0:
            verh[typ] = round(w / m, 2)
    if not verh:
        return None, [], {}
    top = sorted(verh.values(), reverse=True)[:3]
    score = round(min(100.0, sum(min(v, 2.0) for v in top) / len(top) * 50), 1)
    betont = [t for t, v in sorted(verh.items(), key=lambda kv: -kv[1]) if v >= C.MOAT_AUFFAELLIG]
    return score, betont, verh


# ---------------------------------------------------------------------------
# KI-Antwort (Option A und B): Schema, Prompt, robustes JSON
# ---------------------------------------------------------------------------
MOAT_TYPEN = ["Marke", "Netzwerkeffekt", "Wechselkosten", "Kostenvorteil", "Patente/Lizenzen", "Effiziente Skala",
              "keiner"]
KI_SCHEMA = {
    "marktposition": "string – z. B. Marktführer, Herausforderer, Nischenanbieter",
    "alleinstellungsmerkmal": "string",
    "moat_typen": "array of strings aus " + ", ".join(MOAT_TYPEN),
    "moat_trend": "string: wachsend | stabil | schrumpfend",
    "five_forces": {"rivalitaet": "niedrig|mittel|hoch", "neue_anbieter": "niedrig|mittel|hoch",
                    "ersatzprodukte": "niedrig|mittel|hoch", "lieferantenmacht": "niedrig|mittel|hoch",
                    "kundenmacht": "niedrig|mittel|hoch"},
    "abhaengigkeiten": "array of strings",
    "disruptionsrisiko": "string: niedrig | mittel | hoch",
    "begruendung": "string, max. 120 Wörter, auf Deutsch",
    "konfidenz": "number 0-1",
}
PFLICHT = ["marktposition", "alleinstellungsmerkmal", "moat_typen", "moat_trend", "five_forces", "abhaengigkeiten",
           "disruptionsrisiko", "begruendung", "konfidenz"]
STUFEN = {"niedrig", "mittel", "hoch"}


def json_aus_text(text):
    """Erstes vollstaendiges JSON-Objekt aus einer Antwort - robust gegen Markdown-Codebloecke und Text drumherum.
    -> dict oder None"""
    if not text:
        return None
    t = re.sub(r"```(?:json)?", "", str(text))
    start = t.find("{")
    while start != -1:
        tiefe, in_str, esc = 0, False, False
        for i in range(start, len(t)):
            c = t[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                tiefe += 1
            elif c == "}":
                tiefe -= 1
                if tiefe == 0:
                    try:
                        obj = json.loads(t[start:i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except ValueError:
                        pass
                    break
        start = t.find("{", start + 1)
    return None


def pruefen(obj):
    """KI-Antwort pruefen und vereinheitlichen. -> (dict oder None, [Fehler])"""
    if not isinstance(obj, dict):
        return None, ["Keine JSON-Antwort gefunden."]
    fehler = [f"Feld fehlt: {k}" for k in PFLICHT if k not in obj]
    if fehler:
        return None, fehler
    aus = dict(obj)
    typen = aus.get("moat_typen")
    if isinstance(typen, str):
        typen = [typen]
    if not isinstance(typen, list):
        return None, ["moat_typen ist keine Liste."]
    aus["moat_typen"] = [str(x).strip() for x in typen if str(x).strip()]
    if not isinstance(aus.get("five_forces"), dict):
        return None, ["five_forces ist kein Objekt."]
    aus["five_forces"] = {k: str(v).lower() for k, v in aus["five_forces"].items()}
    if not isinstance(aus.get("abhaengigkeiten"), list):
        aus["abhaengigkeiten"] = [str(aus["abhaengigkeiten"])] if aus.get("abhaengigkeiten") else []
    try:
        k = float(aus["konfidenz"])
        aus["konfidenz"] = max(0.0, min(1.0, k / 100 if k > 1 else k))
    except (TypeError, ValueError):
        return None, ["konfidenz ist keine Zahl."]
    for f in ("marktposition", "alleinstellungsmerkmal", "moat_trend", "disruptionsrisiko", "begruendung"):
        aus[f] = str(aus[f]).strip()
    return aus, []


def prompt(aktie, kennzahlen, texte, max_woerter=None):
    """Strukturierter Prompt (Option A und B): Unternehmensdaten + Auszuege + gewuenschtes JSON-Schema.
    aktie: {name, ticker, sektor, branche, land}; kennzahlen: {Bezeichnung: Text}; texte: {Titel: Text}."""
    max_woerter = max_woerter or C.PROMPT_MAX_WOERTER
    kopf = (
        "Du bist ein sorgfältiger Aktienanalyst. Bewerte die Wettbewerbsposition des folgenden Unternehmens "
        "ausschließlich anhand der mitgelieferten Daten. Wenn etwas nicht aus den Daten hervorgeht, sage das in "
        "der Begründung und senke die Konfidenz.\n\n"
        f"Unternehmen: {aktie.get('name')} ({aktie.get('ticker')})\n"
        f"Sektor/Branche: {aktie.get('sektor') or 'n/a'} / {aktie.get('branche') or 'n/a'} · Land: "
        f"{aktie.get('land') or 'n/a'}\n\nKennzahlen:\n"
        + "\n".join(f"- {k}: {v}" for k, v in (kennzahlen or {}).items()) + "\n")
    schluss = (
        "\n\nAntworte AUSSCHLIESSLICH mit einem JSON-Objekt (ohne Markdown, ohne Text davor oder danach) in genau "
        "diesem Schema:\n" + json.dumps(KI_SCHEMA, ensure_ascii=False, indent=1))
    rest = max_woerter - len((kopf + schluss).split())
    teile = []
    for titel, text in (texte or {}).items():
        if not text or rest <= 50:
            continue
        w = text.split()
        stueck = " ".join(w[:rest])
        rest -= min(len(w), rest)
        teile.append(f"\n### {titel}\n{stueck}")
    return kopf + "".join(teile) + schluss


# ---------------------------------------------------------------------------
# Moat-Score
# ---------------------------------------------------------------------------
def ki_moat_score(ki):
    """KI-Einschaetzung -> 0-100: Anzahl Burggraben-Typen (ohne "keiner"), Trend, mal Konfidenz."""
    if not ki:
        return None
    typen = [t for t in ki.get("moat_typen") or [] if t.lower() != "keiner"]
    basis = min(3, len(typen)) / 3 * 80
    trend = str(ki.get("moat_trend") or "").lower()
    basis += 20 if "wachs" in trend else 10 if "stabil" in trend else 0
    k = ki.get("konfidenz")
    k = 0.6 if k is None else k
    return round(basis * (0.5 + 0.5 * k), 1)       # unsichere Antworten zaehlen nur halb so stark


def moat_score(proxy_punkte, text, ki, manuell=None):
    """Kombinierter Burggraben-Score (0-100) nach MOAT_GEWICHTE; fehlende Teile werden hochgerechnet.
    manuell: True/False aus der eigenen Checkliste ("echter Burggraben?") ueberschreibt das Ergebnis.
    -> {score, teile: {kennzahlen, text, ki}, quelle, abweichung}"""
    teile = {"kennzahlen": None if proxy_punkte is None else round(proxy_punkte / 3 * 100, 1), "text": text,
             "ki": ki_moat_score(ki)}
    mit = {k: v for k, v in teile.items() if v is not None}
    summe = sum(C.MOAT_GEWICHTE[k] for k in mit)
    score = round(sum(C.MOAT_GEWICHTE[k] * v for k, v in mit.items()) / summe, 1) if summe else None
    abw = None
    if manuell is not None:
        berechnet_ja = score is not None and score >= 50
        if score is not None and berechnet_ja != manuell:
            abw = ("Deine Einschätzung (Burggraben: " + ("ja" if manuell else "nein") + ") weicht von der "
                   f"berechneten ab ({score:.0f}/100).")
        return {"score": 80.0 if manuell else 20.0, "teile": teile, "quelle": "eigene Einschätzung",
                "abweichung": abw, "berechnet": score}
    quellen = [{"kennzahlen": "berechnet", "text": "Textanalyse", "ki": "KI"}[k] for k in mit]
    return {"score": score, "teile": teile, "quelle": " + ".join(quellen) or "n/a", "abweichung": None,
            "berechnet": score}
