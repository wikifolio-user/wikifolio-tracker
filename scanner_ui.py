"""Investment-Scanner (eigene Ansicht unter Planung & Analyse). Rechenkern: scanner.py.

Kapital, Sparrate, Kredit, Laufzeit und Zielvermoegen kommen aus den gespeicherten Builder-Eingaben; die Scanner-
Einstellungen (Risikoprofil, Aufteilung, Verlusttoleranz, Hoechstgewicht, Kosten, Inflation) werden mit
ihnen gespeichert. Gerechnet wird nur auf Knopfdruck - das Ergebnis bleibt in der Sitzung stehen.
"""
import datetime
import html

import streamlit as st

import portfolio_builder as P
import scanner as S
from portfolio_builder_ui import _smartphone
import formate as FMT

PROFIL_TITEL = {"niedrig": "Niedrig", "mittel": "Mittel", "hoch": "Hoch", "eigene": "Eigene",
                S.FAVORITEN: "Favoriten"}
ART_TITEL = {"etf": "ETF", "aktie": "Aktie", "wikifolio": "wikifolio", "cash": "Cash"}
KLASSEN_KURZ = {"etf": "ETFs", "aktie": "Aktien", "wikifolio": "wikifolios"}


def _de(x, dez=0):
    return f"{x:,.{dez}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _eur(x, dez=0):
    return FMT.eur(x, dez)


def _pct(x, dez=1, vz=False):
    return FMT.pct(x, dez, vz)


def _esc(t):
    return html.escape("" if t is None else str(t))


# ---------------------------------------------------------------- Daten
def _daten(h, katalog):
    """Kandidaten aus Qualitaets-Score (Fundamentaldaten), Index-Listen und Builder-Katalog + Datenstand."""
    lies = (h or {}).get("gh_read_taeglich")

    def datei(pfad):
        try:
            return (lies(pfad, None) if lies else None) or {}
        except Exception:
            return {}

    q = datei("state/qualitaet.json")
    alle = {}
    for i in range(4):
        d = datei(f"state/top50_alle_{i}.json")
        f = d.get("felder") or []
        if "s" in f:
            for z in d.get("zeilen") or []:
                alle[z[f.index("s")]] = dict(zip(f, z))
    fx = {k: v[1] for k, v in (datei("state/top50_fx.json") or {}).items()
          if isinstance(v, (list, tuple)) and len(v) > 1 and v[1]}
    top = datei("state/top50.json")
    # Yahoo-Symbol -> ISIN (Zuordnung des Watchlist-Agenten, {isin: symbol}; "" = nicht gefunden)
    isin = {sym: i for i, sym in ((datei("state/top50_yahoo.json") or {}).get("isin") or {}).items()
            if sym and isinstance(i, str) and len(i) == 12}
    kand = S.kandidaten_aktien(q.get("werte") or {}, alle, fx, isin) + S.kandidaten_katalog(katalog)
    stand = {"Qualitäts-Score (Fundamentaldaten)": q.get("stand"), "Ranglisten / Performance": top.get("stand")}
    return kand, stand


# ---------------------------------------------------------------- Einstellungen
def _profil_gewaehlt():
    p = st.session_state.get("pb_scan_profil")
    if p in S.PROFILE:
        st.session_state["pb_scan_max_dd"] = S.PROFILE[p]["max_dd"]
        for k in ("etf", "aktie", "wikifolio", "cash"):
            st.session_state[f"pb_scan_{k}"] = S.PROFILE[p][k]


def _favoriten_katalog(katalog):
    """{kennung: Katalog-Eintrag} - waehlbare Werte der Top-500-/Watchlist-Daten (Aktien, ETFs, wikifolios)."""
    return {S.kennung(w): w for w in katalog if w.get("art") in ("aktie", "etf", "wikifolio")}


def _favoriten(e, katalog_fn):
    """Favoriten aus der Top-500-Liste auswaehlen; die Rechnung nutzt dann nur diese Werte."""
    je = _favoriten_katalog(katalog_fn())
    gewaehlt = [k for k in (st.session_state.get("pb_scan_favoriten") or []) if k in je]
    if gewaehlt != st.session_state.get("pb_scan_favoriten"):
        st.session_state["pb_scan_favoriten"] = gewaehlt      # nicht mehr in der Liste -> raus (sonst Fehler)

    def beschriftung(k):
        w = je[k]
        return " · ".join(t for t in (w["name"], ART_TITEL.get(w["art"], w["art"]), w.get("wkn") or w.get("isin"),
                                      _eur(w["kurs"], 2) if w.get("kurs") else "") if t)

    st.multiselect(f"⭐ Favoriten aus der Top-500-Liste ({len(je)} Werte)", list(je), key="pb_scan_favoriten",
                   format_func=beschriftung, max_selections=S.MAX_FAVORITEN,
                   placeholder="Name, WKN oder ISIN eintippen …")
    n = {a: sum(1 for k in gewaehlt if je[k]["art"] == a) for a in ("etf", "aktie", "wikifolio")}
    if not gewaehlt:
        st.info("Noch keine Favoriten – oben Aktien, ETFs oder wikifolios auswählen. Gerechnet wird dann nur mit "
                "diesen Werten, nach Aufteilung, Max. Verlust und Max. je Position unten.")
        return
    teile = [f"{n[a]} {KLASSEN_KURZ[a]}" for a in ("aktie", "etf", "wikifolio")]
    st.caption("Favoriten: " + " · ".join(teile) + ". Je Klasse gleich gewichtet, jede Position höchstens "
               "„Max. je Position“ – der Rest der Klasse geht ins Cash.")
    leer = [f"{KLASSEN_KURZ[a]} {_de(e[f'scan_{a}'])} %" for a in ("etf", "aktie", "wikifolio")
            if e[f"scan_{a}"] > 0 and not n[a]]
    ungenutzt = [KLASSEN_KURZ[a] for a in ("etf", "aktie", "wikifolio") if n[a] and e[f"scan_{a}"] <= 0]
    if leer:
        st.warning("Keine Favoriten für " + ", ".join(leer) + " – dieser Anteil bliebe Cash. Favoriten ergänzen "
                   "oder die Aufteilung unten anpassen.")
    if ungenutzt:
        st.warning("Favoriten bei " + ", ".join(ungenutzt) + " werden nicht genutzt – die Aufteilung unten steht "
                   "dort auf 0 %.")


