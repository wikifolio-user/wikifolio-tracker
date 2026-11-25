"""Durchschnittskurs-Rechner - Rechenkern (ohne Streamlit).

Gewichteter durchschnittlicher Einkaufskurs von Aktien, ETFs und Kryptowaehrungen ueber beliebig viele Kaeufe:

    Durchschnittskurs = Summe aller Kaufwerte inklusive Kaufgebuehren / Summe aller Stueckzahlen

Je Kauf wird entweder der Kurs je Stueck oder der Gesamtwert eingegeben; der andere Wert wird berechnet.
Gerechnet wird mit Decimal (keine Rundungsfehler von Gleitkommazahlen), Eingaben mit bis zu 8 Nachkommastellen,
deutsches Zahlenformat ("1.234,56789") und Punkt-Format ("1234.5") werden beide verstanden.
Der Rechner ist unabhaengig vom Depot: es werden keine Depotdaten gelesen oder veraendert."""
import json
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

NACHKOMMA = 8
MAX_WERT = Decimal("1e15")
ARTEN = {"kurs": "Kurs je Stück", "gesamt": "Gesamtwert"}
WAEHRUNGEN = {"EUR": "€", "USD": "$", "CHF": "CHF", "GBP": "£"}
MAX_KAEUFE = 500


class EingabeFehler(ValueError):
    pass


def zahl(text, feld="Wert", leer_null=False, null_erlaubt=False):
    """Text -> Decimal >= 0 mit hoechstens 8 Nachkommastellen. Versteht 1.234,56 / 1234,56 / 1234.56 / 1,234.56.
    Leer: 0 (leer_null) oder Fehler."""
    if isinstance(text, (int, float, Decimal)) and not isinstance(text, bool):
        s = repr(text) if isinstance(text, float) else str(text)
    else:
        s = str(text if text is not None else "").strip()
    s = s.replace(" ", "").replace(" ", "").replace("€", "").replace("$", "").replace("'", "")
    if not s:
        if leer_null:
            return Decimal(0)
        raise EingabeFehler(f"{feld} fehlt.")
    if "," in s and "." in s:                       # Tausendertrenner: das letzte Zeichen ist das Dezimalzeichen
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        if s.count(",") > 1:
            raise EingabeFehler(f"{feld}: „{text}“ ist keine gültige Zahl.")
        s = s.replace(",", ".")
    elif s.count(".") == 1 and re.fullmatch(r"[1-9]\d{0,2}\.\d{3}", s):
        # "5.000" kann 5000 (deutsch) oder 5,0 (englisch) heissen - nicht raten
        raise EingabeFehler(f"{feld}: „{text}“ ist mehrdeutig – bitte {s.replace('.', '')} (Tausender) oder "
                            f"{s.replace('.', ',')} (Dezimal) schreiben.")
    elif s.count(".") > 1:                          # 1.234.567 -> Tausenderpunkte
        teile = s.split(".")
        if all(len(t) == 3 for t in teile[1:]):
            s = "".join(teile)
        else:
            raise EingabeFehler(f"{feld}: „{text}“ ist keine gültige Zahl.")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise EingabeFehler(f"{feld}: „{text}“ ist keine gültige Zahl.") from None
    if not d.is_finite():
        raise EingabeFehler(f"{feld}: „{text}“ ist keine gültige Zahl.")
    if d < 0:
        raise EingabeFehler(f"{feld} darf nicht negativ sein.")
    if d == 0 and not null_erlaubt:
        raise EingabeFehler(f"{feld} muss größer als 0 sein.")
    if d > MAX_WERT:
        raise EingabeFehler(f"{feld} ist zu groß.")
    if -d.as_tuple().exponent > NACHKOMMA:
        raise EingabeFehler(f"{feld}: höchstens {NACHKOMMA} Nachkommastellen.")
    return d


def kauf_pruefen(k):
    """Ein Kauf {"stueck", "art": kurs/gesamt, "kurs", "gesamt", "gebuehr"} (Texte) ->
    {"stueck", "kurs", "kaufwert", "gebuehr", "summe"} als Decimal. Wirft EingabeFehler."""
    stueck = zahl(k.get("stueck"), "Stückzahl")
    art = k.get("art") if k.get("art") in ARTEN else "kurs"
    if art == "kurs":
        kurs = zahl(k.get("kurs"), "Kurs je Stück")
        kaufwert = stueck * kurs
    else:
        kaufwert = zahl(k.get("gesamt"), "Gesamtwert")
        kurs = kaufwert / stueck
    gebuehr = zahl(k.get("gebuehr"), "Gebühr", leer_null=True, null_erlaubt=True)
    return {"stueck": stueck, "kurs": kurs, "kaufwert": kaufwert, "gebuehr": gebuehr, "summe": kaufwert + gebuehr,
            "art": art}


