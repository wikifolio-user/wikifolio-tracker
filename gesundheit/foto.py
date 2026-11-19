"""Foto-Erkennung (KI): Mahlzeit fotografieren -> Lebensmittel mit geschaetzter Menge; Supplement-Etikett
fotografieren -> Produkt und Inhaltsstoffe. Ohne Streamlit; getestet in test_gesundheit.py (ohne Netz).

Ablauf: Bild verkleinern -> an Google Gemini senden (Key GEMINI_API_KEY aus den Secrets, wie ki_anbieter.py) ->
JSON pruefen und auf die eigene Datenbank abbilden. Es wird NICHTS gespeichert: Die Oberflaeche zeigt eine
Vorschau, der Benutzer korrigiert und bestaetigt. Das Foto selbst wird nirgends abgelegt.
Alle Ergebnisse sind Schaetzungen.
"""
import base64
import io
import json
import logging
import re

from . import lebensmittel as L
from . import naehrstoffe as N

MAX_KANTE = 1024           # Pixel - reicht fuer die Erkennung, spart Datenvolumen und Wartezeit
MAX_POSTEN = 12

PROMPT_MAHLZEIT = """Du bist ein Ernährungsassistent. Erkenne auf dem Foto alle Lebensmittel und Getränke und schätze
die Menge in Gramm (bei Getränken in Milliliter, Feld "menge_g" trotzdem verwenden). Nutze einfache deutsche
Bezeichnungen wie in einer Nährwerttabelle (z. B. "Hähnchenbrust, gebraten", "Reis, gekocht", "Brokkoli").
Antworte NUR mit JSON in diesem Schema:
{"lebensmittel": [{"name": "…", "menge_g": 150, "sicherheit": "hoch|mittel|niedrig"}], "hinweis": "kurzer Satz"}
Wenn kein Essen zu sehen ist: {"lebensmittel": [], "hinweis": "Kein Essen erkannt"}"""

PROMPT_ETIKETT = """Lies das Etikett dieses Nahrungsergänzungsmittels. Gib Produktname, Hersteller, Darreichungsform
(Tablette, Kapsel, Softgel, Pulver, Flüssigkeit, Tropfen, Sachet oder Portion), die Portionsangabe
(z. B. "1 Kapsel") und alle Inhaltsstoffe JE PORTION mit Menge und Einheit (mg, µg, g oder IE) an.
Antworte NUR mit JSON in diesem Schema:
{"produkt": "…", "hersteller": "…", "form": "Kapsel", "portion": "1 Kapsel",
 "inhalt": [{"naehrstoff": "Vitamin D3", "menge": 25, "einheit": "µg"}]}
Unleserliche Angaben weglassen statt raten."""

# Namen auf den Etiketten -> Naehrstoff-ID (zusaetzlich zu den Anzeigenamen in naehrstoffe.py)
SYNONYME = {
    "vitamin a": "vit_a", "retinol": "vit_a", "vitamin b1": "vit_b1", "thiamin": "vit_b1", "vitamin b2": "vit_b2",
    "riboflavin": "vit_b2", "vitamin b3": "vit_b3", "niacin": "vit_b3", "nicotinamid": "vit_b3",
    "vitamin b5": "vit_b5", "pantothensaure": "vit_b5", "vitamin b6": "vit_b6", "pyridoxin": "vit_b6",
    "vitamin b7": "vit_b7", "biotin": "vit_b7", "vitamin b9": "vit_b9", "folsaure": "vit_b9", "folat": "vit_b9",
    "vitamin b12": "vit_b12", "cobalamin": "vit_b12", "methylcobalamin": "vit_b12", "cyanocobalamin": "vit_b12",
    "vitamin c": "vit_c", "ascorbinsaure": "vit_c", "vitamin d": "vit_d", "vitamin d3": "vit_d",
    "cholecalciferol": "vit_d", "vitamin e": "vit_e", "tocopherol": "vit_e", "vitamin k": "vit_k",
    "vitamin k2": "vit_k", "vitamin k1": "vit_k", "menachinon": "vit_k", "calcium": "calcium", "kalzium": "calcium",
    "magnesium": "magnesium", "kalium": "kalium", "natrium": "natrium", "phosphor": "phosphor", "chlorid": "chlorid",
    "eisen": "eisen", "zink": "zink", "kupfer": "kupfer", "mangan": "mangan", "selen": "selen", "jod": "jod",
    "chrom": "chrom", "molybdan": "molybdaen", "fluorid": "fluorid", "omega 3": "omega3", "omega 3 fettsauren": "omega3",
    "epa": "epa", "eicosapentaensaure": "epa", "dha": "dha", "docosahexaensaure": "dha", "ala": "ala",
    "alpha linolensaure": "ala", "omega 6": "omega6", "kreatin": "kreatin", "creatin": "kreatin",
    "kreatin monohydrat": "kreatin", "creatine monohydrate": "kreatin",
}


class FotoFehler(Exception):
    """Verstaendliche Meldung fuer den Benutzer (kein technischer Text)."""


def verkleinern(daten, mime="image/jpeg"):
    """Bild auf hoechstens MAX_KANTE Pixel, als JPEG. Ohne Pillow oder bei unbekanntem Format: unveraendert.
    -> (bytes, mime)"""
    try:
        from PIL import Image, ImageOps
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(daten)))      # Handyfotos richtig herum
        img = img.convert("RGB")
        img.thumbnail((MAX_KANTE, MAX_KANTE))
        aus = io.BytesIO()
        img.save(aus, "JPEG", quality=82)
        return aus.getvalue(), "image/jpeg"
    except Exception:
        return daten, mime


