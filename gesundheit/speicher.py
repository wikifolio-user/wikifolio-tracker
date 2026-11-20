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

from . import naehrstoffe as _N
from . import rechnen as R
from . import supplements as SU

PFAD_PROFIL = "state/gesundheit/profil.json"
PFAD_MONAT = "state/gesundheit/tage/{}.json"
MI_NAME = {n: x.name for n, x in _N.NAEHRSTOFFE.items()}
MI_EINHEIT = {n: x.einheit for n, x in _N.NAEHRSTOFFE.items()}
PFAD_ORDNER = "state/gesundheit"
MAHLZEITEN = ["Frühstück", "Mittagessen", "Nachmittag", "Abendessen", "Snacks"]
GETRAENKE = [("wasser", "Wasser", 0), ("kaffee", "Kaffee", 2), ("tee", "Tee", 1), ("saft", "Saft", 45),
             ("milch", "Milch", 47), ("softdrink", "Softdrink", 42)]      # (art, Name, kcal je 100 ml)
GETRAENK_KCAL = {a: k for a, _, k in GETRAENKE}
GETRAENK_NAME = {a: n for a, n, _ in GETRAENKE}
STANDARD_EINSTELLUNGEN = {"glaeser": [{"name": "Mein Glas", "ml": 300}, {"name": "Meine Flasche", "ml": 750}],
                          "sport_zusaetzlich": False, "erweitert": False, "supplements_zeigen": True,
                          "fasten_zeigen": True, "mahlzeiten": list(MAHLZEITEN), "getraenke": [],
                          "kacheln_aus": []}
MAX_HISTORIE = 200


def monat_pfad(tag):
    return PFAD_MONAT.format(tag.strftime("%Y-%m"))


def leeres_profil():
    return {"profil": {}, "historie": [], "einstellungen": copy.deepcopy(STANDARD_EINSTELLUNGEN), "eigene": [],
            "favoriten": [], "nutzung": {}, "supplements": [], "vorlagen": [], "sport_nutzung": {},
            "fasten": {"plan": "16:8", "laeuft": None, "verlauf": []}, "routinen": []}


def profil_doc(roh):
    """Gelesene profil.json -> vollstaendiges Dokument (fehlende Teile mit Standardwerten). Immer eine TIEFE Kopie:
    Aenderungsfunktionen duerfen das Original (z. B. die Sitzungskopie) nie mitveraendern."""
    d = leeres_profil()
    if isinstance(roh, dict):
        for k in d:
            if isinstance(roh.get(k), type(d[k])):
                d[k] = copy.deepcopy(roh[k])
        d["einstellungen"] = {**copy.deepcopy(STANDARD_EINSTELLUNGEN), **copy.deepcopy(roh.get("einstellungen") or {})}
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
    return {"essen": [], "trinken": [], "supplements": [], "sport": []}


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


def trinken_hinzu(monat_doc, tag, art, ml, zeit, name=None, kcal100=None):
    """Getraenk eintragen. Eigene Getraenke (art "eigen:…") speichern Name und kcal je 100 ml als Kopie mit."""
    try:
        ml = float(ml)
    except (TypeError, ValueError):
        return monat_doc
    if ml <= 0:
        return monat_doc
    e = {"id": neue_id(), "art": art, "ml": ml, "zeit": zeit.strftime("%H:%M")}
    if name:
        e["name"] = str(name)[:40]
    if kcal100 is not None:
        e["kcal100"] = float(kcal100)
    return _tag_aendern(monat_doc, tag, lambda t: t["trinken"].append(e))


def gewicht_setzen(monat_doc, tag, kg):
    def f(t):
        if kg is None:
            t.pop("gewicht", None)
        else:
            t["gewicht"] = round(float(kg), 1)
    return _tag_aendern(monat_doc, tag, f)


# ---------------------------------------------------------------- Sport
def sport_hinzu(monat_doc, tag, eintrag):
    return _tag_aendern(monat_doc, tag, lambda t: t["sport"].append(eintrag))