def _einstellungen(e, katalog_fn=None):
    st.segmented_control("Risikobereitschaft", list(PROFIL_TITEL),
                         format_func=lambda p: "⭐ Favoriten" if p == S.FAVORITEN else PROFIL_TITEL[p],
                         key="pb_scan_profil", on_change=_profil_gewaehlt,
                         help="Niedrig / Mittel / Hoch sind Vorschläge für die Aufteilung und die Verlusttoleranz. "
                              "„Eigene“: alles selbst festlegen. „Favoriten“: nur selbst ausgewählte Werte der "
                              "Top-500-Liste, Aufteilung und Regeln wie bei „Eigene“.")
    if e["scan_profil"] == S.FAVORITEN and katalog_fn:
        _favoriten(e, katalog_fn)
    eigene = e["scan_profil"] in ("eigene", S.FAVORITEN)
    handy = _smartphone()
    with st.container(key="pb_scan_reihe1"):
        # Handy: 2 je Zeile - bei 4 nebeneinander zerbrechen die Beschriftungen
        c = (st.columns(2, vertical_alignment="bottom") + st.columns(2, vertical_alignment="bottom")) if handy \
            else st.columns(4, vertical_alignment="bottom")
        for spalte, (k, titel) in zip(c, (("etf", "ETFs %"), ("aktie", "Aktien %"), ("wikifolio", "wikifolios %"),
                                          ("cash", "Cash %"))):
            spalte.number_input(titel, 0.0, 100.0, step=5.0, format="%.0f", key=f"pb_scan_{k}", disabled=not eigene,
                                help=None if eigene else "Für eigene Werte oben „Eigene“ wählen.")
    summe = sum(e[f"scan_{k}"] for k in ("etf", "aktie", "wikifolio", "cash"))
    if eigene and abs(summe - 100) > 0.5:
        st.caption(f"Summe {_de(summe)} % – wird beim Berechnen auf 100 % umgerechnet.")
    with st.container(key="pb_scan_reihe2"):
        c = (st.columns(2, vertical_alignment="bottom") + st.columns(2, vertical_alignment="bottom")) if handy \
            else st.columns(4, vertical_alignment="bottom")
        c[0].number_input("Max. Verlust %", 5.0, 95.0, step=5.0, format="%.0f", key="pb_scan_max_dd",
                          help="Höchster tolerierter zwischenzeitlicher Rückgang vom bisherigen Höchststand. Geprüft wird, dass er in 19 "
                               "von 20 simulierten Verläufen (95 %) nicht überschritten wird – garantiert ist das nie.")
        c[1].number_input("Max. je Position %", 1.0, 100.0, step=0.5, format="%.1f",
                          key="pb_scan_max_gewicht", help="Höchstgewicht je Position: keine einzelne Aktie, kein ETF, "
                                                          "kein wikifolio darüber.")
        c[2].number_input("Kosten % p. a.", 0.0, 5.0, step=0.1, format="%.1f", key="pb_scan_kosten",
                          help="Laufende Kosten, Spreads, Ordergebühren – werden von der Rendite abgezogen.")
        c[3].number_input("Inflation % p. a.", -5.0, 20.0, step=0.5, format="%.1f", key="pb_scan_inflation",
                          help="Nur für die Kaufkraft-Angabe (realer Wert am Ende).")
    st.toggle("Auf Zielwahrscheinlichkeit optimieren", key="pb_scan_optimieren",
              help="Prüft, ob weniger investiert (mehr Cash) die Chance aufs Ziel erhöht oder nötig ist, um die "
                   "Verlusttoleranz einzuhalten. Mehr als deine Aufteilung wird nie investiert; bringt Cash keinen "
                   "Vorteil, bleibt es bei deiner Aufteilung. Das Musterdepot im Menü nutzt immer deine Aufteilung.")
    # die ?-Symbole oeffnen nur bei Maus-Hover - auf Handy/Tablet sind sie nicht erreichbar
    with st.expander("ℹ️ Was bedeuten die Einstellungen?"):
        st.markdown(
            "- **Risikobereitschaft** – Niedrig / Mittel / Hoch setzen Vorschläge für Aufteilung und Max. Verlust; "
            "bei **Eigene** legst du alles selbst fest. Bei **⭐ Favoriten** wählst du die Werte selbst aus der "
            "Top-500-Liste – gerechnet wird nur mit ihnen, je Klasse gleich gewichtet, mit Aufteilung, Max. Verlust "
            "und Max. je Position wie bei „Eigene“.\n"
            "- **ETFs / Aktien / wikifolios / Cash %** – deine Aufteilung. Weicht die Summe von 100 % ab, wird "
            "beim Berechnen umgerechnet.\n"
            "- **Max. Verlust %** – höchster tolerierter zwischenzeitlicher Rückgang vom Höchststand. Geprüft wird, "
            "dass er in 19 von 20 simulierten Verläufen (95 %) nicht überschritten wird – garantiert ist das nie.\n"
            "- **Max. je Position %** – keine einzelne Aktie, kein ETF, kein wikifolio bekommt mehr Gewicht.\n"
            "- **Kosten % p. a.** – laufende Kosten, Spreads, Ordergebühren; werden von der Rendite abgezogen.\n"
            "- **Inflation % p. a.** – nur für die Kaufkraft-Angabe (realer Wert am Ende).\n"
            "- **Auf Zielwahrscheinlichkeit optimieren** – der Scanner rechnet dein Depot mit 30 %, 40 % … 100 % "
            "deiner Aufteilung investiert (Rest Cash) je 4.000-mal durch. Gewählt wird die Stufe mit der höchsten "
            "Chance, dein Zielvermögen zu erreichen, deren Rückgang den Max. Verlust einhält; bei Gleichstand die "
            "mit dem höheren mittleren Endwert. Mehr als deine Aufteilung wird nie investiert – bringt Cash keinen "
            "Vorteil, bleibt es bei 100 %. Hält keine Stufe den Max. Verlust ein, wird die vorsichtigste genommen. "
            "Ausgeschaltet wird genau deine Aufteilung gerechnet. Das gespeicherte Musterdepot nutzt immer deine "
            "Aufteilung.")


# ---------------------------------------------------------------- Rechnen
def _berechnen(h, e, katalog):
    kand, stand = _daten(h, katalog)
    favoriten = e["scan_profil"] == S.FAVORITEN
    if favoriten:                                  # nur die ausgewaehlten Werte (bewertet im Vergleich mit allen)
        je = _favoriten_katalog(katalog)
        kand = S.favoriten_markieren(kand, [je[k] for k in e["scan_favoriten"] if k in je])
    jahre = P.monate(e) / 12.0
    bewertet = S.bewerten(kand, jahre)
    auswahl = [c for c in bewertet if c.get("favorit")] if favoriten else bewertet
    nachgeladen = _kurse_nachladen(h, auswahl, alle=favoriten)
    auft = S.aufteilung(e)
    depot = S.musterdepot(auswahl, auft, e["scan_max_gewicht"], nur_mit_kurs=True,   # Stueckzahlen moeglich
                          frei=favoriten)
    depot_profil = depot                           # genau die Prozentanteile des Risikoprofils (fuers Musterdepot)
    ziel = e["zielvermoegen"]
    opt = None
    if e["scan_optimieren"] and depot["positionen"]:
        opt = S.optimieren(depot, e, ziel, e["scan_max_dd"], e["scan_kosten"])
        depot = S.skalieren(depot, opt["beste"])
    mu, sigma = S.portfolio_kennzahlen(depot)
    start, cfs, rest = S.zahlungsplan(e, depot)
    sim = S.simulieren(mu, sigma, start, cfs, e["scan_kosten"], pfade=10000)
    a = S.auswerten(sim, ziel, rest)
    alt = None
    if ziel > 0 and (a["wahrscheinlichkeit"] or 0) < 0.5:
        alt = S.alternativen(mu, sigma, e, ziel, e["scan_kosten"], depot=depot)
    benoetigt = P.benoetigte_rendite(e) if ziel > 0 else None
    zd = None
    if benoetigt and (a["wahrscheinlichkeit"] or 0) < 0.5:     # Ziel mit dem normalen Depot unwahrscheinlich
        # alle Werte der Top-500-/Watchlist-Daten (auch die ~16.000 Aktien ohne Fundamentaldaten)
        # Favoriten: nur aus der eigenen Auswahl
        alle = [] if favoriten else S.kandidaten_katalog(katalog, arten=("aktie", "etf", "wikifolio"))
        zd = S.ziel_depot(auswahl + alle, benoetigt["rendite"], e["scan_max_gewicht"])
    return {"zeit": datetime.datetime.now().strftime("%d.%m.%Y, %H:%M Uhr"), "stand": stand, "depot_profil": depot_profil,
            "kurse_nachgeladen": nachgeladen, "ziel_depot": zd,
            "anzahl": {k: sum(1 for c in bewertet if c["art"] == k) for k in ("aktie", "etf", "wikifolio")},
            "bewertet": bewertet, "aufteilung": auft, "depot": depot, "optimierung": opt, "mu": mu, "sigma": sigma,
            "auswertung": a, "verlauf": S.verlauf_jaehrlich(sim), "restschuld": rest, "start": start,
            "eingezahlt": start + sum(c for c in cfs if c > 0), "alternativen": alt, "benoetigt": benoetigt,
            "entnommen": sum(S.entnahmen(e, depot)),
            "monate": len(cfs), "eingaben": dict(e)}


