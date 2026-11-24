"""Faceless YouTube - Finanzen (Phase 1): Finanzrechner mit Szenarien und das Kanal-Kassenbuch. Reine Rechenlogik.

Getrennt gehalten:
  * TATSAECHLICHE Einnahmen/Ausgaben (Kassenbuch, von Hand oder spaeter aus angebundenen Quellen erfasst)
  * PROGNOSEN (Finanzrechner) - werden nie als verdientes Geld gebucht und sind immer als Schaetzung gekennzeichnet.

Formeln:
  YouTube-Umsatz   = Views / 1000 x RPM            (erst ab Aufnahme ins Partnerprogramm, vorher 0)
  Affiliate-Umsatz = Views x Klickrate x Conversion-Rate x Provision
  Gesamtumsatz     = YouTube + Affiliate + Sponsoring + sonstige Einnahmen
  Gewinn           = Gesamtumsatz - Gesamtkosten (laufend + einmalig)"""
import datetime
import uuid

KATEGORIEN_EIN = {"werbung": "YouTube-Werbung", "affiliate": "Affiliate-Provision", "sponsoring": "Sponsoring",
                  "sonstiges_ein": "Sonstige Einnahmen"}
KATEGORIEN_AUS = {"produktion": "Produktion", "ki": "KI-Tools / APIs", "software": "Software / Abos",
                  "investition": "Einmalige Investition", "sonstiges_aus": "Sonstige Ausgaben"}

# Szenarien: Faktoren auf Views und RPM, monatliches Wachstum der Views, Start der Werbeeinnahmen (Monat)
SZENARIEN = {
    "konservativ": {"name": "Konservativ", "views_faktor": 0.5, "rpm_faktor": 0.7, "wachstum_pct": 5.0,
                    "monetarisierung_ab": 9},
    "realistisch": {"name": "Realistisch", "views_faktor": 1.0, "rpm_faktor": 1.0, "wachstum_pct": 10.0,
                    "monetarisierung_ab": 6},
    "optimistisch": {"name": "Optimistisch", "views_faktor": 1.5, "rpm_faktor": 1.2, "wachstum_pct": 20.0,
                     "monetarisierung_ab": 4},
}
ZEITRAEUME = (3, 6, 12)

STANDARD_EINGABEN = {
    "views_monat": 20000.0, "rpm": 4.0, "klickrate_pct": 1.0, "conversion_pct": 2.0, "provision": 20.0,
    "sponsoring_monat": 0.0, "sonstige_ein_monat": 0.0, "videos_monat": 8, "kanaele": 1,
    "produktion_monat": 0.0, "ki_monat": 20.0, "sonstige_kosten_monat": 0.0, "einmalig": 0.0,
}


def _zahl(x, name):
    try:
        x = float(x)
    except (TypeError, ValueError):
        raise ValueError(f"{name} ist keine Zahl.") from None
    if x != x or x < 0:
        raise ValueError(f"{name} darf nicht negativ sein.")
    return x


def pruefe(e):
    """Eingaben pruefen und vervollstaendigen -> dict (wirft ValueError mit verstaendlichem Text)."""
    aus = dict(STANDARD_EINGABEN, **(e or {}))
    namen = {"views_monat": "Monatliche Views", "rpm": "RPM", "klickrate_pct": "Affiliate-Klickrate",
             "conversion_pct": "Conversion-Rate", "provision": "Provision", "sponsoring_monat": "Sponsoring",
             "sonstige_ein_monat": "Sonstige Einnahmen", "videos_monat": "Videos pro Monat", "kanaele": "Kanäle",
             "produktion_monat": "Produktionskosten", "ki_monat": "KI-Tool-Kosten",
             "sonstige_kosten_monat": "Sonstige Kosten", "einmalig": "Einmalige Investitionen"}
    for k, n in namen.items():
        aus[k] = _zahl(aus[k], n)
    for k in ("klickrate_pct", "conversion_pct"):
        if aus[k] > 100:
            raise ValueError(f"{namen[k]} kann nicht über 100 % liegen.")
    if aus["rpm"] > 100:
        raise ValueError("Ein RPM über 100 € ist unrealistisch – bitte prüfen.")
    return aus


def monat(e, views=None, rpm=None, monetarisiert=True):
    """Ein Monat -> Umsaetze, Kosten, Gewinn, Kennzahlen (ohne einmalige Investitionen)."""
    v = e["views_monat"] if views is None else views
    r = e["rpm"] if rpm is None else rpm
    yt = v / 1000 * r if monetarisiert else 0.0
    aff = v * e["klickrate_pct"] / 100 * e["conversion_pct"] / 100 * e["provision"]
    ums = yt + aff + e["sponsoring_monat"] + e["sonstige_ein_monat"]
    kosten = e["produktion_monat"] + e["ki_monat"] + e["sonstige_kosten_monat"]
    gew = ums - kosten
    vid = e["videos_monat"] or 0
    return {"views": v, "rpm": r, "youtube": yt, "affiliate": aff, "sponsoring": e["sponsoring_monat"],
            "sonstige": e["sonstige_ein_monat"], "umsatz": ums, "kosten": kosten, "gewinn": gew,
            "marge_pct": gew / ums * 100 if ums else None,
            "umsatz_je_video": ums / vid if vid else None, "kosten_je_video": kosten / vid if vid else None,
            "umsatz_je_kanal": ums / e["kanaele"] if e["kanaele"] else None,
            "je_1000_views": ums / v * 1000 if v else None, "monetarisiert": monetarisiert}


