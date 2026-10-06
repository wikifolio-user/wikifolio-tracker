"""Zinseszins- / Sparrechner (wie die klassischen Bank-Sparrechner) mit Permanentlink und PDF.

Rechenweise (deutsche Bankpraxis): Innerhalb einer Zinsperiode einfache (lineare)
Verzinsung je angefangenem Monat, am Periodenende Gutschrift (Zinseszins) oder Auszahlung.
Relativer Periodenzins = Zinssatz p.a. x Periodenlaenge / 12. Vorschuessig = Einzahlung am
Monatsanfang (der Monat zaehlt mit), nachschuessig = am Monatsende.
Optional: Dynamik (Erhoehung der Rate), Festlegungsfrist (danach keine Raten mehr, Kapital
verzinst sich weiter), Abgeltungsteuer mit Sparerpauschbetrag je Kalenderjahr.
Jede Groesse (Anfangskapital, Rate, Dynamik, Zinssatz, Laufzeit, Endkapital) kann berechnet werden.
"""
import datetime
import math

INTERVALLE = {1: "monatlich", 3: "vierteljährlich", 6: "halbjährlich", 12: "jährlich"}
ZIEL_FELDER = {"e": "Endkapital", "a": "Anfangskapital", "s": "Sparrate", "dy": "Dynamik", "z": "Zinssatz",
               "n": "Ansparzeit"}
STANDARD = {"a": 0.0, "s": 100.0, "si": 1, "ea": "v", "dy": 0.0, "dya": "j", "z": 5.0, "zp": 12, "ze": 1,
            "n": 10, "ne": "j", "f": 0, "fe": "j", "e": 0.0, "calc": "e", "st": 0.0, "fb": 1000.0, "am": ""}
ABGELTUNG = 26.375


# ===========================================================================
# Rechnung
# ===========================================================================
def _monate(wert, einheit):
    return int(round(float(wert))) * (12 if einheit == "j" else 1)


def rechne(p):
    """p: Parameter (siehe STANDARD). -> dict mit Endkapital, Summen, Jahrestabelle, Monatsverlauf."""
    k = float(p["a"])
    rate0 = float(p["s"])
    si = int(p["si"])
    zp = int(p["zp"])
    vorschuessig = p["ea"] == "v"
    zinseszins = bool(int(p["ze"]))
    n_spar = max(_monate(p["n"], p["ne"]), 0)
    n_ges = n_spar + max(_monate(p["f"], p["fe"]), 0)
    dyn = float(p["dy"]) / 100.0
    steuer = float(p.get("st") or 0.0) / 100.0
    freib = float(p.get("fb") or 0.0)

    i_m = float(p["z"]) / 100.0 / 12.0                     # linear je Monat innerhalb der Zinsperiode
    einzahlungen = k
    zinsen_ges = steuer_ges = ausgezahlt = 0.0
    periode_zins = 0.0                                      # in der laufenden Zinsperiode aufgelaufen
    verzinst = k                                            # Betrag, der in diesem Monat Zinsen bringt
    jahre, verlauf = [], [k]
    jz = {"ein": 0.0, "zins": 0.0, "steuer": 0.0}
    frei_rest = freib
    rate = rate0
    for m in range(1, n_ges + 1):
        einz = 0.0
        if m <= n_spar and (m - 1) % si == 0:
            if dyn:
                schritte = (m - 1) // 12 if p["dya"] == "j" else (m - 1) // si
                rate = rate0 * (1 + dyn) ** schritte
            einz = rate
            k += einz
            einzahlungen += einz
            jz["ein"] += einz
            if vorschuessig:
                verzinst += einz                            # zaehlt schon in diesem Monat
        periode_zins += verzinst * i_m
        if einz and not vorschuessig:
            verzinst += einz                                # erst ab dem naechsten Monat
        if m % zp == 0 or m == n_ges:                       # Zinsgutschrift am Periodenende / Laufzeitende
            z_ = periode_zins
            st_ = 0.0
            if steuer and z_ > 0:
                steuerbar = max(z_ - frei_rest, 0.0)
                frei_rest = max(frei_rest - z_, 0.0)
                st_ = steuerbar * steuer
            zinsen_ges += z_
            steuer_ges += st_
            jz["zins"] += z_
            jz["steuer"] += st_
            if zinseszins:
                k += z_ - st_
            else:
                ausgezahlt += z_ - st_
            verzinst = k
            periode_zins = 0.0
        verlauf.append(k)
        if m % 12 == 0 or m == n_ges:
            jahre.append({"jahr": (m - 1) // 12 + 1, "monat": m, "ein": jz["ein"], "zins": jz["zins"],
                          "steuer": jz["steuer"], "stand": k})
            jz = {"ein": 0.0, "zins": 0.0, "steuer": 0.0}
            frei_rest = freib
    return {"end": k, "einzahlungen": einzahlungen, "zinsen": zinsen_ges, "steuer": steuer_ges,
            "ausgezahlt": ausgezahlt, "jahre": jahre, "verlauf": verlauf, "monate": n_ges, "spar_monate": n_spar,
            "letzte_rate": rate}