def _kurse_nachladen(h, bewertet, alle=False):
    """Aktuelle Kurse fuer moegliche Depotwerte ohne Kurs in den Top-500-Daten: Kurs-ID aus den Top-500-Listen
    (sonst exakte Suche ueber WKN/ISIN), dann der aktuelle Kurs von ls-tc.de. Traegt kurs + instrument_id in
    die Kandidaten ein. -> Anzahl nachgeladen"""
    hole, suche = (h or {}).get("get_live_kurs"), (h or {}).get("suche_instrument")
    fehlt = S.kurs_fehlt(bewertet, je_klasse=S.MAX_FAVORITEN, alle=True) if alle else S.kurs_fehlt(bewertet)
    if not fehlt or not hole:
        return 0
    import investment_scanner_pro_engine as PRO
    import planer_ui as PU
    ids = S.top500_ids(_lies(h, "state/top50_ids.json"), _lies(h, "state/top50_wikifolios.json"))
    gemerkt = st.session_state.setdefault("pb_scan_iid", {})

    def kurs_holen(c):
        k = S.kennung(c)
        iid = next((ids[x.upper()] for x in (c.get("isin"), c.get("wkn")) if x and x.upper() in ids), None)
        if iid is None and suche and (c.get("isin") or c.get("wkn")):
            if k not in gemerkt:
                t, art = PRO.treffer_waehlen(c, suche(c.get("isin") or c.get("wkn")) or [])
                gemerkt[k] = int(t["instrument_id"]) if t and art == "exakt" else None
            iid = gemerkt[k]
        if not iid:
            return None
        akt, vor, _ = hole(iid)
        kurs = akt or vor
        return (iid, float(kurs)) if kurs and kurs > 0 else None

    erg = PU._parallel([(i, kurs_holen, (c,)) for i, c in enumerate(fehlt)])
    n = 0
    for i, c in enumerate(fehlt):
        r = erg.get(i)
        if isinstance(r, tuple):
            c["instrument_id"], c["kurs"] = r
            c["kurs_quelle"] = "ls-tc.de aktuell"
            n += 1
    return n


def _signatur(e):
    felder = [k for k in e if k.startswith("scan_")] + ["anfangskapital", "sonstiges_kapital", "kredit_summe",
                                                        "kredit_rate", "kredit_zins_pa", "einzahlung", "entnahme", "entnahme_art",
                                                        "ausgaben", "laufzeit", "laufzeit_einheit", "zielvermoegen"]
    return tuple((k, e.get(k)) for k in sorted(felder))


# ---------------------------------------------------------------- Anzeige
def _tabelle_html(kopf, zeilen, rechts=(), text=(), breit=False):
    """Tabelle; rechts = rechtsbuendige Spalten, text = Spalten mit Fliesstext (duerfen umbrechen).
    Erste Spalte bleibt beim seitlichen Wischen stehen."""
    def kl(i):
        return " ".join(k for k, ja in (("r", i in rechts), ("t", i in text), ("n", i == 0)) if ja)

    th = "".join(f'<th class="{kl(i)}">{_esc(k)}</th>' for i, k in enumerate(kopf))
    tr = "".join("<tr>" + "".join(f'<td class="{kl(i)}">{z}</td>' for i, z in enumerate(zeile))
                 + "</tr>" for zeile in zeilen)
    st.markdown(f'<div class="pb-scan-wrap"><table class="pb-scan{" breit" if breit else ""}"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody>'
                f'</table></div>', unsafe_allow_html=True)


DEPOT_KOPF = ["Wertpapier", "Gewicht", "Betrag", "Rendite p. a.", "Grundlage", "Beitrag", "Kategorie",
              "ISIN / WKN / Ticker", "Begründung"]
# feste Spaltenbreiten (% der Tabelle): beide Musterdepots stehen genau untereinander
DEPOT_BREITEN = (16, 6, 8, 8, 8, 7, 7, 11, 29)
DEPOT_MIN_PX = 1150                                   # schmaler: seitlich wischen, Name bleibt stehen


def _depot_tabelle(zeilen):
    """Musterdepot als Tabelle - gleiche Spalten fuer das Zielrendite- und das normale Musterdepot."""
    def fett(t, z):
        return f"<b>{t}</b>" if z["typ"] == "summe" else t

    html_zeilen = []
    for z in zeilen:
        summe = z["typ"] == "summe"
        html_zeilen.append([
            f"<b>{_esc(z['name'])}</b>", fett(_pct(z["gewicht"]), z), fett(_eur(z["betrag"]), z),
            "" if z["rendite"] is None else _pct(z["rendite"], 1, True), _esc(z["grundlage"]),
            fett(_pct(z["beitrag"], 2, True), z), "" if summe else _esc(ART_TITEL.get(z["art"], z["art"])),
            _esc(z["kennung"]), _esc(z["grund"])])
    kopf = "".join(f'<col style="width:{b}%">' for b in DEPOT_BREITEN)
    th = "".join(f'<th class="{"r" if 1 <= i <= 5 else "n" if i == 0 else ""}">{_esc(k)}</th>'
                 for i, k in enumerate(DEPOT_KOPF))
    tr = "".join("<tr" + (' class="summe"' if z["typ"] == "summe" else "") + ">" + "".join(
        f'<td class="{"r" if 1 <= i <= 5 else "n" if i == 0 else "t" if i == 8 else ""}">{x}</td>'
        for i, x in enumerate(zeile)) + "</tr>" for z, zeile in zip(zeilen, html_zeilen))
    st.markdown(f'<div class="pb-scan-wrap"><table class="pb-scan depot" style="min-width:{DEPOT_MIN_PX}px">'
                f'<colgroup>{kopf}</colgroup><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>',
                unsafe_allow_html=True)


def _kennung(c):
    return c.get("isin") or c.get("wkn") or c.get("ticker") or "–"


def _ziel_zeile(erg):
    """Fuer das Ziel noetige Rendite gegen die erwartete Rendite dieses Depots - auf einen Blick."""
    e, a = erg["eingaben"], erg["auswertung"]
    if e["zielvermoegen"] <= 0:
        return
    ben = (erg.get("benoetigt") or {})
    w = a.get("wahrscheinlichkeit") or 0.0
    erw = erg["mu"] - e["scan_kosten"]
    noetig = (f"über {_pct(ben['rendite'], 0)}" if ben and not ben.get("erreichbar", True)
              else _pct(ben.get("rendite"), 1) if ben else "–")
    zd = erg.get("ziel_depot")
    if w < 0.5 and zd and zd["positionen"] and zd["erreicht"]:
        # Ziel ist erreichbar - mit dem Zielrendite-Depot; das Depot mit der eigenen Aufteilung reicht nicht
        st.success(f"✅ Ziel rechnerisch erreichbar: Für {_eur(e['zielvermoegen'])} sind ≈ {noetig} p. a. nötig – das "
                   f"🎯 Zielrendite-Musterdepot direkt darunter hatte bisher ≈ {_pct(zd['hist_rendite'], 1)} p. a. "
                   f"Mit deiner eigenen Aufteilung (Depot weiter unten) wären nur ≈ {_pct(erw, 1)} p. a. zu erwarten "
                   f"(Wahrscheinlichkeit {_de(w * 100)} %).")
        return
    urteil = ("✅ Ziel erreichbar" if w >= 0.5 else "⚠️ Ziel möglich, aber unsicher" if w >= 0.2
              else "❌ Ziel mit deiner Aufteilung kaum erreichbar")
    text = (f"{urteil}: Für {_eur(e['zielvermoegen'])} nötig ≈ {noetig} p. a. – dieses Depot erwartet ≈ "
            f"{_pct(erw, 1)} p. a. (Wahrscheinlichkeit {_de(w * 100)} %).")
    if w < 0.5 and zd and zd["positionen"]:
        text += (f" Selbst das renditestärkste Depot (darunter) hatte bisher nur ≈ {_pct(zd['hist_rendite'], 1)} p. a.")
    elif w < 0.2:
        text += (" Mehr Rendite heißt mehr Risiko – realistischer sind meist eine höhere Einzahlung, mehr Jahre "
                 "oder ein niedrigeres Ziel (siehe „📈 Prognose“ → Alternativen).")
    (st.success if w >= 0.5 else st.warning if w >= 0.2 else st.error)(text)


