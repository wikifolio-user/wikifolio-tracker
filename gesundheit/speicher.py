"""Datenmodell der gespeicherten Gesundheitsdaten - reine Funktionen auf dicts (ohne Streamlit, ohne Netz).

Dateien (State-Repo, nur Admin):
  state/gesundheit/profil.json        {"profil": {...}, "historie": [{"t": iso, "profil": {...}}],
                                       "einstellungen": {...}, "eigene": [Lebensmittel], "favoriten": [id],
                                       "nutzung": {id: {"n", "zuletzt", "menge", "einheit"}}}
  state/gesundheit/tage/JJJJ-MM.json  {"tage": {"JJJJ-MM-TT": {"essen": [...], "trinken": [...], "gewicht": kg}}}

Ein Monat je Datei: wenige Dateien, jeder Tag bleibt dauerhaft erhalten. Essens-Eintraege speichern die Naehrwerte
je 100 g/ml MIT (pro100) - spaetere Aenderungen an einem Lebensmittel veraendern alte Tage nicht.
"""
import copy
import datetime
import uuid

from . import rechnen as R

PFAD_PROFIL = "state/gesundheit/profil.json"
PFAD_MONAT = "state/gesundheit/tage/{}.json"
MAHLZEITEN = ["Frühstück", "Mittagessen", "Nachmittag", "Abendessen", "Snacks"]
GETRAENKE = [("wasser", "Wasser", 0), ("kaffee", "Kaffee", 2), ("tee", "Tee", 1), ("saft", "Saft", 45),
             ("milch", "Milch", 47), ("softdrink", "Softdrink", 42)]      # (art, Name, kcal je 100 ml)
GETRAENK_KCAL = {a: k for a, _, k in GETRAENKE}
GETRAENK_NAME = {a: n for a, n, _ in GETRAENKE}
STANDARD_EINSTELLUNGEN = {"glaeser": [{"name": "Mein Glas", "ml": 300}, {"name": "Meine Flasche", "ml": 750}],
                          "sport_zusaetzlich": False}
MAX_HISTORIE = 200


def monat_pfad(tag):
    return PFAD_MONAT.format(tag.strftime("%Y-%m"))


def leeres_profil():
    return {"profil": {}, "historie": [], "einstellungen": copy.deepcopy(STANDARD_EINSTELLUNGEN), "eigene": [],
            "favoriten": [], "nutzung": {}}


def profil_doc(roh):
    """Gelesene profil.json -> vollstaendiges Dokument (fehlende Teile mit Standardwerten)."""
    d = leeres_profil()
    if isinstance(roh, dict):
        for k in d:
            if isinstance(roh.get(k), type(d[k])):
                d[k] = roh[k]
        d["einstellungen"] = {**copy.deepcopy(STANDARD_EINSTELLUNGEN), **(roh.get("einstellungen") or {})}
    return d


def eingerichtet(doc):
    p = (doc or {}).get("profil") or {}
    return bool(p.get("gewicht_kg") and p.get("groesse_cm") and p.get("geburtsjahr") and p.get("ziel"))


def profil_setzen(doc, neu, zeit):
    """Profil aendern und den alten Stand in die Historie schreiben (nur bei echter Aenderung)."""
    d = profil_doc(doc)
    alt = d["profil"]
    zusammen = {**alt, **{k: v for k, v in neu.items()}}
    zusammen = {k: v for k, v in zusammen.items() if v is not None}
    if zusammen == alt:
        return d
    d["historie"].append({"t": zeit.isoformat(timespec="seconds"), "profil": zusammen})
    del d["historie"][:-MAX_HISTORIE]
    d["profil"] = zusammen
    return d


# ---------------------------------------------------------------- Tage
def tag_leer():
    return {"essen": [], "trinken": []}


def tag_aus(monat_doc, tag):
    t = ((monat_doc or {}).get("tage") or {}).get(tag.isoformat())
    out = tag_leer()
    if isinstance(t, dict):
        out.update({k: v for k, v in t.items()})
    return out


def _tag_aendern(monat_doc, tag, f):
    d = copy.deepcopy(monat_doc) if isinstance(monat_doc, dict) else {}
    d.setdefault("tage", {})
    t = tag_aus(d, tag)
    f(t)
    d["tage"][tag.isoformat()] = t
    return d


def neue_id():
    return uuid.uuid4().hex[:12]


def essen_eintrag(lm, menge, einheit, mahlzeit, zeit):
    """Lebensmittel + Menge -> Eintrag (mit Naehrwerten je 100 g/ml als Kopie). None bei ungueltiger Menge."""
    g = R.gramm(menge, einheit, lm.get("einheiten"))
    if g is None or g <= 0:
        return None
    return {"id": neue_id(), "lm": lm["id"], "name": lm["name"], "menge": float(menge), "einheit": einheit,
            "gramm": round(g, 1), "basis": lm.get("basis") or "g", "einheiten": dict(lm.get("einheiten") or {}),
            "pro100": dict(lm.get("pro100") or {}), "mahlzeit": mahlzeit, "zeit": zeit.strftime("%H:%M")}


