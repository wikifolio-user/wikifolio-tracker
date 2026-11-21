"""Gap Analyzer (Gap Up & Gap Down) fuer Nasdaq 100, DAX 40, S&P 500 und Dow Jones - reine Rechenlogik.

Datengrundlage: echte, ABGESCHLOSSENE Tageskerzen des Cash-Index (state/markt/ohlc.json, markt_daten.py; Yahoo,
Instrumenttyp INDEX - keine Futures, CFDs oder ETFs). Es werden keine Kurse geschaetzt oder aufgefuellt.

Definitionen (umschaltbar, in allen Ausgaben genannt):
  "hl"   High-Low-Gap (Standard): Gap Up  = Tief heute > Hoch gestern  -> Bereich [Hoch gestern, Tief heute]
                                  Gap Down = Hoch heute < Tief gestern -> Bereich [Hoch heute, Tief gestern]
  "co"   Close-Open-Gap (Eroeffnungsluecke): Eroeffnung heute != Schluss gestern -> Bereich dazwischen
  "pct"  Prozentuale Opening Gaps: wie "co", aber nur ab einer Mindestgroesse in %

Fuellstatus - chronologische Pruefung jeder SPAETEREN Tageskerze (bei Eroeffnungsluecken zaehlt auch der
Entstehungstag ab der Eroeffnung, weil die Luecke dort schon im Tagesverlauf geschlossen werden kann):
  Gap Up:   spaetere Tiefs dringen von oben ein; geschlossen, sobald ein Tief <= untere Grenze
  Gap Down: spaetere Hochs dringen von unten ein; geschlossen, sobald ein Hoch >= obere Grenze
Die urspruenglichen Grenzen bleiben unveraendert; dazu kommen die noch offenen Grenzen und der Fuellgrad.
Ein geschlossenes Gap wird nie wieder offen. Fehlen Handelstage (laut Boersenkalender) zwischen Entstehung und
letzter Kerze, gilt das Gap als "nicht vollstaendig geprueft" - nie als "verifiziert offen".
"""
import datetime
import statistics

DEFINITIONEN = {"hl": "High-Low-Gap", "co": "Close-Open-Gap", "pct": "Opening Gap (%)"}
STATUS = {"offen": "Unberührt", "teilweise": "Teilweise", "geschlossen": "Geschlossen"}
INDEX = {"^NDX": ("NDX", "Nasdaq 100"), "^GDAXI": ("DAX", "DAX 40"), "^GSPC": ("SPX", "S&P 500"),
         "^DJI": ("DJI", "Dow Jones")}
SCHLIESS_FENSTER = (1, 5, 10, 20, 60)
PCT_MINDEST = 0.5                     # Standard-Mindestgroesse fuer prozentuale Opening Gaps


def gap_id(kurz, definition, datum):
    """Stabile, eindeutige ID: Instrument | Zeitrahmen | Definition | Entstehungsdatum."""
    return f"{kurz}|1d|{definition}|{datum}"


def kerzen_pruefen(kerzen):
    """OHLC-Validierung (Reihenfolge, Doppelte, Werte) -> (saubere_kerzen, probleme). Ungueltige fallen weg."""
    probleme, aus, vorher = [], [], None
    for k in sorted(kerzen or [], key=lambda x: str(x[0])):
        try:
            d, o, h, l_, c = str(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4])
            datetime.date.fromisoformat(d)
        except (TypeError, ValueError, IndexError):
            probleme.append(f"Unlesbare Kerze: {k!r}"[:80])
            continue
        if d == vorher:
            probleme.append(f"Doppelter Tag {d} (verworfen)")
            continue
        if min(o, h, l_, c) <= 0 or l_ > min(o, c) + 1e-9 or h < max(o, c) - 1e-9:
            probleme.append(f"Ungültige Kerze {d} (verworfen)")
            continue
        aus.append([d, o, h, l_, c])
        vorher = d
    return aus, probleme


def _luecke(kv, k, definition, pct_min):
    """Gap zwischen Vortageskerze kv und Kerze k -> (typ, unten, oben) oder None."""
    _, _, hv, lv, cv = kv
    _, o, h, l_, _ = k
    if definition == "hl":
        if l_ > hv:
            return "up", hv, l_
        if h < lv:
            return "down", h, lv
        return None
    if o > cv:
        g = ("up", cv, o)
    elif o < cv:
        g = ("down", o, cv)
    else:
        return None
    if definition == "pct" and abs(o / cv - 1) * 100 < pct_min:
        return None
    return g