def _ziel_depot_anzeige(erg, kapital):
    """Zielrendite-Depot: rechnerisch aufs Ziel - nach vergangener Rendite, bewusst riskant."""
    zd = erg.get("ziel_depot")
    if not zd or not zd["positionen"]:
        return
    ben = (erg.get("benoetigt") or {}).get("rendite")
    st.markdown("#### 🎯 1 · Zielrendite-Musterdepot")
    st.caption("Ausgewählt nach der bisherigen Rendite aller Werte der Top-500-Daten, damit das Ziel rechnerisch "
               "erreicht wird – „Rendite p. a.“ ist hier die bisherige Rendite, keine Prognose.")
    if zd["erreicht"]:
        st.success(f"✅ Ziel erreichbar mit diesem Depot: Diese {len(zd['positionen'])} Werte hatten in der Vergangenheit "
                   f"zusammen ≈ {_pct(zd['hist_rendite'], 1)} p. a. – nötig sind ≈ {_pct(ben, 1)} p. a.")
        st.caption("⚠️ Gilt, wenn sich die außergewöhnlichen Renditen der Vergangenheit wiederholen – sehr riskant, "
                   "große Verluste möglich, keine Anlageempfehlung.")
    else:
        st.error(f"Selbst die renditestärksten Werte mit Kurs hatten zusammen nur ≈ {_pct(zd['hist_rendite'], 1)} p. a. "
                 f"– nötig wären ≈ {_pct(ben, 1)} p. a. Das ist das renditestärkste mögliche Depot.")
    md = st.session_state.get("pb_scan_md_ziel")
    if md:
        {"ok": st.success, "warnung": st.warning, "fehler": st.error}[md[0]](md[1])
    _depot_tabelle(S.depot_zeilen(zd, kapital, "historisch", ben))


def _musterdepot(erg, kapital, zum_builder=None, zum_muster=None):
    md = st.session_state.get("pb_scan_md")
    if md:
        {"ok": st.success, "warnung": st.warning, "fehler": st.error}[md[0]](md[1])
        if md[0] == "ok" and zum_muster:
            st.button("📦 Musterdepot ansehen", key="pb_scan_zum_muster", on_click=zum_muster)
    _ziel_zeile(erg)
    zd = erg.get("ziel_depot")
    zwei = bool(zd and zd["positionen"])
    if zwei:
        st.info("Es gibt **zwei getrennte Musterdepots**, beide unter „📦 Musterdepot“ gespeichert: "
                "**1 · Zielrendite** – ausgewählt nach der bisherigen Rendite, damit das Ziel rechnerisch erreicht "
                "wird (sehr riskant). **2 · Deine Aufteilung** – nach Score und vorsichtiger Prognose, mit deinen "
                "Prozentanteilen. Beide Tabellen haben dieselben Spalten.")
    _ziel_depot_anzeige(erg, kapital)                # erreicht das Ziel rechnerisch - gleich hier, nicht ganz unten
    d = erg["depot"]
    st.markdown(f"#### 📦 {'2 · ' if zwei else ''}Musterdepot mit deiner Aufteilung")
    for hw in d["hinweise"]:
        st.info(hw)
    _depot_tabelle(S.depot_zeilen(d, kapital))
    st.caption(f"{len(d['positionen'])} Positionen, jede höchstens {_pct(d.get('max_gewicht', 5))} · „Rendite p. a.“ "
               f"= vorsichtige Prognose vor Kosten · „Beitrag“ = Gewicht × Rendite.")
    _pdf_knopf(erg, kapital)
    # als Callback: laeuft vor dem Neuaufbau, darf also auch "Automatisch aufs Ziel" umstellen
    st.button("📥 Musterdepot in den Portfolio Builder übernehmen", key="pb_scan_uebernehmen", type="primary",
              width="stretch", on_click=_uebernehmen, args=(d, zum_builder),
              help="Ersetzt die Positionen im Portfolio Builder durch das Musterdepot (Gewichte, erwartete Renditen "
                   "aus der Prognose) und öffnet ihn. „Automatisch aufs Ziel“ wird dabei ausgeschaltet.")


def _pdf_knopf(erg, kapital):
    """PDF-Bericht ueber das Ergebnis - erst auf Knopfdruck erzeugt (dauert etwas)."""
    import scanner_pdf
    schluessel = erg["zeit"]
    if st.button("📄 PDF-Bericht erstellen", key="pb_scan_pdf_knopf", width="stretch"):
        e = erg["eingaben"]
        try:
            st.session_state["pb_scan_pdf"] = (schluessel, scanner_pdf.bericht(
                erg, kapital, PROFIL_TITEL.get(e["scan_profil"], e["scan_profil"])))
        except ImportError:
            st.error("Für das PDF fehlt das Paket **reportlab** (requirements.txt).")
    fertig = st.session_state.get("pb_scan_pdf")
    if fertig and fertig[0] == schluessel:
        st.download_button("⬇️ PDF herunterladen", data=fertig[1], mime="application/pdf",
                           file_name=f"Investment_Scanner_{datetime.date.today().isoformat()}.pdf",
                           key="pb_scan_pdf_download", width="stretch", type="primary")


def _uebernehmen(d, danach=None):
    pos = []
    for p in d["positionen"]:
        pos.append({"name": p["name"], "kurs": p.get("kurs") or 0.0, "gewicht": round(p["gewicht"], 4),
                    "art": p["art"], "wkn": p.get("wkn") or "", "isin": p.get("isin") or "",
                    "rendite": round(p["prognose"]["mu"], 2), "rendite_quelle": "Scanner-Prognose",
                    "rendite_basis": "1J"})
    if d["cash"] > 0.01:
        pos.append({"name": P.TAGESGELD, "kurs": 1.0, "gewicht": round(d["cash"], 4), "art": "sonstig",
                    "rendite": S.ANNAHMEN["tagesgeld"], "rendite_quelle": "Annahme Tagesgeld"})
    st.session_state["pb_entnahme_art"] = "betrag"                               # Entnahme wie im Scanner
    st.session_state["pb_positionen"] = P.bereinigen({"positionen": pos})["positionen"]
    st.session_state["pb_auto_ziel"] = False
    st.session_state["pb_tab_ver"] = st.session_state.get("pb_tab_ver", 0) + 1
    st.session_state["pb_meldung"] = (f"Musterdepot mit {len(pos)} Positionen übernommen – fehlende Kurse werden "
                                      "geholt, die Stückzahlen rechnen sich daraus.")
    if danach:
        danach()


def _lies(h, pfad):
    lies = (h or {}).get("gh_read_taeglich")
    try:
        return (lies(pfad, None) if lies else None) or {}
    except Exception:
        return {}