def loese(p):
    """Berechnet die in p["calc"] gewaehlte Groesse so, dass das Endkapital p["e"] erreicht wird.
    -> (p mit eingesetztem Wert, Ergebnis, Hinweis)"""
    ziel = p["calc"]
    if ziel == "e":
        return p, rechne(p), ""
    soll = float(p["e"])
    q = dict(p)

    def end(wert, feld):
        q[feld] = wert
        return rechne(q)["end"]
    if ziel in ("a", "s"):
        f0, f1 = end(0.0, ziel), end(1.0, ziel)
        steigung = f1 - f0
        if steigung <= 0:
            return p, rechne(p), "Nicht berechenbar (z. B. keine Sparzeit für die Rate)."
        wert = (soll - f0) / steigung
        if wert < 0:
            q[ziel] = 0.0
            return q, rechne(q), "Das Endkapital wird schon ohne diesen Betrag erreicht."
        # Steuer macht es leicht nichtlinear -> kurz nachjustieren
        for _ in range(30):
            d = end(wert, ziel) - soll
            if abs(d) < 0.005:
                break
            wert -= d / steigung
        q[ziel] = math.ceil(wert * 100 - 1e-6) / 100       # auf den Cent aufrunden -> Ziel sicher erreicht
        return q, rechne(q), ""
    if ziel in ("z", "dy"):
        lo, hi = (-0.99 * 100, 100.0) if ziel == "z" else (-50.0, 100.0)
        if end(hi, ziel) < soll:
            q[ziel] = hi
            return q, rechne(q), f"Auch mit {hi:.0f} % nicht erreichbar."
        if end(lo, ziel) > soll:
            q[ziel] = lo
            return q, rechne(q), "Wird schon mit dem kleinsten Wert erreicht."
        for _ in range(100):
            mi = (lo + hi) / 2
            if end(mi, ziel) >= soll:
                hi = mi
            else:
                lo = mi
        q[ziel] = round(hi, 4)
        return q, rechne(q), ""
    if ziel == "n":
        q["ne"] = "m"
        for monate in range(0, 12 * 100 + 1):
            if end(monate, "n") >= soll:
                q["n"] = monate
                return q, rechne(q), ""
        return q, rechne(q), "In 100 Jahren nicht erreichbar."
    return p, rechne(p), ""


# ===========================================================================
# Permanentlink (URL-Parameter)
# ===========================================================================
def aus_url(qp):
    """URL-Parameter -> Parameter-dict (unbekannte/kaputte Werte -> Standard)."""
    p = dict(STANDARD)
    for k, std in STANDARD.items():
        if k in qp:
            roh = qp[k]
            try:
                p[k] = type(std)(float(roh)) if isinstance(std, (int, float)) and not isinstance(std, bool) else str(roh)
            except (TypeError, ValueError):
                pass
    if p["si"] not in INTERVALLE:
        p["si"] = 1
    if p["zp"] not in INTERVALLE:
        p["zp"] = 12
    if p["calc"] not in ZIEL_FELDER:
        p["calc"] = "e"
    return p


def in_url(p):
    """Nur Abweichungen vom Standard in den Link (kurz und lesbar)."""
    aus = {"ansicht": "zins"}
    for k, std in STANDARD.items():
        if k == "e" and p.get("calc", "e") == "e":
            continue                                   # Endkapital wird dann berechnet
        v = p.get(k, std)
        if v != std:
            aus[k] = (f"{v:g}" if isinstance(v, float) else str(v))
    return aus


# ===========================================================================
# Formatierung + PDF
# ===========================================================================
def _de(x, nk=2):
    if abs(x) < 0.5 * 10 ** -nk:
        x = 0.0
    return f"{x:,.{nk}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _laufzeit_text(monate):
    j, m = divmod(int(monate), 12)
    return (f"{j} Jahr{'e' if j != 1 else ''}" if j else "") + (" " if j and m else "") + \
           (f"{m} Monat{'e' if m != 1 else ''}" if m else "") or "keine"