def erkennen(kerzen, kurz, definition="hl", fehlende=(), pct_min=PCT_MINDEST, stand=None):
    """Alle Gaps chronologisch erkennen und ihren Fuellstatus bis zur letzten Kerze bestimmen.
    kerzen: [[iso, o, h, l, c]] (geprueft, aufsteigend); fehlende: Handelstage ohne Kerze (aus der Datenpruefung).
    -> Liste von Gap-dicts."""
    fehlende = sorted(set(fehlende or ()))
    gaps = []
    for i in range(1, len(kerzen)):
        g = _luecke(kerzen[i - 1], kerzen[i], definition, pct_min)
        if not g:
            continue
        typ, unten, oben = g
        d = kerzen[i][0]
        luecke_davor = any(kerzen[i - 1][0] < f < d for f in fehlende)        # Vortag fehlt -> unsicher
        gap = {"id": gap_id(kurz, definition, d), "index": kurz, "datum": d, "typ": typ, "definition": definition,
               "unten": unten, "oben": oben, "groesse": oben - unten,
               "groesse_pct": (oben - unten) / (unten if typ == "up" else oben) * 100,
               "vortag_wert": kerzen[i - 1][2] if typ == "up" else kerzen[i - 1][3],
               "tag_wert": kerzen[i][3] if typ == "up" else kerzen[i][2],
               "status": "offen", "offen_unten": unten, "offen_oben": oben, "fuellgrad": 0.0,
               "beruehrt": None, "geschlossen": None, "alter": len(kerzen) - 1 - i,
               "geprueft_bis": kerzen[-1][0], "stand": stand,
               "vollstaendig": not luecke_davor and not any(f > d for f in fehlende)}
        # Pruefung der folgenden Kerzen (bei Eroeffnungsluecken ab dem Entstehungstag selbst)
        erste = i if definition in ("co", "pct") else i + 1
        for k in kerzen[erste:]:
            if typ == "up":
                tief = k[3]
                if tief < gap["offen_oben"]:
                    gap["beruehrt"] = gap["beruehrt"] or k[0]
                    if tief <= unten:
                        gap.update(status="geschlossen", geschlossen=k[0], offen_oben=unten)
                        break
                    gap.update(status="teilweise", offen_oben=tief)
            else:
                hoch = k[2]
                if hoch > gap["offen_unten"]:
                    gap["beruehrt"] = gap["beruehrt"] or k[0]
                    if hoch >= oben:
                        gap.update(status="geschlossen", geschlossen=k[0], offen_unten=oben)
                        break
                    gap.update(status="teilweise", offen_unten=hoch)
        offen = gap["offen_oben"] - gap["offen_unten"] if gap["status"] != "geschlossen" else 0.0
        gap["offen_breite"] = max(0.0, offen)
        gap["fuellgrad"] = 100.0 if gap["status"] == "geschlossen" else (1 - gap["offen_breite"] / gap["groesse"]) * 100
        if gap["geschlossen"]:
            gap["dauer"] = sum(1 for k in kerzen if d < k[0] <= gap["geschlossen"])   # Handelstage bis Schliessung
        else:
            gap["dauer"] = None
        gaps.append(gap)
    return gaps


def lage(gap, kurs):
    """Aktuelle Lage des noch offenen Bereichs relativ zum Kurs und Entfernung zum naechsten Punkt (nie negativ).
    -> (lage: "oberhalb"/"unterhalb"/"innerhalb"/None, entfernung_punkte, entfernung_pct)"""
    if gap["status"] == "geschlossen" or not kurs:
        return None, None, None
    u, o = gap["offen_unten"], gap["offen_oben"]
    if kurs < u:
        e = u - kurs
        return "oberhalb", e, e / kurs * 100
    if kurs > o:
        e = kurs - o
        return "unterhalb", e, e / kurs * 100
    return "innerhalb", 0.0, 0.0


def mit_lage(gaps, kurs):
    for g in gaps:
        g["lage"], g["entfernung"], g["entfernung_pct"] = lage(g, kurs)
    return gaps


def naechste(gaps, n=3):
    """Je drei naechstgelegene offene/teilweise Gaps oberhalb und unterhalb (Liste muss mit_lage haben).
    Gaps, in denen der Kurs gerade steht, zaehlen zu beiden Seiten (Entfernung 0)."""
    offen = [g for g in gaps if g["status"] != "geschlossen" and g.get("lage")]
    ob = sorted([g for g in offen if g["lage"] in ("oberhalb", "innerhalb")], key=lambda g: g["entfernung"])[:n]
    un = sorted([g for g in offen if g["lage"] in ("unterhalb", "innerhalb")], key=lambda g: g["entfernung"])[:n]
    return ob, un