def sport_merken(doc, art, minuten, intensitaet):
    """Zuletzt genutzte Dauer und Intensitaet je Sportart (Standard beim naechsten Mal)."""
    d = profil_doc(doc)
    u = d["sport_nutzung"].get(art) or {}
    d["sport_nutzung"][art] = {"n": int(u.get("n") or 0) + 1, "minuten": float(minuten), "intensitaet": intensitaet}
    return d


# ---------------------------------------------------------------- Koerpermasse
MASSE = [("koerperfett", "Körperfett", "%"), ("muskel", "Muskelmasse", "kg"), ("bauch", "Bauchumfang", "cm"),
         ("huefte", "Hüftumfang", "cm"), ("brust", "Brustumfang", "cm"), ("oberarm", "Oberarm", "cm"),
         ("oberschenkel", "Oberschenkel", "cm")]


def masse_setzen(monat_doc, tag, werte):
    """Koerpermasse eines Tages setzen; None/0 entfernt einen Wert."""
    def f(t):
        m = dict(t.get("masse") or {})
        for k, v in (werte or {}).items():
            if v:
                m[k] = round(float(v), 1)
            else:
                m.pop(k, None)
        t["masse"] = m
    return _tag_aendern(monat_doc, tag, f)


def mass_verlauf(monate, schluessel):
    """-> sortierte [(datum, wert)] eines Koerpermasses (wie gewichte())."""
    aus = []
    for m in monate:
        for tag, t in ((m or {}).get("tage") or {}).items():
            v = ((t or {}).get("masse") or {}).get(schluessel) if isinstance(t, dict) else None
            if v:
                try:
                    aus.append((datetime.date.fromisoformat(tag), float(v)))
                except ValueError:
                    continue
    return sorted(aus)


# ---------------------------------------------------------------- Getraenke
def getraenk_kcal100(x):
    """kcal je 100 ml eines Getraenk-Eintrags: gespeicherte Kopie (eigene Getraenke) oder Standardwert der Art."""
    if x.get("kcal100") is not None:
        try:
            return float(x["kcal100"])
        except (TypeError, ValueError):
            return 0.0
    return GETRAENK_KCAL.get(x.get("art"), 0)


def getraenk_name(x, eigene=()):
    if x.get("name"):
        return x["name"]
    e = next((g for g in eigene or () if g.get("art") == x.get("art")), None)
    return (e or {}).get("name") or GETRAENK_NAME.get(x.get("art"), "Getränk")


def getraenk_speichern(doc, name, kcal100, art=None):
    """Eigenes Getraenk anlegen oder aendern (gleiche art ersetzt). -> (doc, art)"""
    d = profil_doc(doc)
    art = art or "eigen:" + neue_id()
    liste = [g for g in d["einstellungen"].get("getraenke") or [] if g.get("art") != art]
    liste.append({"art": art, "name": str(name).strip()[:30] or "Getränk", "kcal100": max(0.0, float(kcal100 or 0))})
    d["einstellungen"] = {**d["einstellungen"], "getraenke": liste}
    return d, art


def getraenk_entfernen(doc, art):
    d = profil_doc(doc)
    d["einstellungen"] = {**d["einstellungen"], "getraenke": [g for g in d["einstellungen"].get("getraenke") or []
                                                              if g.get("art") != art]}
    return d


def haeufigste_menge(monate, art=None, mindestens=2):
    """Haeufigste Trinkmenge (ml) aus den Eintraegen (optional nur einer Getraenkeart) oder None, wenn keine Menge
    mindestens zweimal vorkommt."""
    zaehler = {}
    for m in monate:
        for t in ((m or {}).get("tage") or {}).values():
            for x in (t or {}).get("trinken") or []:
                if art and x.get("art") != art:
                    continue
                ml = float(x.get("ml") or 0)
                if ml > 0:
                    zaehler[ml] = zaehler.get(ml, 0) + 1
    if not zaehler:
        return None
    ml, n = max(zaehler.items(), key=lambda kv: (kv[1], kv[0]))
    return ml if n >= mindestens else None


