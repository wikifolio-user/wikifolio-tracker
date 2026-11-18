"""Statistik, Wochenvergleich, Kalender und Export - ohne Streamlit, getestet in test_gesundheit.py.

Nur mathematische Auswertung der dokumentierten Werte - keine Diagnosen. Tage ohne Eintraege zaehlen bei
Durchschnitten NICHT als 0 (sonst wuerde jeder vergessene Tag den Schnitt verfaelschen).
"""
import csv
import datetime
import io
import json

from . import fasten as FA
from . import mikro as MI
from . import speicher as S
from . import sport as SP
from . import supplements as SU

ZEITRAEUME = {"7 Tage": 7, "14 Tage": 14, "30 Tage": 30, "Monat": "monat", "Quartal": 91, "Jahr": 365}


def zeitraum(name, heute, von=None, bis=None):
    """-> (von, bis) einschliesslich. "Monat" = aktueller Kalendermonat; "Eigener" mit von/bis."""
    if name == "Eigener" and von and bis:
        return (min(von, bis), max(von, bis))
    n = ZEITRAEUME.get(name, 7)
    if n == "monat":
        return heute.replace(day=1), heute
    return heute - datetime.timedelta(days=n - 1), heute


def monate_zwischen(von, bis):
    """Erste Tage aller Monate im Zeitraum (fuer das Laden der Monatsdateien)."""
    aus, d = [], von.replace(day=1)
    while d <= bis:
        aus.append(d)
        d = (d.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    return aus


def tageswerte(tag, t, doc):
    """Ein Tag -> Kennzahlen. erfasst = es gibt Ernaehrungseintraege (nur dann zaehlt er fuer Ernaehrungs-Schnitte)."""
    su = S.tag_summen(t)
    n = su["naehrwerte"]
    sport_kcal, sport_min = SP.summe(t)
    geplant = [x for l in SU.tagesplan((doc or {}).get("supplements") or [], tag).values() for x in l]
    eingenommen = sum(1 for x in t.get("supplements") or [] if x.get("status") == "eingenommen")
    fasten = FA.am_tag(FA.zustand(doc)["verlauf"], tag)
    return {"datum": tag, "erfasst": bool(t.get("essen") or t.get("trinken")),
            "kcal": su["kcal"], "protein": n["protein"]["wert"], "kh": n["kh"]["wert"], "fett": n["fett"]["wert"],
            "ballast": n["ballast"]["wert"], "zucker": n["zucker"]["wert"],
            "fluessigkeit_ml": su["fluessigkeit_ml"], "sport_kcal": sport_kcal, "sport_min": sport_min,
            "gewicht": t.get("gewicht"), "supp_ein": eingenommen, "supp_geplant": len(geplant),
            "fasten_h": max((d for d, _, _ in fasten), default=None), "masse": dict(t.get("masse") or {}),
            "_tag": t}


def reihe(von, bis, monat_doc_von, doc):
    """Tageswerte fuer jeden Tag im Zeitraum. monat_doc_von(datum) -> Monatsdokument."""
    aus, d = [], von
    while d <= bis:
        aus.append(tageswerte(d, S.tag_aus(monat_doc_von(d), d), doc))
        d += datetime.timedelta(days=1)
    return aus


def _schnitt(werte):
    werte = [w for w in werte if w is not None]
    return sum(werte) / len(werte) if werte else None


def zusammenfassung(r):
    """Durchschnitte (nur ueber erfasste Tage), Sporttage, Gewichtsveraenderung, Supplement-Treue."""
    erfasst = [x for x in r if x["erfasst"]]
    gew = [(x["datum"], x["gewicht"]) for x in r if x["gewicht"]]
    geplant = sum(x["supp_geplant"] for x in r)
    fasten = [x["fasten_h"] for x in r if x["fasten_h"] is not None]
    return {"tage": len(r), "erfasst": len(erfasst),
            **{k: _schnitt([x[k] for x in erfasst]) for k in ("kcal", "protein", "kh", "fett", "fluessigkeit_ml")},
            "sport_tage": sum(1 for x in r if x["sport_min"] > 0), "sport_kcal": sum(x["sport_kcal"] for x in r),
            "sport_min": sum(x["sport_min"] for x in r),
            "gewicht_start": gew[0][1] if gew else None, "gewicht_ende": gew[-1][1] if gew else None,
            "gewicht_diff": (gew[-1][1] - gew[0][1]) if len(gew) >= 2 else None,
            "gewicht_von": gew[0][0] if gew else None,
            "supp_treue": (sum(x["supp_ein"] for x in r) / geplant * 100) if geplant else None,
            "fasten_anzahl": len(fasten), "fasten_schnitt": _schnitt(fasten)}


def _z(x, stellen=0):
    return f"{x:,.{stellen}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def aussagen(z, name="im Zeitraum"):
    """Verstaendliche Saetze zur Zusammenfassung - nur Rechnung, keine Bewertung oder Diagnose."""
    s = []
    if not z["erfasst"]:
        return [f"Für {name} ist noch keine Ernährung dokumentiert."]
    s.append(f"Du hast {name} an {z['erfasst']} von {z['tage']} Tagen Ernährung dokumentiert.")
    if z["kcal"] is not None:
        s.append(f"Durchschnittlich {_z(z['kcal'])} kcal pro dokumentiertem Tag.")
    if z["protein"] is not None:
        s.append(f"Deine durchschnittliche Proteinzufuhr lag bei {_z(z['protein'])} g.")
    if z["fluessigkeit_ml"] is not None:
        s.append(f"Im Schnitt hast du {_z(z['fluessigkeit_ml'] / 1000, 1)} L getrunken.")
    if z["sport_tage"]:
        s.append(f"Du hast an {z['sport_tage']} Tagen Sport eingetragen ({_z(z['sport_min'])} Minuten insgesamt).")
    if z["gewicht_diff"] is not None:
        d = z["gewicht_diff"]
        s.append("Dein Gewicht ist gleich geblieben." if abs(d) < 0.05 else
                 f"Dein Gewicht hat sich seit {z['gewicht_von'].strftime('%d.%m.')} um "
                 f"{'+' if d > 0 else ''}{_z(d, 1)} kg verändert.")
    if z["supp_treue"] is not None:
        s.append(f"Von den geplanten Supplements hast du {_z(z['supp_treue'])} % eingenommen.")
    if z["fasten_anzahl"]:
        s.append(f"{z['fasten_anzahl']} Fastenzeiten, im Schnitt {FA.dauer_text(z['fasten_schnitt'])}.")
    return s


def veraenderung(neu, alt):
    """Prozentuale Veraenderung oder None (ohne Vergleichswert)."""
    if neu is None or alt in (None, 0):
        return None
    return (neu - alt) / abs(alt) * 100


def wochenvergleich(diese, letzte, naehrstoff="magnesium"):
    """Diese gegen letzte Woche (je 7 Tageswerte) -> [(Bezeichnung, diese, letzte, Veraenderung %, Einheit)].
    Gewicht als Differenz in kg statt Prozent."""
    zd, zl = zusammenfassung(diese), zusammenfassung(letzte)

    def mikro(r):
        return MI.durchschnitt([x["_tag"] for x in r if x["erfasst"]], naehrstoff)[0]
    zeilen = [("Kalorien", zd["kcal"], zl["kcal"], "kcal"), ("Protein", zd["protein"], zl["protein"], "g"),
              ("Getrunken", zd["fluessigkeit_ml"], zl["fluessigkeit_ml"], "ml"),
              ("Sport", zd["sport_min"], zl["sport_min"], "min"),
              (S.MI_NAME.get(naehrstoff, naehrstoff), mikro(diese), mikro(letzte), S.MI_EINHEIT.get(naehrstoff, ""))]
    aus = [(n, a, b, veraenderung(a, b), e) for n, a, b, e in zeilen]
    g_d = [x["gewicht"] for x in diese if x["gewicht"]]
    g_l = [x["gewicht"] for x in letzte if x["gewicht"]]
    if g_d and g_l:
        aus.append(("Gewicht", _schnitt(g_d), _schnitt(g_l), None, "kg"))
    return aus


def kalender_zeichen(x):
    """Kleine Kennzeichen eines Tages (fuer die Kalenderansicht): Text-Symbole, nie nur Farbe."""
    z = []
    if x["erfasst"] and x["kcal"]:
        z.append("🍽")
    if x["fluessigkeit_ml"]:
        z.append("💧")
    if x["sport_min"]:
        z.append("🏃")
    if x["gewicht"]:
        z.append("⚖")
    if x["supp_ein"]:
        z.append("💊")
    if x["fasten_h"] is not None:
        z.append("⏱")
    return z


# ---------------------------------------------------------------- Export
CSV_SPALTEN = [("datum", "Datum"), ("kcal", "Kalorien (kcal)"), ("protein", "Protein (g)"),
               ("kh", "Kohlenhydrate (g)"), ("fett", "Fett (g)"), ("ballast", "Ballaststoffe (g)"),
               ("zucker", "Zucker (g)"), ("fluessigkeit_ml", "Getrunken (ml)"), ("sport_min", "Sport (min)"),
               ("sport_kcal", "Sport (kcal)"), ("gewicht", "Gewicht (kg)"), ("supp_ein", "Supplements eingenommen"),
               ("supp_geplant", "Supplements geplant"), ("fasten_h", "Fasten (h)")]


def als_csv(r):
    """Tageswerte als CSV (Semikolon, deutsches Dezimalkomma - oeffnet sich direkt in Excel)."""
    f = io.StringIO()
    w = csv.writer(f, delimiter=";")
    w.writerow([t for _, t in CSV_SPALTEN] + [n for _, n, _ in S.MASSE])
    for x in r:
        zeile = []
        for k, _ in CSV_SPALTEN:
            v = x.get(k)
            zeile.append(v.isoformat() if isinstance(v, datetime.date) else
                         "" if v is None else str(round(v, 1) if isinstance(v, float) else v).replace(".", ","))
        zeile += ["" if x["masse"].get(k) is None else str(x["masse"][k]).replace(".", ",") for k, _, _ in S.MASSE]
        w.writerow(zeile)
    return "﻿" + f.getvalue()          # BOM: Excel erkennt UTF-8 (Umlaute)


def als_json(doc, monate):
    """Alle gespeicherten Gesundheitsdaten (Profil + alle Monate) als JSON - vollstaendiger Export (DSGVO)."""
    return json.dumps({"export": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                       "profil": doc, "monate": monate}, ensure_ascii=False, indent=1, default=str)