def berechnen(kaeufe, mit_gebuehren=True):
    """-> {"anzahl", "stueck", "kaufwert", "gebuehren", "investition", "durchschnitt", "durchschnitt_ohne",
    "zeilen": [geprueft oder {"fehler"}], "fehler": [(nr, text)]}. Ungueltige Kaeufe zaehlen nicht mit;
    leere Zeilen werden uebergangen."""
    zeilen, fehler = [], []
    for nr, k in enumerate(kaeufe or [], 1):
        if leer(k):
            zeilen.append(None)
            continue
        try:
            z = kauf_pruefen(k)
            if not mit_gebuehren:
                z["gebuehr"], z["summe"] = Decimal(0), z["kaufwert"]
            zeilen.append(z)
        except EingabeFehler as ex:
            zeilen.append({"fehler": str(ex)})
            fehler.append((nr, str(ex)))
    ok = [z for z in zeilen if z and "fehler" not in z]
    stueck = sum((z["stueck"] for z in ok), Decimal(0))
    kaufwert = sum((z["kaufwert"] for z in ok), Decimal(0))
    gebuehren = sum((z["gebuehr"] for z in ok), Decimal(0))
    investition = kaufwert + gebuehren
    return {"anzahl": len(ok), "stueck": stueck, "kaufwert": kaufwert, "gebuehren": gebuehren,
            "investition": investition, "durchschnitt": investition / stueck if stueck else None,
            "durchschnitt_ohne": kaufwert / stueck if stueck else None, "zeilen": zeilen, "fehler": fehler}


def leer(k):
    return not any(str((k or {}).get(f) or "").strip() for f in ("stueck", "kurs", "gesamt", "gebuehr"))


def nachkauf(ergebnis, stueck, kurs, gebuehr=0):
    """Hypothetischer Nachkauf: neuer Durchschnitt, wenn zusaetzlich stueck zum kurs gekauft wuerden."""
    s = zahl(stueck, "Stückzahl")
    k = zahl(kurs, "Kurs je Stück")
    g = zahl(gebuehr, "Gebühr", leer_null=True, null_erlaubt=True)
    gesamt_stueck = ergebnis["stueck"] + s
    invest = ergebnis["investition"] + s * k + g
    return {"stueck": gesamt_stueck, "investition": invest, "durchschnitt": invest / gesamt_stueck}


# ---------------------------------------------------------------------------------------------------- Format
def de(x, n=2, min_n=None):
    """Decimal/Zahl -> deutsches Format. n = hoechstens Nachkommastellen; min_n = mindestens (Standard n)."""
    if x is None:
        return "–"
    d = Decimal(str(x)) if not isinstance(x, Decimal) else x
    d = d.quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP)
    s = f"{d:,.{n}f}"
    if min_n is not None and min_n < n and "." in s:
        ganz, nach = s.split(".")
        nach = nach.rstrip("0")
        nach = nach + "0" * max(0, min_n - len(nach))
        s = ganz + ("." + nach if nach else "")
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def geld(x, waehrung="EUR", n=2):
    if x is None:
        return "–"
    z = WAEHRUNGEN.get(waehrung, waehrung)
    return f"{de(x, n)} {z}"


def kurs_text(x, waehrung="EUR"):
    """Kurs: mindestens 2, hoechstens 8 Nachkommastellen (fuer Krypto-Bruchteile)."""
    if x is None:
        return "–"
    return f"{de(x, NACHKOMMA, 2)} {WAEHRUNGEN.get(waehrung, waehrung)}"


def stueck_text(x):
    return "–" if x is None else de(x, NACHKOMMA, 0)


# ---------------------------------------------------------------------------------------------------- Speicher
def speichern(kaeufe):
    """Kaeufe als JSON-Text (nur bekannte Felder, Texte - so bleibt jede Nachkommastelle erhalten)."""
    aus = []
    for k in (kaeufe or [])[:MAX_KAEUFE]:
        aus.append({"stueck": str(k.get("stueck") or "")[:40], "art": k.get("art") if k.get("art") in ARTEN else "kurs",
                    "kurs": str(k.get("kurs") or "")[:40], "gesamt": str(k.get("gesamt") or "")[:40],
                    "gebuehr": str(k.get("gebuehr") or "")[:40], "notiz": str(k.get("notiz") or "")[:80]})
    return json.dumps(aus, ensure_ascii=False)


def laden(text):
    try:
        daten = json.loads(text or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(daten, list):
        return []
    return json.loads(speichern([k for k in daten if isinstance(k, dict)]))
