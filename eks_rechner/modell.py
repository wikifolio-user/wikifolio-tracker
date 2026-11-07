"""Datenmodell der EKS-Investmentbewertung: Defaults, Bereinigung (alte/kaputte Staende), Export/Import.

Gespeichert wird je Benutzer in state/eks_ideen.json (State-Branch, wie das Analyse-Depot):
{ "version": 2,
  "einstellungen": {kriterien: [{id, name, gewicht, invers}], kriterien_version, schwelle_nutzwert,
                    schwelle_eks, min_engpass, mindest_stundensatz, netto_monat_job, stunden_woche_job,
                    mindest_aus_job, diskont_pa, szenarien: {pess|real|opt: {umsatz, kosten, gewicht}}},
  "ideen": [{id, name, beschreibung, status, erstellt, geaendert, status_seit, start_monat,
             phasen: {"1".."7": {text, score}}, kriterien: {id: score}, finanzen: {...},
             szenarien: {pess|real|opt: {umsatz, kosten, gewicht}},
             ist: [{monat "JJJJ-MM", umsatz, kosten, stunden}], abbruch: [{art, wert, nach_monaten}]}],
  "letzter_lauf": {stand, ampeln: {idee_id: ampel}, text: [...]}   # vom Monatslauf (eks_agent.py)
}
"""
import csv
import datetime
import io
import json
import re
import uuid

VERSION = 2
PHASEN = [("1", "Stärken", "Worin bin ich besonders gut? Welche Fähigkeiten, Ressourcen, Kontakte habe ich?"),
          ("2", "Geschäftsfeld", "Welches Feld passt am besten zu diesen Stärken?"),
          ("3", "Zielgruppe", "Für welche eng umrissene Zielgruppe bin ich am attraktivsten?"),
          ("4", "Brennendstes Problem", "Was ist das dringendste, noch ungelöste Problem dieser Zielgruppe?"),
          ("5", "Innovation / Lösung", "Welche Lösung biete ich, die besser ist als alles Bisherige?"),
          ("6", "Kooperation", "Mit wem arbeite ich zusammen, um mich auf meine Stärken zu konzentrieren?"),
          ("7", "Konstantes Grundbedürfnis", "Welches dauerhafte Bedürfnis steckt dahinter – trägt es langfristig?")]
ENGPASS_PHASE = "4"             # Kern der EKS: das brennendste Problem der Zielgruppe
# Leitfragen je Phase (nach Mewes) - Hilfe beim Ausfuellen
LEITFRAGEN = {
    "1": ["Was kann ich besser als die meisten anderen (Fachwissen, Erfahrung, Kontakte, Ausstattung)?",
          "Wofür fragen mich andere schon heute um Rat?", "Welche Stärke ist schwer nachzuahmen?"],
    "2": ["In welchem Feld zahlen sich genau diese Stärken am meisten aus?",
          "Gibt es dort zahlende Kunden – nicht nur Interessierte?", "Kann ich mich dort klar spezialisieren?"],
    "3": ["Wer genau ist der Kunde (Branche, Größe, Rolle, Region)?",
          "Ist die Gruppe klein genug, um dort die Nummer 1 zu werden, und groß genug, um davon zu leben?",
          "Wie erreiche ich sie direkt (Verbände, Netzwerke, Kanäle)?"],
    "4": ["Welches Problem kostet die Zielgruppe heute am meisten Geld, Zeit oder Nerven?",
          "Haben mir mindestens fünf Personen dieses Problem selbst genannt – ohne Suggestivfrage?",
          "Was haben sie schon versucht, und warum reicht das nicht?", "Würden sie dafür sofort bezahlen?"],
    "5": ["Löst mein Angebot genau dieses Problem besser, schneller oder günstiger als die Alternativen?",
          "Was ist das eine Merkmal, an dem man mich erkennt?", "Lässt sich die Lösung klein testen (Prototyp, Pilot)?"],
    "6": ["Welche Aufgaben außerhalb meiner Stärken gebe ich ab?",
          "Wer hat dieselbe Zielgruppe, aber kein Konkurrenzangebot (Partner, Vertriebswege)?",
          "Wer liefert mir Kunden, wer liefert mir Leistung zu?"],
    "7": ["Welches dauerhafte Bedürfnis steckt hinter dem Problem (Sicherheit, Zeit, Anerkennung …)?",
          "Bleibt es bestehen, wenn sich Technik oder Mode ändern?", "Wie kann ich mit der Zielgruppe mitwachsen?"],
}
# Bewertungsraster: was ein Score bedeutet (gilt fuer alle Phasen)
RASTER = [("1–3", "schwach: Annahme ohne Belege, eher Wunsch als Tatsache"),
          ("4–6", "mittel: teilweise belegt, einzelne Rückmeldungen, deutliche Lücken"),
          ("7–8", "stark: durch Gespräche, Zahlen oder erste Verkäufe gut belegt"),
          ("9–10", "herausragend: klar belegt und schwer nachzuahmen – hier bin ich (fast) die Nummer 1")]