def _jahr_label(z, p):
    if p.get("am"):
        try:
            j0, m0 = (int(x) for x in str(p["am"]).split("-")[:2])
            ende = datetime.date(j0 + (m0 - 1 + z["monat"] - 1) // 12, (m0 - 1 + z["monat"] - 1) % 12 + 1, 1)
            return ende.strftime("%m/%Y")
        except Exception:
            pass
    return str(z["jahr"])


def zeilen_kenndaten(p):
    zei = [["Anfangskapital", f"{_de(float(p['a']))} €"],
           ["Sparrate", f"{_de(float(p['s']))} € {INTERVALLE[int(p['si'])]}"],
           ["Einzahlungsart", "vorschüssig" if p["ea"] == "v" else "nachschüssig"],
           ["Dynamik", f"{_de(float(p['dy']), 3)} % " + ("jährlich" if p["dya"] == "j" else "je Sparintervall")
            if float(p["dy"]) else "keine"],
           ["Zinssatz", f"{_de(float(p['z']), 3)} % p.a."],
           ["Zinsperiode", INTERVALLE[int(p["zp"])]],
           ["Zinseszins", "ja, Zinsansammlung" if int(p["ze"]) else "nein, Zinsauszahlung"],
           ["Ansparzeit", _laufzeit_text(_monate(p["n"], p["ne"]))],
           ["Festlegungsfrist", _laufzeit_text(_monate(p["f"], p["fe"]))],
           ["Steuer", f"{_de(float(p['st']), 3)} % (Freibetrag {_de(float(p['fb']), 0)} €/Jahr)"
            if float(p.get("st") or 0) else "nicht berücksichtigt"]]
    if p.get("am"):
        zei.append(["Anfangsmonat", str(p["am"])])
    return zei


def pdf_bericht(p, r, hinweis="", link=""):
    from abfindung import _PDF, _kuerzen
    pdf = _PDF()
    pdf.fuss = "Zinseszinsrechner - Szenariorechnung ohne Gewähr"
    pdf.y -= 8
    pdf.text(pdf.RAND, pdf.y, "Zinseszins- / Sparrechner", 20, True, (0.08, 0.1, 0.16))
    pdf.y -= 16
    pdf.text(pdf.RAND, pdf.y, f"erstellt am {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}", 9,
             farbe=(0.4, 0.4, 0.4))
    pdf.y -= 12
    pdf.rechteck(pdf.RAND, pdf.y - 64, pdf.B - 2 * pdf.RAND, 64, (0.93, 0.96, 1.0))
    ziel = p["calc"]
    if ziel == "e":
        kopf = f"Endkapital: {_de(r['end'])} €"
    elif ziel == "n":
        kopf = f"Benötigte Ansparzeit: {_laufzeit_text(_monate(p['n'], p['ne']))}"
    elif ziel in ("z", "dy"):
        kopf = f"Benötigt{'er Zinssatz' if ziel == 'z' else 'e Dynamik'}: {_de(float(p[ziel]), 3)} %"
    else:
        kopf = f"Benötigt{'es Anfangskapital' if ziel == 'a' else 'e Sparrate'}: {_de(float(p[ziel]))} €"
    pdf.text(pdf.RAND + 10, pdf.y - 20, kopf, 14, True)
    pdf.text(pdf.RAND + 10, pdf.y - 38,
             f"Endkapital {_de(r['end'])} € · Einzahlungen {_de(r['einzahlungen'])} € · Zinsen {_de(r['zinsen'])} €"
             + (f" · Steuern {_de(r['steuer'])} €" if r["steuer"] else "")
             + (f" · ausgezahlt {_de(r['ausgezahlt'])} €" if r["ausgezahlt"] else ""), 9)
    if hinweis:
        pdf.text(pdf.RAND + 10, pdf.y - 54, hinweis, 8.5, farbe=(0.6, 0.2, 0.1))
    pdf.y -= 72
    pdf.ueberschrift("Kenndaten")
    pdf.tabelle(["Angabe", "Wert"], zeilen_kenndaten(p), [2, 2.4])
    pdf.ueberschrift("Entwicklung " + ("je Jahr" if not p.get("am") else "(Stand am Jahresende)"))
    pdf.tabelle(["Jahr", "Einzahlungen", "Zinsen", "Steuern", "Kontostand"],
                [[_jahr_label(z, p), f"{_de(z['ein'])} €", f"{_de(z['zins'])} €", f"{_de(z['steuer'])} €",
                  f"{_de(z['stand'])} €"] for z in r["jahre"]], [0.8, 1.2, 1.2, 1, 1.4], groesse=8)
    if link:
        pdf.y -= 6
        pdf.absatz("Permanentlink: " + link, 7.5, farbe=(0.2, 0.3, 0.6))
    pdf.absatz("Rechenweise: innerhalb der Zinsperiode lineare Verzinsung je Monat, Zinsgutschrift am Ende der "
               "Zinsperiode (Bankpraxis). Szenariorechnung ohne Gewähr.", 7.5)
    return pdf.bytes()


# ===========================================================================
# Oberflaeche
# ===========================================================================
def render(basis_url=""):
    import streamlit as st
    import pandas as pd

    # Erstaufruf: Werte aus dem Link uebernehmen (danach gelten die Eingaben)
    if not st.session_state.get("zr_init"):
        p0 = aus_url({k: st.query_params.get(k) for k in STANDARD if k in st.query_params})
        for k, v in p0.items():
            st.session_state[f"zr_{k}"] = v
        st.session_state["zr_init"] = True

    calc = st.selectbox("Was berechnen?", list(ZIEL_FELDER), format_func=ZIEL_FELDER.get, key="zr_calc")
    p = {"calc": calc}

    def zahl(feld, label, mini, maxi, step, fmt="%.2f", hilfe=None, spalte=st):
        if calc == feld:
            spalte.text_input(label, "wird berechnet", disabled=True, key=f"zr_dis_{feld}")
            return float(st.session_state.get(f"zr_{feld}", STANDARD[feld]))
        return float(spalte.number_input(label, mini, maxi, step=step, format=fmt, key=f"zr_{feld}", help=hilfe))

    c1, c2 = st.columns(2)
    p["a"] = zahl("a", "Anfangskapital (€)", 0.0, 1e10, 1000.0, spalte=c1)
    p["s"] = zahl("s", "Sparrate (€)", 0.0, 1e9, 25.0, spalte=c2)
    c3, c4 = st.columns(2)
    p["si"] = c3.selectbox("Sparintervall", list(INTERVALLE), format_func=INTERVALLE.get, key="zr_si")
    p["ea"] = c4.selectbox("Einzahlungsart", ["v", "n"], key="zr_ea",
                           format_func={"v": "vorschüssig (Anfang)", "n": "nachschüssig (Ende)"}.get)
    c5, c6 = st.columns(2)
    p["dy"] = zahl("dy", "Dynamik (%)", -50.0, 100.0, 0.5, "%.3f", "Erhöhung der Sparrate", spalte=c5)
    p["dya"] = c6.selectbox("Dynamik", ["j", "i"], key="zr_dya",
                            format_func={"j": "jährlich", "i": "je Sparintervall"}.get)
    c7, c8 = st.columns(2)
    p["z"] = zahl("z", "Zinssatz (% p.a.)", -99.0, 100.0, 0.25, "%.3f", spalte=c7)
    p["zp"] = c8.selectbox("Zinsperiode", list(INTERVALLE), format_func=INTERVALLE.get, key="zr_zp")
    p["ze"] = st.selectbox("Zinseszins", [1, 0], key="zr_ze",
                           format_func={1: "Ja, Zinsansammlung", 0: "Nein, Zinsauszahlung"}.get)
    c9, c10 = st.columns(2)
    if calc == "n":
        c9.text_input("Ansparzeit", "wird berechnet", disabled=True, key="zr_dis_n")
        p["n"], p["ne"] = st.session_state.get("zr_n", 10), st.session_state.get("zr_ne", "j")
    else:
        p["n"] = int(c9.number_input("Ansparzeit", 0, 1200, step=1, key="zr_n"))
        p["ne"] = c10.selectbox("Einheit", ["j", "m"], key="zr_ne", format_func={"j": "Jahre", "m": "Monate"}.get)
    c11, c12 = st.columns(2)
    p["f"] = int(c11.number_input("Festlegungsfrist", 0, 1200, step=1, key="zr_f",
                                  help="Nach der Ansparzeit: keine Raten mehr, das Kapital wird weiter verzinst"))
    p["fe"] = c12.selectbox("Einheit ", ["j", "m"], key="zr_fe", format_func={"j": "Jahre", "m": "Monate"}.get)
    if calc == "e":
        p["e"] = float(st.session_state.get("zr_e", 0.0))
    else:
        p["e"] = float(st.number_input("Endkapital (Ziel, €)", 0.0, 1e12, step=1000.0, format="%.2f", key="zr_e"))
    with st.expander("Steuer & Anfangsmonat", expanded=bool(float(st.session_state.get("zr_st") or 0)
                                                           or st.session_state.get("zr_am"))):
        c13, c14 = st.columns(2)
        p["st"] = float(c13.number_input("Steuersatz auf Zinsen (%)", 0.0, 60.0, step=0.5, format="%.3f", key="zr_st",
                                         help=f"Abgeltungsteuer + Soli = {ABGELTUNG} % (0 = nicht berücksichtigen)"))
        p["fb"] = float(c14.number_input("Freibetrag pro Jahr (€)", 0.0, 1e6, step=100.0, format="%.0f", key="zr_fb",
                                         help="Sparerpauschbetrag: 1.000 € (Ehepaare 2.000 €)"))
        am = st.text_input("Anfangsmonat (MM/JJJJ, für Tabelle und PDF)", st.session_state.get("zr_am_txt", "")
                           or (f"{str(st.session_state.get('zr_am'))[5:7]}/{str(st.session_state.get('zr_am'))[:4]}"
                               if st.session_state.get("zr_am") else ""), key="zr_am_txt")
        p["am"] = ""
        if am.strip():
            try:
                mm, jj = am.strip().split("/")
                p["am"] = f"{int(jj):04d}-{int(mm):02d}"
            except ValueError:
                st.caption("Format MM/JJJJ, z. B. 01/2027")
        st.session_state["zr_am"] = p["am"]

    q, r, hinweis = loese(p)
    # berechneten Wert merken (Anzeige + Link)
    if calc != "e":
        st.session_state[f"zr_{calc}"] = q[calc] if calc != "n" else q["n"]
        if calc == "n":
            st.session_state["zr_ne"] = "m"
    else:
        st.session_state["zr_e"] = round(r["end"], 2)     # Vorbelegung, falls danach etwas anderes berechnet wird

    st.markdown("##### Ergebnis")
    if calc == "e":
        st.metric("Endkapital inkl. Zinsen", f"{_de(r['end'])} €")
    elif calc == "n":
        st.metric("Benötigte Ansparzeit", _laufzeit_text(_monate(q["n"], q["ne"])))
    elif calc in ("z", "dy"):
        st.metric("Benötigter Zinssatz" if calc == "z" else "Benötigte Dynamik", f"{_de(float(q[calc]), 3)} %")
    else:
        st.metric("Benötigtes Anfangskapital" if calc == "a" else "Benötigte Sparrate", f"{_de(float(q[calc]))} €")
    if hinweis:
        st.warning(hinweis)
    k1, k2 = st.columns(2)
    k1.metric("Einzahlungen gesamt", f"{_de(r['einzahlungen'])} €")
    k2.metric("Zinsen gesamt", f"{_de(r['zinsen'])} €")
    if r["steuer"] or r["ausgezahlt"]:
        k3, k4 = st.columns(2)
        k3.metric("Steuern gesamt", f"{_de(r['steuer'])} €")
        k4.metric("Zinsen ausgezahlt", f"{_de(r['ausgezahlt'])} €")
    if calc != "e":
        st.caption(f"Endkapital damit: {_de(r['end'])} €")

    df = pd.DataFrame([{"Jahr": _jahr_label(z, q), "Einzahlungen": f"{_de(z['ein'])} €",
                        "Zinsen": f"{_de(z['zins'])} €", "Steuern": f"{_de(z['steuer'])} €",
                        "Kontostand": f"{_de(z['stand'])} €"} for z in r["jahre"]])
    if not r["steuer"]:
        df = df.drop(columns=["Steuern"])
    try:
        st.area_chart(pd.DataFrame({"Kontostand": r["verlauf"]},
                                   index=[i / 12 for i in range(len(r["verlauf"]))]), height=220)
    except Exception:
        pass
    with st.expander("📅 Entwicklung je Jahr", expanded=False):
        st.dataframe(df, hide_index=True, width="stretch")

    # Permanentlink: Browser-Adresse zeigt immer die aktuelle Variante
    params = in_url(q)
    try:
        st.query_params.from_dict(params)
    except Exception:
        pass
    from urllib.parse import urlencode
    link = (basis_url.rstrip("/") + "/?" if basis_url else "?") + urlencode(params)
    st.markdown("##### 🔗 Permanentlink zu dieser Variante")
    st.code(link, language=None)
    st.caption("Die Adresse im Browser ist jetzt genau dieser Link – als Lesezeichen speichern oder teilen; beim "
               "Öffnen erscheint der Rechner mit allen Werten.")
    st.download_button("📄 Ergebnis als PDF", data=pdf_bericht(q, r, hinweis, link),
                       file_name="Zinsrechner.pdf", mime="application/pdf", width="stretch", key="zr_pdf")