# ---------------------------------------------------------------- Eigene Lebensmittel
def lebensmittel_speichern(doc, lm):
    """Eigenes Lebensmittel anlegen oder (gleiche id) aendern. Fruehere Tage behalten ihre Kopie der Naehrwerte."""
    d = profil_doc(doc)
    d["eigene"] = [x for x in d["eigene"] if x.get("id") != lm["id"]] + [copy.deepcopy(lm)]
    return d


def lebensmittel_entfernen(doc, lm_id):
    """Eigenes Lebensmittel loeschen (auch aus Favoriten und Nutzung). Fruehere Eintraege bleiben unveraendert."""
    d = profil_doc(doc)
    d["eigene"] = [x for x in d["eigene"] if x.get("id") != lm_id]
    d["favoriten"] = [f for f in d["favoriten"] if f != lm_id]
    d["nutzung"].pop(lm_id, None)
    return d


def tag_kopieren(monat_doc_quelle, quelle, monat_doc_ziel, ziel, zeit):
    """Alle Essens-Eintraege eines Tages auf einen anderen Tag uebernehmen (neue IDs). -> (neues Zieldokument, Anzahl)"""
    eintraege = tag_aus(monat_doc_quelle, quelle)["essen"]
    if not eintraege:
        return monat_doc_ziel, 0
    return essen_hinzu(monat_doc_ziel, ziel, kopieren(eintraege, zeit)), len(eintraege)


# ---------------------------------------------------------------- Mahlzeiten-Vorlagen
def vorlage_speichern(doc, name, eintraege, vid):
    """Eintraege als Vorlage merken (ohne IDs/Uhrzeit; gleicher Name ersetzt die alte Vorlage)."""
    d = profil_doc(doc)
    teile = [{k: v for k, v in e.items() if k not in ("id", "zeit")} for e in eintraege]
    d["vorlagen"] = [v for v in d["vorlagen"] if v.get("name") != name] + [{"id": vid, "name": name, "eintraege": teile}]
    return d


def vorlage_umbenennen(doc, vid, name):
    d = profil_doc(doc)
    name = str(name or "").strip()[:40]
    if name:
        for v in d["vorlagen"]:
            if v.get("id") == vid:
                v["name"] = name
    return d


def vorlage_entfernen(doc, vid):
    d = profil_doc(doc)
    d["vorlagen"] = [v for v in d["vorlagen"] if v.get("id") != vid]
    return d


# ---------------------------------------------------------------- Supplements
def einnahme_setzen(monat_doc, tag, sup, status, zeit, portionen=None):
    """Einnahme eines Supplements fuer den Tag setzen (je Supplement und Tag ein Eintrag; erneutes Setzen ersetzt).
    status: "eingenommen" oder "ausgelassen". Der Inhalt wird umgerechnet als Kopie gespeichert."""
    portionen = portionen or (sup.get("plan") or {}).get("portionen") or 1
    inhalt, _ = SU.inhalt_basis(sup, portionen)

    def f(t):
        t["supplements"] = [x for x in t.get("supplements") or [] if x.get("sup") != sup["id"]]
        t["supplements"].append({"id": neue_id(), "sup": sup["id"], "name": sup.get("name") or "Supplement",
                                 "portionen": portionen, "status": status, "zeit": zeit.strftime("%H:%M"),
                                 "inhalt": inhalt})
    return _tag_aendern(monat_doc, tag, f)


def einnahme_loeschen(monat_doc, tag, sup_id):
    """Einnahme zuruecksetzen (wieder "geplant")."""
    def f(t):
        t["supplements"] = [x for x in t.get("supplements") or [] if x.get("sup") != sup_id]
    return _tag_aendern(monat_doc, tag, f)