STATUS = {"idee": "Idee", "test": "Test läuft", "aktiv": "aktiv", "verworfen": "verworfen"}
SZENARIEN = {"pess": "pessimistisch", "real": "realistisch", "opt": "optimistisch"}
STANDARD_SZENARIEN = {"pess": {"umsatz": 0.7, "kosten": 1.15, "gewicht": 25.0},
                      "real": {"umsatz": 1.0, "kosten": 1.0, "gewicht": 50.0},
                      "opt": {"umsatz": 1.3, "kosten": 0.95, "gewicht": 25.0}}
# Version 2: ohne Doppelzaehlung mit den EKS-Phasen (Staerken = Phase 1, Problem = Phase 4 stecken im EKS-Score)
KRITERIEN_VERSION = 2
STANDARD_KRITERIEN = [
    {"id": "markt", "name": "Marktgröße (zahlende Zielkunden)", "gewicht": 20.0, "invers": False},
    {"id": "wettbewerb", "name": "Wettbewerb", "gewicht": 20.0, "invers": True},
    {"id": "zeit", "name": "Zeitbedarf", "gewicht": 15.0, "invers": True},
    {"id": "skalierung", "name": "Skalierbarkeit", "gewicht": 20.0, "invers": False},
    {"id": "risiko", "name": "Risiko", "gewicht": 15.0, "invers": True},
    {"id": "motivation", "name": "Freude / Motivation", "gewicht": 10.0, "invers": False},
]
# Standard bis Version 1 - wer ihn nie geaendert hat, bekommt automatisch die neuen Kriterien
ALTE_STANDARD_KRITERIEN = [("staerken", 25.0, False), ("problem", 20.0, False), ("wettbewerb", 15.0, True),
                           ("zeit", 15.0, True), ("skalierung", 15.0, False), ("risiko", 10.0, True)]
STANDARD_FINANZEN = {"start_invest": 0.0, "umsatz_monat": 0.0, "var_kosten_pct": 0.0, "fix_monat": 0.0,
                     "stunden_woche": 5.0, "stunden_anlauf_woche": 5.0, "anlauf_monate": 6, "horizont_jahre": 3,
                     "steuersatz_pct": 30.0, "afa_jahre": 3, "hebesatz_pct": 400.0}
STANDARD_EINSTELLUNGEN = {"schwelle_nutzwert": 60.0, "schwelle_eks": 60.0, "min_engpass": 6.0,
                          "mindest_stundensatz": 25.0, "netto_monat_job": 0.0, "stunden_woche_job": 0.0,
                          "mindest_aus_job": False, "diskont_pa": 7.0}
GRENZEN = {"start_invest": (0, 1e9), "umsatz_monat": (0, 1e8), "var_kosten_pct": (0, 100), "fix_monat": (0, 1e8),
           "stunden_woche": (0, 168), "stunden_anlauf_woche": (0, 168), "anlauf_monate": (0, 120),
           "horizont_jahre": (1, 30), "steuersatz_pct": (0, 100), "afa_jahre": (0, 50), "hebesatz_pct": (0, 1000)}