def top500_kursmap(h):
    """{WKN/ISIN/Symbol (gross): Kurs in EUR} aus den Top-500-/Watchlist-Daten (Tagesschluss): grosser Katalog
    (ETFs, wikifolios, Aktien der ls-tc-Listen) und Qualitaets-Daten (alle Aktien, in EUR umgerechnet)."""
    aus = {}
    for i in range(4):
        d = _lies(h, f"state/planer/katalog_gross_{i}.json")
        f = d.get("felder") or []
        for z in d.get("zeilen") or []:
            w = dict(zip(f, z))
            if isinstance(w.get("kurs"), (int, float)) and w["kurs"] > 0:
                for k in (w.get("kennung"), w.get("isin")):
                    if k:
                        aus.setdefault(str(k).upper(), float(w["kurs"]))
    fx = {k: v[1] for k, v in (_lies(h, "state/top50_fx.json") or {}).items()
          if isinstance(v, (list, tuple)) and len(v) > 1 and v[1]}
    for c in S.kandidaten_aktien((_lies(h, "state/qualitaet.json").get("werte") or {}), {}, fx):
        if c.get("kurs"):
            aus.setdefault(c["ticker"].upper(), float(c["kurs"]))
    return aus


def _instrumente(h, depot):
    """Kurse aus den Top-500-Daten (Kurs der Kandidaten), Kurs-IDs aus den Top-500-Listen - ohne Live-Suche."""
    return S.kurse_aus_top500(depot, S.top500_ids(_lies(h, "state/top50_ids.json"),
                                                   _lies(h, "state/top50_wikifolios.json")))


def _prognose_fuer(depot, e, erg):
    """Zielprognose fuer genau dieses Musterdepot (Monte-Carlo wie im Scanner) - wird mit ihm gespeichert und in
    der Musterdepot-Ansicht gezeigt. Keine Garantie: Modellwerte aus den Annahmen des Scanners."""
    try:
        mu, sigma = S.portfolio_kennzahlen(depot)
        start, cfs, rest = S.zahlungsplan(e, depot)
        a = S.auswerten(S.simulieren(mu, sigma, start, cfs, e["scan_kosten"], pfade=4000, seed=21),
                        e["zielvermoegen"], rest)
        ben = (erg.get("benoetigt") or {}).get("rendite") if e["zielvermoegen"] > 0 else None
        return {"ziel": e["zielvermoegen"], "monate": len(cfs), "einzahlung": e["einzahlung"],
                "entnahme": e["entnahme"], "erwartet": round(mu - e["scan_kosten"], 3), "schwankung": round(sigma, 2),
                "benoetigt": None if ben is None else round(ben, 3),
                "wahrscheinlichkeit": a["wahrscheinlichkeit"], "median": a["end"][50], "p10": a["end"][10],
                "p90": a["end"][90]}
    except Exception:
        return None


def _musterdepot_speichern(h, erg, e, depot=None, titel=None, profil=None, basis="modell"):
    """Nach jedem Scan: das Musterdepot mit genau den Prozentanteilen des gewaehlten Risikoprofils als NEUES
    Musterdepot ins Menue "📦 Musterdepot" schreiben (eigener Name je Scan, vorhandene bleiben unveraendert).
    Kurse aus den Top-500-Daten. -> Meldung (art, text)"""
    import planer_ui as PU
    depot = depot or erg.get("depot_profil") or erg["depot"]
    if not depot["positionen"]:
        return ("warnung", "Kein Musterdepot angelegt – das Depot ist leer.")
    auft = erg["aufteilung"]
    profil = profil or (f"{PROFIL_TITEL.get(e['scan_profil'], e['scan_profil'])}: "
                        + " / ".join(f"{ART_TITEL[k]} {_de(auft[k])} %" for k in ("etf", "aktie", "wikifolio", "cash")))
    heute = datetime.date.today()
    eintrag, ohne = S.musterdepot_eintrag(depot, erg["start"], _instrumente(h, depot), heute.isoformat(),
                                          profil=profil)
    if not eintrag["positionen"]:
        return ("warnung", "Kein Musterdepot angelegt – für keine Position gibt es einen Kurs in den Top-500-Daten.")
    titel = titel or PROFIL_TITEL.get(e["scan_profil"], e["scan_profil"])
    eintrag["prognose"] = _prognose_fuer(depot, e, erg)
    if eintrag["prognose"]:
        eintrag["prognose"]["basis"] = basis
    gespeichert = {}

    def _anlegen(d):
        if not isinstance(d.get("depots"), dict):
            d["depots"] = {}
        name = S.musterdepot_name(d["depots"], titel, heute.strftime("%d.%m.%Y"))   # nie ueberschreiben
        d["depots"][name] = dict(eintrag, name=name)
        d["aktiv"] = name
        gespeichert["name"] = name
        return d
    if not PU._aendern_speichern(h, PU._pfad(h, PU.PFAD_MUSTERDEPOT), _anlegen,
                                 "scanner: neues Musterdepot [skip ci]"):
        return ("fehler", "Musterdepot nicht gespeichert (Datenspeicher nicht erreichbar).")
    text = (f"Neues Musterdepot „{gespeichert.get('name')}“ angelegt ({profil}): {len(eintrag['positionen'])} "
            f"Positionen in ganzen Stücken zum Kurs aus den Top-500-Daten"
            + (f" ({erg['kurse_nachgeladen']} fehlende aktuell von ls-tc.de nachgeladen)" if erg.get("kurse_nachgeladen") else "")
            + f", Cash {_eur(eintrag['cash'], 2)}. "
            "Frühere Musterdepots bleiben erhalten.")
    if ohne:
        text += f" Ohne Kurs (bleibt Cash): {', '.join(ohne[:4])}" + (" …" if len(ohne) > 4 else "") + "."
    return ("ok", text)


def _top_investments(erg):
    n = st.select_slider("Anzahl je Anlageklasse", [10, 25, 50], value=10, key="pb_scan_top_n")
    im_depot = {(_kennung(p), p["name"]): p["gewicht"] for p in erg["depot"]["positionen"]}
    for art in ("etf", "aktie", "wikifolio"):
        liste = [c for c in erg["bewertet"] if c["art"] == art][:n]
        st.markdown(f"**{S.KLASSEN[art]}** · {erg['anzahl'][art]} bewertet")
        if not liste:
            st.caption("Keine Daten.")
            continue
        zeilen = []
        for i, c in enumerate(liste, 1):
            pr = c["prognose"]
            hist = f"{_pct(c['hist'], 1, True)} p. a. ({c['hist_jahre']:.0f} J.)" if c["hist"] is not None else "–"
            zeilen.append([f"{i}. <b>{_esc(c['name'])}</b>" + ("" if c["ausreichend"] else " <span class=gr>"
                                                                          "(zu wenig Daten)</span>"),
                           f"<b>{c['score']}</b>", f"{_pct(pr['pess'], 0, True)} … {_pct(pr['opt'], 0, True)}", hist,
                           S.risikostufe(pr["sigma"]),
                           _pct(im_depot.get((_kennung(c), c["name"]))) if (_kennung(c), c["name"]) in im_depot
                           else "–", _esc(_kennung(c)),
                           _esc(", ".join(c["chancen"]) or "–"), _esc(", ".join(c["risiken"]) or "–")])
        _tabelle_html(["Name", "Score", "Erwartet p. a. (10–90 %)", "Historisch", "Risiko", "Im Depot",
                       "ISIN / WKN / Ticker", "Chancen", "Risiken"], zeilen, rechts=(1, 2, 3, 5), text=(7, 8),
                      breit=True)
    st.caption("Score 0–100 je Anlageklasse (Rang innerhalb der Klasse). Erwartete Spanne: 10- bis 90-%-Bereich der "
               "durchschnittlichen Jahresrendite über deinen Anlagezeitraum – keine Garantie.")