def routine_speichern(doc, name, sup_ids, rid=None):
    """Benannte Supplement-Routine (z. B. "Training") anlegen oder aendern. -> (doc, rid)"""
    d = profil_doc(doc)
    rid = rid or "rt:" + neue_id()
    d["routinen"] = [r for r in d["routinen"] if r.get("id") != rid] + [
        {"id": rid, "name": str(name).strip()[:30] or "Routine", "sups": list(dict.fromkeys(sup_ids or []))}]
    return d, rid


def routine_entfernen(doc, rid):
    d = profil_doc(doc)
    d["routinen"] = [r for r in d["routinen"] if r.get("id") != rid]
    return d


def routine_einnehmen(monat_doc, tag, routine, supplements, zeit):
    """Alle (aktiven) Supplements einer Routine fuer den Tag als eingenommen markieren. -> (doc, anzahl)"""
    nach_id = {s.get("id"): s for s in supplements or () if s.get("aktiv", True)}
    n = 0
    for sid in routine.get("sups") or []:
        if sid in nach_id:
            monat_doc = einnahme_setzen(monat_doc, tag, nach_id[sid], "eingenommen", zeit)
            n += 1
    return monat_doc, n


def supplement_speichern(doc, sup):
    """Supplement anlegen oder (gleiche id) ersetzen."""
    d = profil_doc(doc)
    d["supplements"] = [x for x in d["supplements"] if x.get("id") != sup["id"]] + [copy.deepcopy(sup)]
    return d


def supplement_entfernen(doc, sup_id):
    """Nicht loeschen, sondern deaktivieren: alte Tage bleiben nachvollziehbar, der Plan zeigt es nicht mehr."""
    d = profil_doc(doc)
    for x in d["supplements"]:
        if x.get("id") == sup_id:
            x["aktiv"] = False
    return d


# ---------------------------------------------------------------- Auswertung eines Tages
def tag_summen(t):
    """-> {"naehrwerte": summe(...), "kcal", "fluessigkeit_ml", "trinken_kcal", "mahlzeiten": {name: kcal}}.
    Fluessigkeit = Getraenke + Lebensmittel mit ml-Basis (Milch, Saft …)."""
    essen = t.get("essen") or []
    nw = [eintrag_naehrwerte(e) for e in essen]
    trinken = t.get("trinken") or []
    trinken_kcal = sum(float(x.get("ml") or 0) * getraenk_kcal100(x) / 100 for x in trinken)
    s = R.summe(nw)
    fl = sum(float(x.get("ml") or 0) for x in trinken) + sum(
        float(e.get("gramm") or 0) for e in essen if e.get("basis") == "ml")
    mahl = {}
    for e, w in zip(essen, nw):
        mahl[e.get("mahlzeit") or "Snacks"] = mahl.get(e.get("mahlzeit") or "Snacks", 0) + (w.get("kcal") or 0)
    return {"naehrwerte": s, "kcal": s["kcal"]["wert"] + trinken_kcal, "fluessigkeit_ml": fl,
            "trinken_kcal": trinken_kcal, "mahlzeiten": mahl}


def nutzung_merken(doc, lm_id, menge, einheit, zeit, mahlzeit=None):
    """Haeufigkeit, letzte Nutzung, letzte Menge und Haeufigkeit je Mahlzeit eines Lebensmittels (fuer Vorschlaege
    nach Tageszeit und Standardmengen)."""
    d = profil_doc(doc)
    u = d["nutzung"].get(lm_id) or {}
    je = dict(u.get("mahlzeiten") or {})
    if mahlzeit:
        je[mahlzeit] = int(je.get(mahlzeit) or 0) + 1
    d["nutzung"][lm_id] = {"n": int(u.get("n") or 0) + 1, "zuletzt": zeit.isoformat(timespec="seconds"),
                           "menge": float(menge), "einheit": einheit, "mahlzeiten": je}
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