GANZZAHL = {"anlauf_monate", "horizont_jahre", "afa_jahre"}
# Abbruch-Kriterien: art -> (Text mit {wert} und {n}, Einheit)
ABBRUCH_ARTEN = {
    "umsatz_min": ("Umsatz im Monat mindestens {wert} € ab Monat {n}", "€"),
    "gewinn_kum_min": ("Kumulierter Gewinn (vor Steuern) nach {n} Monaten mindestens {wert} €", "€"),
    "eur_h_min": ("Gewinn je Stunde nach {n} Monaten mindestens {wert} €", "€/h"),
    "stunden_max": ("Höchstens {wert} Stunden je Woche (Ø der ersten {n} Monate)", "h"),
}
MONAT_RE = re.compile(r"^(\d{4})-(\d{2})$")
SCORE_MIN, SCORE_MAX, SCORE_START = 1, 10, 5
GEWICHT_TOLERANZ = 0.5          # Prozentpunkte


def jetzt_iso(jetzt=None):
    return (jetzt or datetime.datetime.now()).isoformat(timespec="minutes")


def _zahl(x, standard=None):
    try:
        v = float(str(x).replace(",", ".")) if isinstance(x, str) else float(x)
    except (TypeError, ValueError):
        return standard
    return v if v == v and v not in (float("inf"), float("-inf")) else standard


def _score(x):
    v = _zahl(x)
    return SCORE_START if v is None else int(round(min(max(v, SCORE_MIN), SCORE_MAX)))


def _text(x, n=4000):
    return str(x or "").strip()[:n]


def neue_id():
    return uuid.uuid4().hex[:10]


def kriterium_id(name, vorhanden=()):
    basis = re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")[:24] or "kriterium"
    kid, i = basis, 2
    while kid in vorhanden:
        kid, i = f"{basis}_{i}", i + 1
    return kid


def standard_einstellungen():
    return {**STANDARD_EINSTELLUNGEN, "kriterien": [dict(k) for k in STANDARD_KRITERIEN],
            "kriterien_version": KRITERIEN_VERSION,
            "szenarien": {k: dict(v) for k, v in STANDARD_SZENARIEN.items()}}


def _szenarien(roh, standard):
    roh = roh if isinstance(roh, dict) else {}
    aus = {}
    for k in SZENARIEN:
        s = roh.get(k) if isinstance(roh.get(k), dict) else {}
        aus[k] = {f: min(max(_zahl(s.get(f), standard[k][f]), 0.0), 10.0) for f in ("umsatz", "kosten")}
        aus[k]["gewicht"] = min(max(_zahl(s.get("gewicht"), standard[k].get("gewicht", 0.0)), 0.0), 100.0)
    return aus


def neue_idee(name="Neue Idee", einstellungen=None, jetzt=None):
    e = einstellungen or standard_einstellungen()
    t = jetzt_iso(jetzt)
    return {"id": neue_id(), "name": _text(name, 120) or "Neue Idee", "beschreibung": "", "status": "idee",
            "erstellt": t, "geaendert": t, "status_seit": t, "start_monat": t[:7], "ist": [], "abbruch": [],
            "phasen": {nr: {"text": "", "score": SCORE_START} for nr, _, _ in PHASEN},
            "kriterien": {k["id"]: SCORE_START for k in e["kriterien"]},
            "finanzen": dict(STANDARD_FINANZEN), "szenarien": _szenarien(e.get("szenarien"), STANDARD_SZENARIEN)}