def _prognose(erg, e):
    a, ziel = erg["auswertung"], e["zielvermoegen"]
    w = a["wahrscheinlichkeit"]
    dd_ok = a["dd95"] <= e["scan_max_dd"]
    score = None if w is None else int(round(w * 100 * (1.0 if dd_ok else 0.8)))
    jahre = erg["monate"] / 12.0
    real = a["end"][50] / (1 + e["scan_inflation"] / 100.0) ** jahre
    k = [("Benötigte Rendite p. a.", _pct(erg["benoetigt"]["rendite"], 2) if erg["benoetigt"] else "–",
          "für das Zielvermögen" if ziel > 0 else "kein Ziel eingetragen"),
         ("Erwartete Rendite p. a.", _pct(erg["mu"] - e["scan_kosten"], 2), f"nach {_pct(e['scan_kosten'])} Kosten · "
                                                                             f"Schwankung {_pct(erg['sigma'])}"),
         ("Erwartetes Endvermögen", _eur(a["end"][50]), f"Median, netto · real {_eur(real)}"),
         ("Zielwahrscheinlichkeit", _pct(w * 100 if w is not None else None, 0),
          f"Ziel {_eur(ziel)}" if ziel > 0 else "Zielvermögen oben eintragen"),
         ("Zielerreichungs-Score", "–" if score is None else f"{score}/100",
          "Wahrscheinlichkeit, abgewertet bei verletzter Verlusttoleranz"),
         ("Max. Rückgang (95 %)", _pct(-a["dd95"], 0), "eingehalten" if dd_ok else
          f"über deiner Toleranz von {_pct(e['scan_max_dd'], 0)}")]
    st.markdown('<div class="pb-scan-kpis">' + "".join(
        f'<div class="k"><div class="l">{_esc(l)}</div><div class="w">{_esc(v)}</div><div class="s">{_esc(s)}</div>'
        f'</div>' for l, v, s in k) + "</div>", unsafe_allow_html=True)
    _faecher(erg, ziel)
    szen = [("Pessimistisch (10 %)", a["end"][10]), ("Basis (Median)", a["end"][50]), ("Optimistisch (90 %)",
                                                                                         a["end"][90])]
    _tabelle_html(["Szenario", "Endvermögen netto", "Rendite p. a. (ca.)"],
                  [[s, _eur(v), _pct(_rendite_aus(erg, v + erg["restschuld"]), 1, True)] for s, v in szen],
                  rechts=(1, 2))
    zeilen = [[f"Jahr {m // 12}" if m % 12 == 0 else f"Monat {m}", _eur(v["p10"]), _eur(v["p50"]), _eur(v["p90"])]
              for v in erg["verlauf"] for m in [v["monat"]]]
    with st.expander("Depotentwicklung je Jahr"):
        _tabelle_html(["", "Pessimistisch (10 %)", "Median", "Optimistisch (90 %)"], zeilen, rechts=(1, 2, 3))
        st.caption("Depotwert vor Abzug eines Kredits; Sparraten und Kosten eingerechnet, monatliches Rebalancing.")
    if erg["optimierung"]:
        o = erg["optimierung"]
        st.markdown("**Optimierung: investierter Anteil gegen Cash**")
        _tabelle_html(["Investiert", "Erw. Rendite", "Zielwahrscheinlichkeit", "Max. Rückgang (95 %)", ""],
                      [[_pct(s["investiert"], 0), _pct(s["mu"], 1), _pct((s["wahrscheinlichkeit"] or 0) * 100, 0),
                        _pct(-s["dd95"], 0), "✓ gewählt" if s["anteil"] == o["beste"] else
                        ("über Toleranz" if s["dd95"] > e["scan_max_dd"] else "")] for s in o["stufen"]],
                      rechts=(0, 1, 2, 3))
        if not o["eingehalten"]:
            st.warning("Selbst mit dem geringsten getesteten Anteil liegt der mögliche Rückgang über deiner Toleranz – "
                       "gewählt ist die vorsichtigste Variante. Toleranz erhöhen oder mehr Cash/Anleihen einplanen.")
    alt = erg["alternativen"]
    if alt:
        tipps = []
        if alt.get("sparrate"):
            tipps.append(f"Sparrate auf etwa **{_eur(alt['sparrate'])}/Monat** erhöhen")
        if alt.get("jahre_mehr"):
            tipps.append(f"Anlagezeitraum um etwa **{alt['jahre_mehr']} Jahre** verlängern")
        tipps.append(f"Ziel auf etwa **{_eur(alt['erreichbar'])}** anpassen (Median)")
        st.warning("Das Ziel ist mit realistischen Annahmen eher unwahrscheinlich (unter 50 %). Die Renditeannahmen "
                   "werden dafür bewusst **nicht** erhöht. Für 50 % Wahrscheinlichkeit: " + " · oder ".join(tipps) + ".")


def _rendite_aus(erg, endwert):
    """Grobe Jahresrendite, die vom Start mit den Zahlungen auf endwert fuehrt (Bisektion)."""
    e = erg["eingaben"]
    lo, hi = -50.0, 60.0
    for _ in range(50):
        m = (lo + hi) / 2
        if P.simulation(e, rendite_pa=m)["endwert"] < endwert:
            lo = m
        else:
            hi = m
    return (lo + hi) / 2


def _faecher(erg, ziel):
    import plotly.graph_objects as go
    v = erg["verlauf"]
    heute = datetime.date.today()
    x = [heute.replace(day=1) + datetime.timedelta(days=round(z["monat"] * 30.44)) for z in v]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=[z["p90"] for z in v], mode="lines", line=dict(width=0), showlegend=False,
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=[z["p10"] for z in v], mode="lines", line=dict(width=0), fill="tonexty",
                             fillcolor="rgba(91,155,255,0.16)", name="10–90 % der Verläufe",
                             customdata=[f"{_eur(z['p10'])} – {_eur(z['p90'])}" for z in v],
                             hovertemplate="10–90 %: %{customdata}<extra></extra>"))
    fig.add_trace(go.Scatter(x=x, y=[z["p50"] for z in v], mode="lines", line=dict(color="#5B9BFF", width=2.6),
                             name="Median", customdata=[_eur(z["p50"]) for z in v],
                             hovertemplate="Median: %{customdata}<extra></extra>"))
    if ziel > 0:
        fig.add_hline(y=ziel + erg["restschuld"], line=dict(color="#F5B942", dash="dot", width=1.5),
                      annotation_text="Ziel", annotation_font_color="#F5B942")
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=300, separators=",.",
                      margin=dict(l=4, r=4, t=8, b=4), font=dict(color="#D6D9DE", size=12), hovermode="x unified",
                      legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0),
                      xaxis=dict(showgrid=False, tickformat="%Y"),
                      yaxis=dict(gridcolor="#1E2228", tickformat=",.0f", ticksuffix=" €", side="right"))
    st.plotly_chart(fig, width="stretch", key="pb_scan_faecher", config={"displayModeBar": False})


def _risiken(erg, kapital):
    d = erg["depot"]
    st.markdown("**Stresstest: sofortiger Rückgang des Depots**")
    _tabelle_html(["Szenario", "Rückgang", "In Euro (heute)"],
                  [[s["szenario"], _pct(s["prozent"], 1), _eur(s["euro"])] for s in S.stresstest(d, kapital)],
                  rechts=(1, 2))
    st.caption("Annahmen je Anlageklasse (Crash: Aktien −40 %, ETFs −35 %, wikifolios −40 %; Rezession −25/−20/−25 %; "
               "Inflation: realer Verlust im Jahr; enttäuschende Gewinne −20/−12/−15 %).")
    schwach = S.schwachstellen(d)
    if schwach:
        st.markdown("**Schwachstellen**\n\n" + "\n".join(f"- {s}" for s in schwach))
    st.markdown("**Grenzen der Vorhersage**\n\n"
                "- Korrelationen steigen in Krisen – Streuung schützt dann weniger als im Modell.\n"
                "- Vergangene Gewinner sind oft nicht die künftigen (Mean Reversion) – darum werden ihre Renditen "
                "begrenzt und zur langfristigen Erwartung hingezogen.\n"
                "- Die Ranglisten enthalten nur heute noch aktive Werte (Survivorship Bias).\n"
                "- Die Verlusttoleranz ist ein Planungswert, keine Garantie: reale Einbrüche können tiefer sein.")