def prognose(e, szenario="realistisch", monate=12):
    """Monat-fuer-Monat-Prognose eines Szenarios (Schaetzung!). Views wachsen je Monat um wachstum_pct,
    Werbeeinnahmen erst ab monetarisierung_ab. -> {"monate": [...], "summe": {...}, "roi_pct", "break_even"}"""
    e = pruefe(e)
    s = SZENARIEN[szenario]
    zeilen, kum = [], -e["einmalig"]
    break_even = None
    for m in range(1, monate + 1):
        v = e["views_monat"] * s["views_faktor"] * (1 + s["wachstum_pct"] / 100) ** (m - 1)
        z = monat(e, v, e["rpm"] * s["rpm_faktor"], m >= s["monetarisierung_ab"])
        kum += z["gewinn"]
        z.update(monat_nr=m, kumuliert=kum)
        if break_even is None and kum >= 0:
            break_even = m
        zeilen.append(z)
    summe = {k: sum(z[k] for z in zeilen) for k in ("views", "youtube", "affiliate", "sponsoring", "sonstige",
                                                      "umsatz", "kosten", "gewinn")}
    summe["kosten_gesamt"] = summe["kosten"] + e["einmalig"]
    summe["gewinn_nach_invest"] = summe["gewinn"] - e["einmalig"]
    return {"szenario": szenario, "name": s["name"], "annahmen": s, "monate": zeilen, "summe": summe,
            "roi_pct": summe["gewinn_nach_invest"] / summe["kosten_gesamt"] * 100 if summe["kosten_gesamt"] else None,
            "marge_pct": summe["gewinn"] / summe["umsatz"] * 100 if summe["umsatz"] else None,
            "break_even": break_even, "schaetzung": True}


def alle_szenarien(e):
    """Je Szenario die Summen fuer 3, 6 und 12 Monate."""
    aus = {}
    for sz in SZENARIEN:
        p = prognose(e, sz, max(ZEITRAEUME))
        aus[sz] = {"prognose": p, "zeitraeume": {n: _bis(p, n, e) for n in ZEITRAEUME}}
    return aus


def _bis(p, n, e):
    z = p["monate"][:n]
    ums = sum(x["umsatz"] for x in z)
    kosten = sum(x["kosten"] for x in z) + pruefe(e)["einmalig"]
    gew = ums - kosten
    return {"umsatz": ums, "kosten": kosten, "gewinn": gew, "roi_pct": gew / kosten * 100 if kosten else None}


# ---------------------------------------------------------------- Kassenbuch (tatsaechliche Werte)
def neuer_kanal(name, sprache="de", markt="DE", nische="", status="geplant", start=None):
    name = (name or "").strip()
    if not name:
        raise ValueError("Bitte einen Kanalnamen angeben.")
    if status not in ("geplant", "aktiv", "pausiert", "beendet"):
        raise ValueError("Unbekannter Status.")
    return {"id": uuid.uuid4().hex[:8], "name": name[:80], "sprache": sprache, "markt": markt,
            "nische": (nische or "").strip()[:80], "status": status, "start": start or datetime.date.today().isoformat()}


def neue_buchung(datum, art, kategorie, betrag, kanal_id=None, notiz=""):
    """Tatsaechliche Einnahme oder Ausgabe. betrag immer positiv; art bestimmt das Vorzeichen."""
    if art not in ("einnahme", "ausgabe"):
        raise ValueError("Art muss Einnahme oder Ausgabe sein.")
    erlaubt = KATEGORIEN_EIN if art == "einnahme" else KATEGORIEN_AUS
    if kategorie not in erlaubt:
        raise ValueError("Die Kategorie passt nicht zur Art der Buchung.")
    b = _zahl(betrag, "Betrag")
    if b <= 0:
        raise ValueError("Der Betrag muss größer als 0 sein.")
    try:
        d = datetime.date.fromisoformat(str(datum)[:10])
    except ValueError:
        raise ValueError("Ungültiges Datum.") from None
    if d > datetime.date.today():
        raise ValueError("Tatsächliche Buchungen dürfen nicht in der Zukunft liegen (Prognosen gehören in den "
                         "Finanzrechner).")
    return {"id": uuid.uuid4().hex[:10], "datum": d.isoformat(), "art": art, "kategorie": kategorie,
            "betrag": round(b, 2), "kanal": kanal_id, "notiz": (notiz or "").strip()[:200]}


def auswertung(buchungen, kanal_id=None, von=None, bis=None):
    """Summen der tatsaechlichen Buchungen (optional je Kanal/Zeitraum)."""
    liste = [b for b in buchungen or [] if (kanal_id is None or b.get("kanal") == kanal_id)
             and (not von or b["datum"] >= von) and (not bis or b["datum"] <= bis)]
    ein = sum(b["betrag"] for b in liste if b["art"] == "einnahme")
    aus = sum(b["betrag"] for b in liste if b["art"] == "ausgabe")
    je_kat = {}
    for b in liste:
        je_kat[b["kategorie"]] = je_kat.get(b["kategorie"], 0.0) + b["betrag"]
    je_monat = {}
    for b in liste:
        m = je_monat.setdefault(b["datum"][:7], {"einnahmen": 0.0, "ausgaben": 0.0})
        m["einnahmen" if b["art"] == "einnahme" else "ausgaben"] += b["betrag"]
    for m in je_monat.values():
        m["gewinn"] = m["einnahmen"] - m["ausgaben"]
    gewinn = ein - aus
    return {"einnahmen": ein, "ausgaben": aus, "gewinn": gewinn, "marge_pct": gewinn / ein * 100 if ein else None,
            "roi_pct": gewinn / aus * 100 if aus else None, "je_kategorie": je_kat,
            "je_monat": dict(sorted(je_monat.items())), "anzahl": len(liste)}