def _einstellungen(roh):
    roh = roh if isinstance(roh, dict) else {}
    e = standard_einstellungen()
    for k, (lo, hi) in {"schwelle_nutzwert": (0, 100), "schwelle_eks": (0, 100), "min_engpass": (0, 10),
                        "mindest_stundensatz": (0, 1e5), "netto_monat_job": (0, 1e7),
                        "stunden_woche_job": (0, 168), "diskont_pa": (-50, 100)}.items():
        v = _zahl(roh.get(k))
        if v is not None:
            e[k] = min(max(v, lo), hi)
    e["mindest_aus_job"] = bool(roh.get("mindest_aus_job"))
    if isinstance(roh.get("kriterien"), list):
        kr, ids = [], set()
        for k in roh["kriterien"]:
            if not isinstance(k, dict) or not _text(k.get("name"), 80):
                continue
            kid = str(k.get("id") or "") or kriterium_id(k.get("name"), ids)
            if kid in ids:
                kid = kriterium_id(kid, ids)
            ids.add(kid)
            kr.append({"id": kid, "name": _text(k.get("name"), 80),
                       "gewicht": min(max(_zahl(k.get("gewicht"), 0.0), 0.0), 100.0), "invers": bool(k.get("invers"))})
        if kr and not (roh.get("kriterien_version") is None and _alter_standard(kr)):
            e["kriterien"] = kr                # sonst: nie geaenderter alter Standard -> neue Kriterien
    e["szenarien"] = _szenarien(roh.get("szenarien"), STANDARD_SZENARIEN)
    return e


def _alter_standard(kr):
    return [(k["id"], k["gewicht"], k["invers"]) for k in kr] == ALTE_STANDARD_KRITERIEN


def monat_ok(m):
    mt = MONAT_RE.match(str(m or "").strip())
    return bool(mt) and 1 <= int(mt.group(2)) <= 12


def _ist(roh):
    """[{monat, umsatz, kosten, stunden}] - gueltige Monate, Werte >= 0, je Monat der letzte Eintrag, sortiert."""
    je = {}
    for z in roh if isinstance(roh, list) else []:
        if not isinstance(z, dict) or not monat_ok(z.get("monat")):
            continue
        je[str(z["monat"]).strip()] = {"monat": str(z["monat"]).strip(),
                                       **{f: max(_zahl(z.get(f), 0.0), 0.0) for f in ("umsatz", "kosten", "stunden")}}
    return [je[m] for m in sorted(je)]


def _abbruch(roh):
    aus = []
    for z in roh if isinstance(roh, list) else []:
        if not isinstance(z, dict) or z.get("art") not in ABBRUCH_ARTEN or _zahl(z.get("wert")) is None:
            continue
        aus.append({"art": z["art"], "wert": max(_zahl(z["wert"]), 0.0),
                    "nach_monaten": int(min(max(_zahl(z.get("nach_monaten"), 3.0), 1), 120))})
    return aus[:10]


def _finanzen(roh):
    roh = roh if isinstance(roh, dict) else {}
    if "stunden_anlauf_woche" not in roh and "stunden_woche" in roh:   # alter Stand: Anlauf wie Normalbetrieb
        roh = dict(roh, stunden_anlauf_woche=roh["stunden_woche"])
    f = {}
    for k, std in STANDARD_FINANZEN.items():
        lo, hi = GRENZEN[k]
        v = min(max(_zahl(roh.get(k), std), lo), hi)
        f[k] = int(round(v)) if k in GANZZAHL else float(v)
    return f