def _plan(erg, e, positionen):
    d, kapital = erg["depot"], erg["start"]
    tranche = 3 if kapital < 50000 else 6
    st.markdown(
        "**Handlungsplan**\n\n"
        f"1. **Aufbau:** Startkapital in {tranche} gleichen Monatsraten investieren (glättet den Einstiegszeitpunkt), "
        "zuerst die ETFs, dann Einzelaktien, zuletzt wikifolios.\n"
        f"2. **Sparrate:** {_eur(e['einzahlung'])} im Monat nach den Zielgewichten verteilen – bevorzugt in Positionen, "
        "die unter ihrem Zielgewicht liegen (spart Verkäufe).\n"
        f"3. **Kontrolle:** vierteljährlich; Scanner neu rechnen lassen (die Daten werden täglich aktualisiert).\n"
        f"4. **Rebalancing:** wenn eine Position über {_pct(e['scan_max_gewicht'] + 1, 0)} steigt oder eine "
        "Anlageklasse mehr als 5 Prozentpunkte vom Ziel abweicht – sonst laufen lassen (Kosten, Steuern).\n"
        "5. **Austausch:** nur wenn ein Wert in zwei Prüfungen nacheinander deutlich (≥ 10 Punkte) schlechter "
        "abschneidet als der schwächste Wert im Musterdepot.\n"
        "6. **Steuern:** Gewinne sind beim Verkauf steuerpflichtig (in Deutschland Abgeltungsteuer plus "
        "Solidaritätszuschlag, ggf. Kirchensteuer; Freibetrag beachten) – in der Simulation **nicht** abgezogen.")
    if positionen:
        st.markdown("**Empfehlungen zu deinen aktuellen Positionen**")
        emp = S.empfehlungen(positionen, d, erg["bewertet"])
        _tabelle_html(["Position", "Empfehlung", "Ist", "Soll", "Score"],
                      [[_esc(x["name"]), f"<b>{_esc(x['aktion'])}</b>", _pct(x["ist"]), _pct(x["soll"]),
                        "–" if x["score"] is None else str(x["score"])] for x in emp], rechts=(2, 3, 4))


def _daten_annahmen(erg):
    st.markdown("**Datenstand**\n\n" + "\n".join(
        f"- {k}: {(v or 'nicht verfügbar')[:16].replace('T', ' ')}" for k, v in erg["stand"].items())
        + f"\n- Berechnet: {erg['zeit']}\n- Bewertet: {erg['anzahl']['aktie']} Aktien, {erg['anzahl']['etf']} ETFs, "
          f"{erg['anzahl']['wikifolio']} wikifolios")
    st.markdown("**Verwendet je Anlageklasse**\n\n"
                "- **Aktien:** Qualitäts-Score der Watchlist (Umsatz-, Gewinn- und Free-Cashflow-Wachstum, ROIC, "
                "Margen, Verschuldung, Forward-KGV, EV/EBIT, FCF-Rendite, Burggraben), Kursentwicklung 1–10 J.\n"
                "- **ETFs:** Kursentwicklung 1–10 J., Volatilität und maximaler Drawdown (soweit vorhanden). "
                "Hebel- und Short-Produkte ausgeschlossen, je Kernindex nur ein ETF.\n"
                "- **wikifolios:** Kursentwicklung, Volatilität, Drawdown, Länge der Historie; im Musterdepot "
                f"erst ab {S.ANNAHMEN['wikifolio_min_jahre']:.0f} Jahren Historie.")
    st.markdown("**Nicht in den Daten (deshalb nicht bewertet)**\n\n"
                "- ETFs: TER, Tracking Difference/Error, Fondsvolumen, Replikation, Länder-/Sektoraufteilung\n"
                "- wikifolios: Gebühren, Handelsstrategie, Trader, investiertes Kapital, Handelsaktivität\n"
                "- Aktien: Analystenprognosen\n- Korrelationen je Einzelwert (stattdessen Modellannahme je Klasse)")
    a = S.ANNAHMEN
    st.markdown("**Modellannahmen**\n\n"
                f"- Langfristige Erwartung p. a.: Aktien {a['erwartung']['aktie']:.1f} %, ETFs {a['erwartung']['etf']:.1f} %, "
                f"wikifolios {a['erwartung']['wikifolio']:.1f} %, Tagesgeld {a['tagesgeld']:.1f} %\n"
                f"- Historische Renditen werden auf ±{a['rendite_deckel']:.0f} % p. a. begrenzt; sie zählen je nach "
                f"Länge der Historie, höchstens zu {a['vorsprung_anteil'] * 50:.0f} % (bei 10 Jahren)\n"
                "- Aktien: zur Hälfte Fundamental-Erwartung = FCF-Rendite + ½ Umsatzwachstum (begrenzt)\n"
                f"- Schwankung ohne Messwert: Aktien {a['vola']['aktie']:.0f} %, ETFs {a['vola']['etf']:.0f} %, "
                f"wikifolios {a['vola']['wikifolio']:.0f} %\n"
                f"- Korrelation: Aktie–Aktie {a['korrelation'][('aktie', 'aktie')]}, ETF–ETF "
                f"{a['korrelation'][('etf', 'etf')]}, Aktie–ETF {a['korrelation'][('aktie', 'etf')]}, "
                f"wikifolio–wikifolio {a['korrelation'][('wikifolio', 'wikifolio')]}\n"
                "- 10.000 simulierte Verläufe, monatlich; Krisen-Regime (gebündelte Einbrüche) ohne Änderung von "
                "Durchschnittsrendite und Gesamtschwankung")
    st.caption("Keine Anlageberatung. Modellierte Wahrscheinlichkeiten sind keine garantierten Eintrittswahrscheinlichkeiten; "
               "vergangene Entwicklungen sind kein verlässlicher Indikator für die Zukunft.")


def _eckdaten(e):
    """Eigene Eckdaten des Scanners (unabhaengig vom Portfolio Builder)."""
    handy = _smartphone()
    c = (st.columns(2) + st.columns(2) + st.columns(2)) if handy else st.columns(5)
    c[0].number_input("Startkapital €", 0.0, P.MAX_KAPITAL, step=1000.0, format="%.0f", key="pb_scan_kapital")
    c[1].number_input("Einzahlung €/Monat", 0.0, P.MAX_MONATLICH, step=50.0, format="%.0f", key="pb_scan_einzahlung")
    c[2].number_input("Entnahme €/Monat", 0.0, P.MAX_MONATLICH, step=50.0, format="%.0f", key="pb_scan_entnahme")
    c[3].number_input("Laufzeit (Jahre)", 1, 50, step=1, key="pb_scan_laufzeit")
    c[4].number_input("Zielvermögen €", 0.0, P.MAX_KAPITAL, step=10000.0, format="%.0f", key="pb_scan_ziel",
                      help="0 = kein Ziel (dann keine Zielwahrscheinlichkeit und keine Alternativen).")
    st.caption("Diese Eckdaten gelten nur für den Scanner – der Portfolio Builder bleibt unverändert. Die Entnahme "
               "ist ein fester Betrag je Monat, verkauft wird anteilig nach dem Wert der Positionen.")
    if e["scan_ziel"] <= 0:
        st.info("Kein Zielvermögen gesetzt – ohne Ziel gibt es keine Zielwahrscheinlichkeit und keine Alternativen.")


def _e_plan(erg, e):
    return dict(e, anfangskapital=erg["eingaben"]["anfangskapital"],
                sonstiges_kapital=erg["eingaben"]["sonstiges_kapital"], kredit_summe=erg["eingaben"]["kredit_summe"])


