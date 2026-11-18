"""Nahrungsergaenzung: Supplement-Datenbank, Einnahmeplan und Vorlagen - ohne Streamlit.

Ein Supplement (in profil.json unter "supplements"):
  {"id", "name", "hersteller", "form", "portion": "1 Kapsel", "inhalt": [{"n": naehrstoff, "menge", "einheit"}],
   "plan": {"zeit": "Morgens", "rhythmus": "taeglich"|"wochentage"|"intervall", "tage": [0..6], "alle": 2,
            "ab": "JJJJ-MM-TT", "portionen": 1}, "aktiv": True, "notiz": ""}
Inhalt je Portion in beliebigen Einheiten (mg, µg, g, IE) - umgerechnet wird erst beim Rechnen (naehrstoffe.in_basis).
Eine Einnahme (im Tag unter "supplements") speichert den umgerechneten Inhalt als Kopie: spaetere Aenderungen am
Produkt veraendern alte Tage nicht. Nur Eintraege mit status "eingenommen" zaehlen in der Tagesberechnung.
"""
import datetime

from . import naehrstoffe as N

FORMEN = ["Tablette", "Kapsel", "Softgel", "Pulver", "Flüssigkeit", "Tropfen", "Sachet", "Portion"]
ZEITEN = ["Morgens", "Mittags", "Abends", "Nachts"]
EINHEITEN = ["mg", "µg", "g", "IE"]
WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

# Vorlagen: haeufige Produkte mit typischem Inhalt - beim Anlegen vorbelegt und frei aenderbar (Etikett pruefen!)
VORLAGEN = [
    {"name": "Vitamin D3", "form": "Tablette", "portion": "1 Tablette", "zeit": "Morgens",
     "inhalt": [("vit_d", 1000, "IE")]},
    {"name": "Vitamin D3 + K2", "form": "Tropfen", "portion": "1 Portion", "zeit": "Morgens",
     "inhalt": [("vit_d", 25, "µg"), ("vit_k", 100, "µg")]},
    {"name": "Magnesium", "form": "Kapsel", "portion": "1 Kapsel", "zeit": "Abends", "inhalt": [("magnesium", 250, "mg")]},
    {"name": "Zink", "form": "Tablette", "portion": "1 Tablette", "zeit": "Abends", "inhalt": [("zink", 10, "mg")]},
    {"name": "Omega-3 (Fischöl)", "form": "Softgel", "portion": "1 Kapsel", "zeit": "Mittags",
     "inhalt": [("omega3", 0.3, "g"), ("epa", 180, "mg"), ("dha", 120, "mg")]},
    {"name": "Multivitamin", "form": "Tablette", "portion": "1 Tablette", "zeit": "Morgens",
     "inhalt": [("vit_a", 800, "µg"), ("vit_b1", 1.1, "mg"), ("vit_b2", 1.4, "mg"), ("vit_b3", 16, "mg"),
                ("vit_b5", 6, "mg"), ("vit_b6", 1.4, "mg"), ("vit_b7", 50, "µg"), ("vit_b9", 200, "µg"),
                ("vit_b12", 2.5, "µg"), ("vit_c", 80, "mg"), ("vit_d", 5, "µg"), ("vit_e", 12, "mg"),
                ("vit_k", 75, "µg"), ("zink", 10, "mg"), ("selen", 55, "µg"), ("jod", 150, "µg")]},
    {"name": "Vitamin B12", "form": "Tablette", "portion": "1 Tablette", "zeit": "Morgens",
     "inhalt": [("vit_b12", 500, "µg")]},
    {"name": "Vitamin C", "form": "Kapsel", "portion": "1 Kapsel", "zeit": "Morgens", "inhalt": [("vit_c", 500, "mg")]},
    {"name": "Calcium", "form": "Tablette", "portion": "1 Tablette", "zeit": "Abends", "inhalt": [("calcium", 500, "mg")]},
    {"name": "Eisen", "form": "Tablette", "portion": "1 Tablette", "zeit": "Morgens", "inhalt": [("eisen", 14, "mg")]},
    {"name": "Kreatin", "form": "Pulver", "portion": "1 Portion (5 g)", "zeit": "Mittags", "inhalt": [("kreatin", 5, "g")]},
    {"name": "Elektrolyte", "form": "Sachet", "portion": "1 Beutel", "zeit": "Mittags",
     "inhalt": [("natrium", 500, "mg"), ("kalium", 200, "mg"), ("magnesium", 60, "mg")]},
]