def idee_bereinigen(roh, einstellungen):
    if not isinstance(roh, dict):
        return None
    i = neue_idee(roh.get("name") or "Neue Idee", einstellungen)
    i["id"] = str(roh.get("id") or i["id"])[:40]
    i["beschreibung"] = _text(roh.get("beschreibung"))
    i["status"] = roh.get("status") if roh.get("status") in STATUS else "idee"
    for f in ("erstellt", "geaendert", "status_seit"):
        if roh.get(f):
            i[f] = str(roh[f])[:25]
    i["start_monat"] = str(roh["start_monat"]).strip() if monat_ok(roh.get("start_monat")) else i["erstellt"][:7]
    i["ist"] = _ist(roh.get("ist"))
    i["abbruch"] = _abbruch(roh.get("abbruch"))
    ph = roh.get("phasen") if isinstance(roh.get("phasen"), dict) else {}
    for nr, _, _ in PHASEN:
        p = ph.get(nr) if isinstance(ph.get(nr), dict) else {}
        i["phasen"][nr] = {"text": _text(p.get("text")), "score": _score(p.get("score"))}
    kr = roh.get("kriterien") if isinstance(roh.get("kriterien"), dict) else {}
    i["kriterien"] = {k["id"]: _score(kr.get(k["id"])) for k in einstellungen["kriterien"]}
    for kid, v in kr.items():                  # Werte entfernter Kriterien behalten (falls sie zurueckkommen)
        i["kriterien"].setdefault(str(kid), _score(v))
    i["finanzen"] = _finanzen(roh.get("finanzen"))
    i["szenarien"] = _szenarien(roh.get("szenarien"), einstellungen["szenarien"])
    return i


def bereinigen(roh):
    """Beliebiger (auch alter oder kaputter) Stand -> gueltiges Datenmodell."""
    roh = roh if isinstance(roh, dict) else {}
    e = _einstellungen(roh.get("einstellungen"))
    e["kriterien_version"] = KRITERIEN_VERSION
    ideen, ids = [], set()
    for r in roh.get("ideen") or []:
        i = idee_bereinigen(r, e)
        if i is None:
            continue
        if i["id"] in ids:
            i["id"] = neue_id()
        ids.add(i["id"])
        ideen.append(i)
    lauf = roh.get("letzter_lauf") if isinstance(roh.get("letzter_lauf"), dict) else {}
    return {"version": VERSION, "einstellungen": e, "ideen": ideen, "letzter_lauf": lauf}


def leer():
    return bereinigen({})


def gewichte_summe(kriterien):
    return sum(_zahl(k.get("gewicht"), 0.0) for k in kriterien)


def gewichte_ok(kriterien):
    return abs(gewichte_summe(kriterien) - 100.0) <= GEWICHT_TOLERANZ


def status_setzen(idee, status, jetzt=None):
    if status in STATUS and status != idee.get("status"):
        idee["status"] = status
        idee["status_seit"] = jetzt_iso(jetzt)
    return idee


# ---------------------------------------------------------------- Export / Import
def export_json(daten):
    return json.dumps(bereinigen(daten), ensure_ascii=False, indent=2)


def _zusammenfuehren(daten, neue, einstellungen=None):
    """Ideen per id ersetzen bzw. anhaengen. -> (daten, neu, ersetzt)"""
    daten = bereinigen(daten)
    if einstellungen is not None:
        daten["einstellungen"] = _einstellungen(einstellungen)
    je = {i["id"]: n for n, i in enumerate(daten["ideen"])}
    neu = ersetzt = 0
    for r in neue:
        i = idee_bereinigen(r, daten["einstellungen"])
        if i is None:
            continue
        if i["id"] in je:
            daten["ideen"][je[i["id"]]] = i
            ersetzt += 1
        else:
            je[i["id"]] = len(daten["ideen"])
            daten["ideen"].append(i)
            neu += 1
    return daten, neu, ersetzt


def import_json(daten, text, mit_einstellungen=False):
    """JSON-Export (ganzer Stand) oder Liste von Ideen einlesen. -> (daten, neu, ersetzt); ValueError bei Unsinn."""
    try:
        roh = json.loads(text)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Keine gültige JSON-Datei ({e})") from None
    if isinstance(roh, list):
        return _zusammenfuehren(daten, roh)
    if isinstance(roh, dict) and isinstance(roh.get("ideen"), list):
        return _zusammenfuehren(daten, roh["ideen"], roh.get("einstellungen") if mit_einstellungen else None)
    raise ValueError("Die Datei enthält keine Ideen.")