def statistik(gaps, letzte_kerze_index=None):
    """Statistik je Gap-Liste. Schliessungsquoten je Fenster nur ueber Gaps, die mindestens so lange beobachtet
    werden konnten (alter >= Fenster); offene Gaps sind zensierte Beobachtungen, keine "nie geschlossen"."""
    def zus(liste):
        if not liste:
            return {"anzahl": 0}
        groessen = [g["groesse_pct"] for g in liste]
        punkte = [g["groesse"] for g in liste]
        dauer = [g["dauer"] for g in liste if g["dauer"] is not None]
        quoten = {}
        for n in SCHLIESS_FENSTER:
            basis = [g for g in liste if (g["dauer"] is not None and g["dauer"] <= n) or g["alter"] >= n]
            zu = [g for g in basis if g["dauer"] is not None and g["dauer"] <= n]
            quoten[n] = (len(zu) / len(basis) * 100, len(basis)) if basis else (None, 0)
        return {"anzahl": len(liste), "up": sum(g["typ"] == "up" for g in liste),
                "down": sum(g["typ"] == "down" for g in liste),
                "geschlossen": sum(g["status"] == "geschlossen" for g in liste),
                "teilweise": sum(g["status"] == "teilweise" for g in liste),
                "offen": sum(g["status"] == "offen" for g in liste),
                "zensiert": sum(g["status"] != "geschlossen" for g in liste),
                "groesse_pct_mittel": statistics.mean(groessen), "groesse_pct_median": statistics.median(groessen),
                "groesse_mittel": statistics.mean(punkte), "groesse_median": statistics.median(punkte),
                "dauer_mittel": statistics.mean(dauer) if dauer else None,
                "dauer_median": statistics.median(dauer) if dauer else None,
                "quote_gesamt": len(dauer) / len(liste) * 100, "quoten": quoten}
    return {"alle": zus(gaps), "up": zus([g for g in gaps if g["typ"] == "up"]),
            "down": zus([g for g in gaps if g["typ"] == "down"])}


def zeitraum(gaps, von=None, bis=None):
    """Gaps, die im Zeitraum entstanden sind (iso-Daten, einschliesslich). Der Fuellstatus bleibt der bis zur
    letzten Kerze geprueften Stand."""
    return [g for g in gaps if (not von or g["datum"] >= von) and (not bis or g["datum"] <= bis)]


def uebersicht(gaps, kurs):
    """Kennzahlen fuer eine Index-Karte."""
    offen = [g for g in gaps if g["status"] != "geschlossen"]
    ob, un = naechste(gaps, 1)
    return {"offen_up": sum(g["typ"] == "up" and g["status"] == "offen" for g in gaps),
            "offen_down": sum(g["typ"] == "down" and g["status"] == "offen" for g in gaps),
            "teilweise": sum(g["status"] == "teilweise" for g in gaps), "offen": len(offen),
            "summe_offen": sum(g["offen_breite"] for g in offen),
            "naechstes_oben": ob[0] if ob else None, "naechstes_unten": un[0] if un else None,
            "ungeprueft": sum(not g["vollstaendig"] for g in offen), "kurs": kurs}


# ---------------------------------------------------------------------------------------------------- Alerts
STANDARD_ALERTS = {"naehe_an": True, "naehe_pct": 1.0, "erreicht_an": True, "teilweise_an": True,
                   "geschlossen_an": True, "neu_an": True, "gross_an": True, "gross_pct": 1.0}
ALERT_TAGE = 7          # nur Ereignisse der letzten Tage melden, nicht die ganze Historie


def alerts(gaps_je_index, kurse, einstellungen, gesehen=(), heute=None):
    """Ereignisse -> [{"schluessel", "text", "neu"}]. Jedes Ereignis (Gap-ID + Art) nur einmal."""
    e = dict(STANDARD_ALERTS, **(einstellungen or {}))
    heute = heute or datetime.date.today()
    grenze = (heute - datetime.timedelta(days=ALERT_TAGE)).isoformat()
    gesehen = set(gesehen)
    aus = []

    def add(gap, art, text):
        sch = f"{gap['id']}|{art}"
        aus.append({"schluessel": sch, "text": text, "neu": sch not in gesehen, "index": gap["index"]})
    for kurz, gaps in gaps_je_index.items():
        kurs = kurse.get(kurz)
        for g in gaps:
            name = f"{kurz} {'Gap Up' if g['typ'] == 'up' else 'Gap Down'} vom {g['datum']}"
            if e["neu_an"] and g["datum"] >= grenze:
                add(g, "neu", f"Neues {name}: {g['unten']:.1f}–{g['oben']:.1f} ({g['groesse_pct']:.2f} %)")
            if e["gross_an"] and g["datum"] >= grenze and g["groesse_pct"] >= e["gross_pct"]:
                add(g, "gross", f"Großes {name}: {g['groesse_pct']:.2f} %")
            if e["teilweise_an"] and g["beruehrt"] and g["beruehrt"] >= grenze and g["status"] == "teilweise":
                add(g, "teilweise", f"{name} teilweise geschlossen ({g['fuellgrad']:.0f} %)")
            if e["geschlossen_an"] and g["geschlossen"] and g["geschlossen"] >= grenze:
                add(g, "geschlossen", f"{name} vollständig geschlossen am {g['geschlossen']}")
            if g["status"] != "geschlossen" and kurs:
                lg, ent, ent_pct = lage(g, kurs)
                if e["erreicht_an"] and lg == "innerhalb":
                    add(g, "erreicht", f"{kurz} notiert im offenen Bereich des {name}")
                elif e["naehe_an"] and ent_pct is not None and ent_pct < e["naehe_pct"]:
                    add(g, "naehe", f"{kurz} nur {ent_pct:.2f} % vom offenen {name} entfernt")
    for a in aus:
        a["text"] = a["text"].replace(".", ",")
    return aus
