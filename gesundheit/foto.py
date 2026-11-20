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
import time

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


ERSATZ_MODELL = "gemini-2.5-flash-lite"   # wenn das Hauptmodell ueberlastet oder nicht verfuegbar ist
VORUEBERGEHEND = (500, 502, 503, 504)


def _fehlergrund(r):
    """Status und Grund aus Googles Fehlerantwort (z. B. "INVALID_ARGUMENT", "API_KEY_INVALID") - ohne Schluessel."""
    try:
        e = (r.json() or {}).get("error") or {}
    except Exception:
        return "", ""
    gruende = [d.get("reason", "") for d in e.get("details") or [] if isinstance(d, dict)]
    return str(e.get("status") or ""), " ".join(g for g in gruende if g) + " " + str(e.get("message") or "")


def _fehler_text(code, status, grund):
    g = grund.lower()
    if code == 429:
        return "Das kostenlose Kontingent der Foto-Erkennung ist gerade ausgeschöpft. Bitte später erneut versuchen."
    if "api_key_invalid" in g or "api key not valid" in g or "api key expired" in g:
        return ("Google akzeptiert den Gemini-Schlüssel nicht (ungültig oder abgelaufen). Bitte in den App-Einstellungen "
                "(Secrets) GEMINI_API_KEY prüfen bzw. in Google AI Studio einen neuen Schlüssel erstellen.")
    if "location" in g and "not supported" in g:
        return "Die Foto-Erkennung ist vom Server-Standort aus gerade nicht verfügbar (Fehler 400)."
    if code == 403:
        return ("Der Gemini-Schlüssel hat keinen Zugriff auf die Gemini-API (Fehler 403). Bitte in Google AI Studio "
                "einen neuen Schlüssel ohne Einschränkungen erstellen und in den App-Einstellungen eintragen.")
    if code in VORUEBERGEHEND:
        return f"Die Foto-Erkennung ist bei Google gerade überlastet (Fehler {code}). Bitte in einer Minute erneut versuchen."
    if code == 400:
        return "Google hat das Foto nicht angenommen (Fehler 400). Bitte ein anderes Foto versuchen."
    return f"Die Foto-Erkennung hat gerade nicht funktioniert (Fehler {code}). Bitte versuche es erneut."


def gemini(key, modell, prompt, bild, mime, post, timeout=45, warten=None):
    """Ein Bild + Anweisung an Gemini -> Antworttext (JSON). Fehler als FotoFehler mit verstaendlichem Text.
    Voruebergehende Fehler (Ueberlastung): einmal kurz wiederholen, dann das Ersatzmodell. Modell nicht gefunden:
    gleich das Ersatzmodell."""
    if not key:
        raise FotoFehler("Für die Foto-Erkennung fehlt der Gemini-Schlüssel (GEMINI_API_KEY) in den App-Einstellungen.")
    warten = warten or time.sleep
    body = {"contents": [{"parts": [{"text": prompt},
                                    {"inline_data": {"mime_type": mime, "data": base64.b64encode(bild).decode()}}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1}}
    versuche = [modell, modell] + ([ERSATZ_MODELL] if modell != ERSATZ_MODELL else [])
    letzter = None
    for n, m in enumerate(versuche):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
        try:
            r = post(url, headers={"x-goog-api-key": key, "Content-Type": "application/json"}, timeout=timeout, json=body)
        except Exception as e:
            logging.warning(f"Foto-Erkennung ({m}): {type(e).__name__}")
            letzter = "Die Foto-Erkennung ist gerade nicht erreichbar. Bitte versuche es erneut."
            if n >= 1:                                          # Netz weg/Zeitueberschreitung: nicht ewig warten
                break
            continue
        if r.status_code == 200:
            try:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError, TypeError, ValueError):
                raise FotoFehler("Auf dem Foto wurde nichts erkannt. Bitte ein schärferes Foto versuchen.") from None
        status, grund = _fehlergrund(r)
        logging.warning(f"Foto-Erkennung ({m}): HTTP {r.status_code} {status} {grund[:160]}")
        letzter = _fehler_text(r.status_code, status, grund)
        if r.status_code in VORUEBERGEHEND:
            if n == 0:
                warten(2)
            continue
        if r.status_code == 404 and m == modell and n == 0:     # Modell (nicht mehr) verfuegbar -> Ersatzmodell
            if modell != ERSATZ_MODELL:
                versuche[1:] = [ERSATZ_MODELL]
                continue
        break                                                   # Schluessel/Foto/Kontingent: Wiederholen hilft nicht
    raise FotoFehler(letzter)


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