def eintrag_naehrwerte(e):
    return R.naehrwerte(e.get("pro100"), e.get("gramm"))


def essen_hinzu(monat_doc, tag, eintraege):
    return _tag_aendern(monat_doc, tag, lambda t: t["essen"].extend(eintraege))


def essen_menge(monat_doc, tag, eid, menge, einheit=None, mahlzeit=None):
    """Menge (und optional Einheit/Mahlzeit) eines Eintrags aendern. Ungueltige Menge: unveraendert."""
    def f(t):
        for e in t["essen"]:
            if e.get("id") == eid:
                ein = einheit or e.get("einheit")
                g = R.gramm(menge, ein, e.get("einheiten"))
                if g is not None and g > 0:
                    e.update(menge=float(menge), einheit=ein, gramm=round(g, 1))
                if mahlzeit:
                    e["mahlzeit"] = mahlzeit
    return _tag_aendern(monat_doc, tag, f)


def entfernen(monat_doc, tag, liste, eid):
    """Eintrag aus "essen" oder "trinken" entfernen. -> (neues Dokument, entfernter Eintrag oder None)"""
    box = {}

    def f(t):
        for i, e in enumerate(t[liste]):
            if e.get("id") == eid:
                box["e"] = t[liste].pop(i)
                return
    return _tag_aendern(monat_doc, tag, f), box.get("e")


def wiederherstellen(monat_doc, tag, liste, eintrag):
    return _tag_aendern(monat_doc, tag, lambda t: t[liste].append(eintrag) if all(
        e.get("id") != eintrag.get("id") for e in t[liste]) else None)


def kopieren(eintraege, zeit):
    """Eintraege (z. B. von gestern) als neue Eintraege - neue IDs, aktuelle Uhrzeit."""
    aus = []
    for e in eintraege:
        k = copy.deepcopy(e)
        k["id"], k["zeit"] = neue_id(), zeit.strftime("%H:%M")
        aus.append(k)
    return aus


def trinken_hinzu(monat_doc, tag, art, ml, zeit):
    try:
        ml = float(ml)
    except (TypeError, ValueError):
        return monat_doc
    if ml <= 0:
        return monat_doc
    e = {"id": neue_id(), "art": art, "ml": ml, "zeit": zeit.strftime("%H:%M")}
    return _tag_aendern(monat_doc, tag, lambda t: t["trinken"].append(e))


def gewicht_setzen(monat_doc, tag, kg):
    def f(t):
        if kg is None:
            t.pop("gewicht", None)
        else:
            t["gewicht"] = round(float(kg), 1)
    return _tag_aendern(monat_doc, tag, f)


# ---------------------------------------------------------------- Auswertung eines Tages
def tag_summen(t):
    """-> {"naehrwerte": summe(...), "kcal", "fluessigkeit_ml", "trinken_kcal", "mahlzeiten": {name: kcal}}.
    Fluessigkeit = Getraenke + Lebensmittel mit ml-Basis (Milch, Saft …)."""
    essen = t.get("essen") or []
    nw = [eintrag_naehrwerte(e) for e in essen]
    trinken = t.get("trinken") or []
    trinken_kcal = sum(float(x.get("ml") or 0) * GETRAENK_KCAL.get(x.get("art"), 0) / 100 for x in trinken)
    s = R.summe(nw)
    fl = sum(float(x.get("ml") or 0) for x in trinken) + sum(
        float(e.get("gramm") or 0) for e in essen if e.get("basis") == "ml")
    mahl = {}
    for e, w in zip(essen, nw):
        mahl[e.get("mahlzeit") or "Snacks"] = mahl.get(e.get("mahlzeit") or "Snacks", 0) + (w.get("kcal") or 0)
    return {"naehrwerte": s, "kcal": s["kcal"]["wert"] + trinken_kcal, "fluessigkeit_ml": fl,
            "trinken_kcal": trinken_kcal, "mahlzeiten": mahl}


def nutzung_merken(doc, lm_id, menge, einheit, zeit):
    """Haeufigkeit, letzte Nutzung und letzte Menge eines Lebensmittels (fuer Vorschlaege und Standardmengen)."""
    d = profil_doc(doc)
    u = d["nutzung"].get(lm_id) or {}
    d["nutzung"][lm_id] = {"n": int(u.get("n") or 0) + 1, "zuletzt": zeit.isoformat(timespec="seconds"),
                           "menge": float(menge), "einheit": einheit}
    return d


def favorit_umschalten(doc, lm_id):
    d = profil_doc(doc)
    d["favoriten"] = [f for f in d["favoriten"] if f != lm_id] if lm_id in d["favoriten"] else d["favoriten"] + [lm_id]
    return d


def gewichte(monate):
    """Alle Gewichtseintraege aus Monatsdokumenten -> sortierte Liste [(datum, kg)]."""
    aus = []
    for m in monate:
        for tag, t in ((m or {}).get("tage") or {}).items():
            if isinstance(t, dict) and t.get("gewicht"):
                try:
                    aus.append((datetime.date.fromisoformat(tag), float(t["gewicht"])))
                except ValueError:
                    continue
    return sorted(aus)
