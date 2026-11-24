"""Skript-Agent: Auftrag -> eigenstaendiges Skript (Titel, Hook, Kapitel mit Szenentexten, Bildsuchbegriffen,
Beschreibung, Tags, zu pruefende Aussagen). Ueber eine KI (ki_anbieter: Gemini/Groq) oder aus einem von Hand
eingefuegten Text. Das Skript ist immer bearbeitbar; die KI-Fakten gelten bis zur Pruefung als ungeprueft."""
import json
import re

WOERTER_PRO_MINUTE = 140            # ruhiges deutsches Erklaer-Tempo (Piper thorsten-medium ~ 140-150)
MAX_SZENE_WOERTER = 40              # laengere Szenen werden geteilt (ca. 15-17 Sekunden)


class SkriptFehler(Exception):
    pass


def wortbudget(dauer_min):
    return int(round(float(dauer_min) * WOERTER_PRO_MINUTE))


def prompt(auftrag, dauer_min, sprache="de", zielgruppe=""):
    """Anweisung an die KI. Verlangt ein eigenstaendiges Skript (keine Kopie fremder Videos) als JSON."""
    budget = wortbudget(dauer_min)
    return f"""Du bist ein erfahrener Autor für sachliche, faceless YouTube-Erklärvideos.
Auftrag: {auftrag}
Sprache des Sprechertexts: {"Deutsch" if sprache == "de" else "Englisch"}. Zielgruppe: {zielgruppe or "aus dem Auftrag ableiten"}.
Länge: ca. {dauer_min} Minuten = ca. {budget} Wörter Sprechertext insgesamt (Toleranz ±10 %).

Regeln:
- Eigenständiger Inhalt mit echtem Mehrwert. Keine Kopie, Übersetzung oder Paraphrase fremder Videos oder Texte.
- Starker Einstieg (Hook) in 1-2 Sätzen, klare Kapitel, konkrete Beispiele, kurzer Abschluss mit Fazit.
- Keine erfundenen Zahlen, Preise oder Zitate. Wo eine Aussage geprüft werden muss, nimm sie in "zu_pruefen" auf.
- Keine Werbeversprechen, keine Garantien, keine Anlage-, Rechts- oder Gesundheitsberatung.
- Jede Szene: 1-3 Sätze Sprechertext (höchstens {MAX_SZENE_WOERTER} Wörter) und ein kurzer ENGLISCHER Bildsuchbegriff
  (2-4 Wörter, allgemein und bildlich, z. B. "small business laptop", keine Markennamen, keine Personen).

Antworte NUR mit einem JSON-Objekt in genau diesem Schema:
{{"titel": "...(max. 70 Zeichen)", "hook": "...", "kapitel": [{{"titel": "...", "szenen": [{{"text": "...", "bild": "..."}}]}}],
 "beschreibung": "...(2-4 Sätze für YouTube)", "tags": ["..."], "zu_pruefen": ["Aussage, die vor Veröffentlichung geprüft werden muss"]}}"""


def json_aus_text(text):
    if not text:
        return None
    m = re.search(r"\{.*\}", str(text), re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


def _woerter(t):
    return len(re.findall(r"\w+", t or ""))


def pruefen(obj):
    """KI-Antwort pruefen und vereinheitlichen -> Skript-dict. Wirft SkriptFehler mit verstaendlichem Text."""
    if not isinstance(obj, dict):
        raise SkriptFehler("Die KI hat kein gültiges Skript geliefert.")
    titel = str(obj.get("titel") or "").strip()
    kapitel = []
    for k in obj.get("kapitel") or []:
        if not isinstance(k, dict):
            continue
        szenen = [{"text": str(s.get("text") or "").strip(), "bild": str(s.get("bild") or "").strip()}
                  for s in k.get("szenen") or [] if isinstance(s, dict) and str(s.get("text") or "").strip()]
        if szenen:
            kapitel.append({"titel": str(k.get("titel") or "").strip() or "Kapitel", "szenen": szenen})
    if not titel or not kapitel:
        raise SkriptFehler("Im Skript fehlen Titel oder Kapitel.")
    hook = str(obj.get("hook") or "").strip()
    if hook:
        kapitel[0]["szenen"].insert(0, {"text": hook, "bild": kapitel[0]["szenen"][0]["bild"]})
    return {"titel": titel[:100], "kapitel": kapitel, "beschreibung": str(obj.get("beschreibung") or "").strip(),
            "tags": [str(t).strip() for t in obj.get("tags") or [] if str(t).strip()][:15],
            "zu_pruefen": [str(t).strip() for t in obj.get("zu_pruefen") or [] if str(t).strip()],
            "quelle": "KI", "geprueft": False}


def aus_text(titel, text, bild_standard=""):
    """Von Hand eingefuegtes Skript -> Skript-dict. Kapitel beginnen mit '## Titel'; Absaetze werden Szenen.
    Optional je Absatz am Ende '[bild: english search words]'."""
    titel = (titel or "").strip()
    if not titel or not (text or "").strip():
        raise SkriptFehler("Bitte Titel und Skripttext angeben.")
    kapitel, akt = [], {"titel": "Einleitung", "szenen": []}
    for block in re.split(r"\n\s*\n", text.strip()):
        block = block.strip()
        if block.startswith("## "):
            zeilen = block.split("\n", 1)
            if akt["szenen"]:
                kapitel.append(akt)
            akt = {"titel": zeilen[0][3:].strip() or "Kapitel", "szenen": []}
            block = zeilen[1].strip() if len(zeilen) > 1 else ""
            if not block:
                continue
        m = re.search(r"\[bild:\s*([^\]]+)\]\s*$", block, re.I)
        bild = m.group(1).strip() if m else bild_standard
        satz = re.sub(r"\[bild:[^\]]*\]\s*$", "", block, flags=re.I).strip()
        if satz:
            akt["szenen"].append({"text": " ".join(satz.split()), "bild": bild})
    if akt["szenen"]:
        kapitel.append(akt)
    if not kapitel:
        raise SkriptFehler("Der Text enthält keine Absätze.")
    return {"titel": titel[:100], "kapitel": kapitel, "beschreibung": "", "tags": [], "zu_pruefen": [],
            "quelle": "manuell", "geprueft": True}


def mit_ki(anbieter, auftrag, dauer_min, sprache="de", zielgruppe=""):
    """Skript ueber ki_anbieter (Gemini/Groq). Bei ungueltigem JSON genau ein zweiter Versuch."""
    if anbieter is None:
        raise SkriptFehler("Kein KI-Zugang (GEMINI_API_KEY) eingerichtet – Skript bitte von Hand einfügen.")
    p = prompt(auftrag, dauer_min, sprache, zielgruppe)
    fehler = None
    for _ in range(2):
        try:
            return pruefen(json_aus_text(anbieter.antwort(p)))
        except SkriptFehler as ex:
            fehler = ex
            p += "\n\nDeine letzte Antwort war kein gültiges JSON im verlangten Schema. Nur das JSON-Objekt!"
    raise SkriptFehler(f"{fehler} (nach zwei Versuchen)")


def woerter(skript):
    return sum(_woerter(s["text"]) for k in skript["kapitel"] for s in k["szenen"])


def geschaetzte_dauer_s(skript):
    return woerter(skript) / WOERTER_PRO_MINUTE * 60