def gemini(key, modell, prompt, bild, mime, post, timeout=60):
    """Ein Bild + Anweisung an Gemini -> Antworttext (JSON). Fehler als FotoFehler mit verstaendlichem Text."""
    if not key:
        raise FotoFehler("Für die Foto-Erkennung fehlt der Gemini-Schlüssel (GEMINI_API_KEY) in den App-Einstellungen.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modell}:generateContent"
    try:
        r = post(url, headers={"x-goog-api-key": key, "Content-Type": "application/json"}, timeout=timeout,
                 json={"contents": [{"parts": [{"text": prompt},
                                               {"inline_data": {"mime_type": mime,
                                                                "data": base64.b64encode(bild).decode()}}]}],
                       "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1}})
    except Exception as e:
        logging.warning(f"Foto-Erkennung: {type(e).__name__}")
        raise FotoFehler("Die Foto-Erkennung ist gerade nicht erreichbar. Bitte versuche es erneut.") from None
    if r.status_code == 429:
        raise FotoFehler("Das kostenlose Kontingent der Foto-Erkennung ist gerade ausgeschöpft. Bitte später erneut versuchen.")
    if r.status_code != 200:
        logging.warning(f"Foto-Erkennung: HTTP {r.status_code}")
        raise FotoFehler("Die Foto-Erkennung hat gerade nicht funktioniert. Bitte versuche es erneut.")
    try:
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError, ValueError):
        raise FotoFehler("Auf dem Foto wurde nichts erkannt. Bitte ein schärferes Foto versuchen.") from None


def _json(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        m = re.search(r"\{.*\}", str(text or ""), re.S)          # JSON in Text eingebettet
        try:
            return json.loads(m.group(0)) if m else None
        except ValueError:
            return None


def _zahl(x, lo, hi):
    try:
        z = float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return z if lo <= z <= hi else None


def mahlzeit_auswerten(text, alle):
    """Antwort -> {"posten": [{"name", "gramm", "sicherheit", "vorschlaege": [Lebensmittel]}], "hinweis"}.
    Je erkanntem Lebensmittel die besten Treffer aus der eigenen Datenbank (der erste ist vorausgewaehlt)."""
    d = _json(text)
    if not isinstance(d, dict) or not isinstance(d.get("lebensmittel"), list):
        raise FotoFehler("Die Antwort der Foto-Erkennung war unvollständig. Bitte versuche es erneut.")
    posten = []
    for x in d["lebensmittel"][:MAX_POSTEN]:
        if not isinstance(x, dict) or not str(x.get("name") or "").strip():
            continue
        name = str(x["name"]).strip()[:60]
        gramm = _zahl(x.get("menge_g"), 1, 3000) or 100.0
        vorschlaege = L.suchen(name, alle, limit=5)
        if not vorschlaege:                                   # erstes Wort ("Hähnchenbrust, gebraten" -> "Hähnchenbrust")
            vorschlaege = L.suchen(re.split(r"[ ,(]", name)[0], alle, limit=5)
        sicherheit = str(x.get("sicherheit") or "mittel").lower()
        posten.append({"name": name, "gramm": round(gramm), "vorschlaege": vorschlaege,
                       "sicherheit": sicherheit if sicherheit in ("hoch", "mittel", "niedrig") else "mittel"})
    return {"posten": posten, "hinweis": str(d.get("hinweis") or "")[:200]}


def _schluessel(name):
    t = L._norm(name)
    t = re.sub(r"\(.*?\)", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def naehrstoff_id(name):
    """Bezeichnung auf einem Etikett -> Naehrstoff-ID oder None."""
    k = _schluessel(name)
    if k in SYNONYME:
        return SYNONYME[k]
    for nid, n in N.NAEHRSTOFFE.items():
        if _schluessel(n.name) == k:
            return nid
    for syn, nid in sorted(SYNONYME.items(), key=lambda x: -len(x[0])):   # "Vitamin D3 (Cholecalciferol) 1000 IE"
        if re.search(rf"\b{re.escape(syn)}\b", k):
            return nid
    return None


def etikett_auswerten(text, formen):
    """Antwort -> {"name", "hersteller", "form", "portion", "inhalt": [{"n", "menge", "einheit"}],
    "unbekannt": [Text]} - nicht zuordenbare oder nicht umrechenbare Angaben landen in "unbekannt"."""
    d = _json(text)
    if not isinstance(d, dict):
        raise FotoFehler("Das Etikett konnte nicht gelesen werden. Bitte ein schärferes Foto versuchen.")
    inhalt, unbekannt = [], []
    for x in (d.get("inhalt") or [])[:30]:
        if not isinstance(x, dict):
            continue
        roh = str(x.get("naehrstoff") or "").strip()
        menge = _zahl(x.get("menge"), 0, 100000)
        einheit = {"mcg": "µg", "ug": "µg", "μg": "µg", "iu": "IE", "i.e.": "IE", "ie": "IE"}.get(
            str(x.get("einheit") or "").strip().lower(), str(x.get("einheit") or "").strip())
        nid = naehrstoff_id(roh)
        if nid and menge is not None and N.in_basis(nid, menge, einheit) is not None:
            inhalt.append({"n": nid, "menge": menge, "einheit": einheit})
        elif roh:
            wert = "" if menge is None else f"{menge:g}".replace(".", ",")
            unbekannt.append(f"{roh} {wert} {einheit}".strip())
    form = str(d.get("form") or "").strip().capitalize()
    return {"name": str(d.get("produkt") or "").strip()[:60], "hersteller": str(d.get("hersteller") or "").strip()[:60],
            "form": form if form in formen else formen[0], "portion": str(d.get("portion") or "1 Portion").strip()[:30],
            "inhalt": inhalt, "unbekannt": unbekannt}