FIN_SPALTEN = {"start_invest": "Startinvestition €", "umsatz_monat": "Umsatz/Monat €",
               "var_kosten_pct": "variable Kosten %", "fix_monat": "Fixkosten/Monat €",
               "stunden_woche": "Stunden/Woche", "stunden_anlauf_woche": "Stunden/Woche Anlauf",
               "anlauf_monate": "Anlauf Monate", "horizont_jahre": "Horizont Jahre",
               "steuersatz_pct": "Steuersatz %", "afa_jahre": "Abschreibung Jahre", "hebesatz_pct": "Hebesatz %"}


def export_csv(daten, kennzahlen=None):
    """Eine Zeile je Idee (Semikolon, deutsches Komma): Stammdaten, Phasen-Scores, Kriterien, Finanzen und -
    falls uebergeben - berechnete Kennzahlen {idee_id: {spalte: wert}} (beim Import ignoriert)."""
    daten = bereinigen(daten)
    kr = daten["einstellungen"]["kriterien"]
    kopf = (["id", "Name", "Beschreibung", "Status"] + [f"Phase {nr} {t}" for nr, t, _ in PHASEN] +
            [f"Kriterium {k['name']}" for k in kr] + list(FIN_SPALTEN.values()))
    extra = sorted({s for z in (kennzahlen or {}).values() for s in z})
    puffer = io.StringIO()
    w = csv.writer(puffer, delimiter=";")
    w.writerow(kopf + extra)
    for i in daten["ideen"]:
        z = [i["id"], i["name"], i["beschreibung"], STATUS[i["status"]]]
        z += [i["phasen"][nr]["score"] for nr, _, _ in PHASEN]
        z += [i["kriterien"].get(k["id"], SCORE_START) for k in kr]
        z += [str(i["finanzen"][f]).replace(".", ",") for f in FIN_SPALTEN]
        werte = (kennzahlen or {}).get(i["id"]) or {}
        z += ["" if werte.get(s) is None else str(werte[s]).replace(".", ",") for s in extra]
        w.writerow(z)
    return "﻿" + puffer.getvalue()


def import_csv(daten, text):
    """CSV aus export_csv (auch in Excel bearbeitet) einlesen. -> (daten, neu, ersetzt)"""
    text = str(text or "").lstrip("﻿")
    try:
        dialekt = csv.Sniffer().sniff(text.splitlines()[0] if text else "", delimiters=";,\t")
        trenner = dialekt.delimiter
    except csv.Error:
        trenner = ";"
    zeilen = list(csv.DictReader(io.StringIO(text), delimiter=trenner))
    if not zeilen or "Name" not in (zeilen[0] or {}):
        raise ValueError("Die CSV-Datei hat keine Spalte „Name“ – bitte eine aus diesem Export verwenden.")
    bereinigt = bereinigen(daten)
    kr = bereinigt["einstellungen"]["kriterien"]
    status_rueck = {v: k for k, v in STATUS.items()}
    ideen = []
    for z in zeilen:
        if not (z.get("Name") or "").strip():
            continue
        ideen.append({
            "id": (z.get("id") or "").strip() or neue_id(), "name": z["Name"], "beschreibung": z.get("Beschreibung"),
            "status": status_rueck.get((z.get("Status") or "").strip(), (z.get("Status") or "").strip()),
            "phasen": {nr: {"score": z.get(f"Phase {nr} {t}"), "text": ""} for nr, t, _ in PHASEN},
            "kriterien": {k["id"]: z.get(f"Kriterium {k['name']}") for k in kr},
            "finanzen": {f: z.get(sp) for f, sp in FIN_SPALTEN.items()}})
    # Texte der Phasen bestehender Ideen behalten (die CSV traegt nur Scores)
    alt = {i["id"]: i for i in bereinigt["ideen"]}
    for i in ideen:
        if i["id"] in alt:
            for nr, _, _ in PHASEN:
                i["phasen"][nr]["text"] = alt[i["id"]]["phasen"][nr]["text"]
            i["szenarien"] = alt[i["id"]]["szenarien"]
            for f in ("erstellt", "status_seit", "start_monat", "ist", "abbruch"):
                i[f] = alt[i["id"]][f]
    return _zusammenfuehren(bereinigt, ideen)