def neues(vorlage, sid, heute):
    """Supplement aus einer Vorlage (oder leer: vorlage=None) mit sinnvollem Standardplan (taeglich, 1 Portion)."""
    v = vorlage or {"name": "", "form": "Tablette", "portion": "1 Tablette", "zeit": "Morgens", "inhalt": []}
    return {"id": sid, "name": v["name"], "hersteller": "", "form": v["form"], "portion": v["portion"],
            "inhalt": [{"n": n, "menge": m, "einheit": e} for n, m, e in v["inhalt"]],
            "plan": {"zeit": v["zeit"], "rhythmus": "taeglich", "tage": list(range(7)), "alle": 2,
                     "ab": heute.isoformat(), "portionen": 1},
            "aktiv": True, "notiz": ""}


def inhalt_basis(sup, portionen=1):
    """Inhalt fuer die Portionen in Basiseinheiten -> ({naehrstoff: menge}, [nicht umrechenbare Angaben])."""
    aus, fehler = {}, []
    try:
        faktor = float(portionen)
    except (TypeError, ValueError):
        faktor = 1.0
    for z in (sup or {}).get("inhalt") or []:
        wert = N.in_basis(z.get("n"), z.get("menge"), z.get("einheit"))
        if wert is None:
            fehler.append(z)
            continue
        aus[z["n"]] = aus.get(z["n"], 0.0) + wert * faktor
    return aus, fehler


def geplant_am(sup, tag):
    """Ist das Supplement an diesem Tag laut Plan vorgesehen?"""
    if not sup.get("aktiv", True):
        return False
    p = sup.get("plan") or {}
    r = p.get("rhythmus", "taeglich")
    if r == "wochentage":
        return tag.weekday() in (p.get("tage") or [])
    if r == "intervall":
        try:
            ab = datetime.date.fromisoformat(p.get("ab"))
            alle = max(1, int(p.get("alle") or 1))
        except (TypeError, ValueError):
            return True
        return tag >= ab and (tag - ab).days % alle == 0
    return True


def tagesplan(sups, tag):
    """-> {Tageszeit: [Supplement]} fuer diesen Tag (nur geplante, Reihenfolge der Tageszeiten)."""
    plan = {z: [] for z in ZEITEN}
    for s in sups or []:
        if isinstance(s, dict) and geplant_am(s, tag):
            z = (s.get("plan") or {}).get("zeit")
            plan[z if z in plan else ZEITEN[0]].append(s)
    return {z: l for z, l in plan.items() if l}


def plan_text(sup):
    p = sup.get("plan") or {}
    r = p.get("rhythmus", "taeglich")
    zeit = (p.get("zeit") or "Morgens").lower()
    if r == "wochentage":
        tage = p.get("tage") or []
        return f"{zeit}, " + ("täglich" if len(tage) == 7 else " / ".join(WOCHENTAGE[t] for t in sorted(tage)) or "nie")
    if r == "intervall":
        return f"{zeit}, alle {p.get('alle') or 1} Tage"
    return f"jeden Tag {zeit}"


def inhalt_text(sup, max_n=3):
    teile = [f"{N.NAEHRSTOFFE[z['n']].name.split(' (')[0]} {_zahl(z['menge'])} {z['einheit']}"
             for z in (sup.get("inhalt") or []) if z.get("n") in N.NAEHRSTOFFE]
    return ", ".join(teile[:max_n]) + (" …" if len(teile) > max_n else "")


def _zahl(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return str(x)
    t = f"{x:,.2f}".rstrip("0").rstrip(".") if not x.is_integer() else f"{x:,.0f}"
    return t.replace(",", "X").replace(".", ",").replace("X", ".")