def _entnahme_reiter(erg, e):
    """Verkaufsplan fuer das berechnete Musterdepot (live aus den aktuellen Verkaufsmengen)."""
    from portfolio_builder_ui import plan_anzeigen
    if e["entnahme"] <= 0:
        st.caption("Keine Entnahme eingetragen – oben in den Eckdaten bei „Entnahme €/Monat“ einen Betrag eintragen.")
        return
    plan_anzeigen(e, S.depot_entnahmeplan(erg["depot"], _e_plan(erg, e)), False)
    st.caption("Prognose, Zielwahrscheinlichkeit und Alternativen rechnen mit diesen Entnahmen. Nach einer Änderung „Neu berechnen“.")


def seite(h):
    """Eigene Ansicht: laedt die gespeicherten Builder-Eingaben, Scanner-Einstellungen werden mit ihnen gespeichert."""
    import portfolio_builder_ui as B
    st.markdown(B.CSS, unsafe_allow_html=True)
    st.markdown(CSS, unsafe_allow_html=True)
    B._start(h)
    e = B._aus_widgets()
    if e["scan_entnahme_art"] != "betrag":         # alte Einstellung "Stückzahlen" -> nur noch €-Betrag
        st.session_state["pb_scan_entnahme_art"] = "betrag"
        e = B._aus_widgets()
    if e["scan_kapital"] < 0:                     # erstes Oeffnen: einmal mit den Builder-Werten vorbelegen
        st.session_state.update(pb_scan_kapital=P.eigenkapital(e), pb_scan_einzahlung=e["einzahlung"],
                                pb_scan_laufzeit=max(round(P.monate(e) / 12), 1),
                                pb_scan_ziel=e["zielvermoegen"], pb_scan_entnahme=e["entnahme"])
        e = B._aus_widgets()
    st.markdown('<div class="pb-kopf"><div class="pb-titel">Investment-<span>Scanner</span></div>'
                '<div class="pb-unter">Aktien · ETFs · wikifolios → Musterdepot für dein Ziel</div></div>',
                unsafe_allow_html=True)
    with st.container(border=True, key="pb_scan_eckdaten"):
        st.markdown('<div class="pb-karte-t">Eckdaten</div>', unsafe_allow_html=True)
        _eckdaten(e)
    render(h, S.scanner_eingaben(e), lambda: B._katalog(h), (h or {}).get("zum_builder"))
    art, _ = B._automatisch_speichern(h, e)
    if art in ("lesefehler", "fehler"):
        st.caption("⚠ Einstellungen gerade nicht gespeichert – wird bei der nächsten Änderung erneut versucht.")


def render(h, e, katalog_fn, zum_builder=None):
    """Scanner-Karte. e = bereinigte Builder-Eingaben, katalog_fn() = Builder-Katalog."""
    with st.container(border=True, key="pb_scanner"):
        st.markdown('<div class="pb-karte-t">Risikoprofil & Regeln</div>', unsafe_allow_html=True)
        st.caption("Durchsucht Aktien (mit Fundamentaldaten), ETFs und wikifolios aus den Daten der Watchlist, bewertet "
                   "sie, stellt ein Musterdepot zusammen und simuliert dein Ziel mit den Eckdaten oben.")
        _einstellungen(e, katalog_fn)
        sig = _signatur(e)
        keine_favoriten = e["scan_profil"] == S.FAVORITEN and not e["scan_favoriten"]
        erg = st.session_state.get("pb_scan_erg")
        veraltet = erg is not None and st.session_state.get("pb_scan_sig") != sig
        if st.button("🔍 Scannen & Musterdepot berechnen" if erg is None else "🔄 Neu berechnen",
                     key="pb_scan_los", type="primary" if erg is None or veraltet else "secondary", width="stretch",
                     disabled=keine_favoriten):
            with st.spinner("Bewerte Aktien, ETFs und wikifolios und simuliere 10.000 Verläufe …"):
                erg = _berechnen(h, e, katalog_fn())
            st.session_state["pb_scan_erg"], st.session_state["pb_scan_sig"] = erg, sig
            with st.spinner("Lege das Investment Scanner Musterdepot an (Kurse von heute) …"):
                st.session_state["pb_scan_md"] = _musterdepot_speichern(h, erg, e)
                zd = erg.get("ziel_depot")
                st.session_state["pb_scan_md_ziel"] = _musterdepot_speichern(
                    h, erg, e, zd, "Zielrendite",
                    f"Zielrendite: renditestärkste Werte nach vergangener Rendite (Ø {_pct(zd['hist_rendite'], 1)} p. a.)",
                    "historisch") if zd and zd["positionen"] else None
            st.rerun()
            veraltet = False
        if erg is None:
            return
        if veraltet:
            st.info("Eingaben geändert – „Neu berechnen“, damit das Ergebnis dazu passt.")
        kapital = erg["start"]
        tabs = st.tabs(["📦 Musterdepot", "🏆 Top-Investments", "📈 Prognose", "💸 Entnahme", "⚠️ Risiken",
                        "🧭 Plan", "ℹ️ Daten"])
        with tabs[0]:
            _musterdepot(erg, kapital, zum_builder, (h or {}).get("zum_muster"))
        with tabs[1]:
            _top_investments(erg)
        with tabs[2]:
            _prognose(erg, erg["eingaben"])
        with tabs[3]:
            _entnahme_reiter(erg, e)
        with tabs[4]:
            _risiken(erg, kapital)
        with tabs[5]:
            _plan(erg, erg["eingaben"], e["positionen"])
        with tabs[6]:
            _daten_annahmen(erg)


CSS = """
<style>
.pb-scan-wrap { overflow-x:auto; margin:4px 0 10px; }
table.pb-scan { width:100%; border-collapse:separate; border-spacing:0; font-size:.84rem; }
table.pb-scan.breit { min-width:640px; }
table.pb-scan th { text-align:left; color:#9AA0A6; font-weight:700; font-size:.72rem; letter-spacing:.4px;
  text-transform:uppercase; padding:6px 8px; border-bottom:1px solid #262B33; vertical-align:bottom; }
table.pb-scan td { padding:6px 8px; border-bottom:1px solid #1A1E24; vertical-align:top; white-space:nowrap; }
table.pb-scan td.t { white-space:normal; min-width:180px; max-width:280px; }
table.pb-scan .n { position:sticky; left:0; background:#0A0B0D; z-index:1; max-width:220px; white-space:normal; }
table.pb-scan .r { text-align:right; white-space:nowrap; }
table.pb-scan .gr { color:#9AA0A6; font-weight:400; }
table.pb-scan.depot { table-layout:fixed; }
table.pb-scan.depot td, table.pb-scan.depot th { overflow:hidden; text-overflow:ellipsis; }
table.pb-scan.depot td.t, table.pb-scan.depot td.n { white-space:normal; max-width:none; min-width:0; }
table.pb-scan.depot tr.summe td { border-top:1px solid #3A3F47; }
.pb-scan-kpis { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:8px; margin:6px 0 10px; }
.pb-scan-kpis .k { border:1px solid #262B33; border-radius:10px; padding:10px 12px; background:#0F1115; }
.pb-scan-kpis .l { color:#9AA0A6; font-size:.72rem; text-transform:uppercase; letter-spacing:.4px; }
.pb-scan-kpis .w { font-size:1.25rem; font-weight:800; margin-top:2px; }
.pb-scan-kpis .s { color:#9AA0A6; font-size:.76rem; margin-top:2px; }
@media (max-width: 640px) { .pb-scan-kpis { grid-template-columns:repeat(2, minmax(0,1fr)); }
  table.pb-scan .n { max-width:150px; } table.pb-scan { font-size:.8rem; } }
</style>
"""
