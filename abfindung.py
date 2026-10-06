"""Abfindungsrechner (Deutschland, Steuerjahr 2026) - Szenariorechnung, keine Steuerberatung.

- Einkommensteuer nach § 32a EStG (Tarif 2026), Splittingtarif bei Zusammenveranlagung
- Fuenftelregelung nach § 34 EStG (seit 2025 nur noch ueber die Steuererklaerung,
  der Arbeitgeber zieht bei der Auszahlung die volle Lohnsteuer ab)
- Solidaritaetszuschlag mit Freigrenze und Milderungszone, Kirchensteuer optional
- Abfindungen sind sozialversicherungsfrei
Die Steuer auf die Abfindung = Steuer(mit Abfindung) - Steuer(ohne Abfindung).
"""
import math

# --- Tarif 2026 (§ 32a EStG) ---
GRUNDFREIBETRAG = 12348
ZONE2_ENDE = 17799
ZONE3_ENDE = 69878
ZONE4_ENDE = 277825
SOLI_FREIGRENZE = 20350          # Einzelveranlagung (Splitting: doppelt)
SOLI_SATZ = 0.055
SOLI_MILDERUNG = 0.119
STEUERJAHR = 2026


def est_tarif(zve):
    """Einkommensteuer (Grundtarif) fuer ein zu versteuerndes Einkommen, volle Euro."""
    x = math.floor(max(zve, 0.0))
    if x <= GRUNDFREIBETRAG:
        return 0.0
    if x <= ZONE2_ENDE:
        y = (x - GRUNDFREIBETRAG) / 10000.0
        return float(math.floor((914.51 * y + 1400.0) * y))
    if x <= ZONE3_ENDE:
        z = (x - ZONE2_ENDE) / 10000.0
        return float(math.floor((173.10 * z + 2397.0) * z + 1034.87))
    if x <= ZONE4_ENDE:
        return float(math.floor(0.42 * x - 11135.63))
    return float(math.floor(0.45 * x - 19470.38))


def est(zve, splitting=False):
    if splitting:
        return 2.0 * est_tarif(math.floor(max(zve, 0.0) / 2.0))
    return est_tarif(zve)


def est_fuenftel(zve_rest, abfindung, splitting=False):
    """Einkommensteuer mit Fuenftelregelung (§ 34 Abs. 1 EStG)."""
    if abfindung <= 0:
        return est(zve_rest, splitting)
    if zve_rest < 0:
        gesamt = zve_rest + abfindung
        return 5.0 * est(gesamt / 5.0, splitting) if gesamt > 0 else 0.0
    basis = est(zve_rest, splitting)
    return basis + 5.0 * (est(zve_rest + abfindung / 5.0, splitting) - basis)


def soli(est_betrag, splitting=False):
    frei = SOLI_FREIGRENZE * (2 if splitting else 1)
    if est_betrag <= frei:
        return 0.0
    return round(min(SOLI_SATZ * est_betrag, SOLI_MILDERUNG * (est_betrag - frei)), 2)


def steuern(est_betrag, splitting=False, kirche=0.0):
    s = soli(est_betrag, splitting)
    k = round(est_betrag * kirche, 2)
    return {"est": est_betrag, "soli": s, "kirche": k, "summe": est_betrag + s + k}


def abfindung_regel(monatsbrutto, jahre, faktor=0.5):
    """Faustformel: Faktor x Bruttomonatsgehalt x Jahre der Betriebszugehoerigkeit
    (§ 1a KSchG: 0,5; in Verhandlungen oft 0,5 bis 1,5)."""
    return max(float(monatsbrutto), 0.0) * max(float(jahre), 0.0) * max(float(faktor), 0.0)


def rechne(abfindung, zve_rest, splitting=False, kirche=0.0):
    """-> dict mit Steuern ohne/mit Fuenftelregelung auf die Abfindung, Netto, Saetze."""
    a = max(float(abfindung), 0.0)
    r = float(zve_rest)
    ohne_a = steuern(est(r, splitting), splitting, kirche)
    voll = steuern(est(r + a, splitting), splitting, kirche)
    fuenf = steuern(est_fuenftel(r, a, splitting), splitting, kirche)

    def teil(mit):
        d = {k: mit[k] - ohne_a[k] for k in ("est", "soli", "kirche", "summe")}
        d["netto"] = a - d["summe"]
        d["satz"] = d["summe"] / a if a else 0.0
        return d
    t_voll, t_fuenf = teil(voll), teil(fuenf)
    return {"abfindung": a, "zve_rest": r, "ohne": t_voll, "fuenftel": t_fuenf,
            "ersparnis": t_voll["summe"] - t_fuenf["summe"],
            "steuer_ohne_abfindung": ohne_a["summe"]}


# ===========================================================================
# Oberflaeche (Streamlit)
# ===========================================================================
def _de(x, nk=0):
    if abs(x) < 0.5 * 10 ** -nk:
        x = 0.0
    return f"{x:,.{nk}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(x):
    return _de(x * 100, 1) + " %"


def render():
    import streamlit as st
    import pandas as pd

    st.caption(f"Szenariorechnung für {STEUERJAHR} · keine Steuer- oder Rechtsberatung · Einkommensteuer nach "
               "§ 32a EStG, Fünftelregelung nach § 34 EStG, Soli und Kirchensteuer vereinfacht.")

    st.markdown("##### 1 · Höhe der Abfindung")
    c1, c2 = st.columns(2)
    monat = c1.number_input("Bruttomonatsgehalt (€)", 0.0, 1e6, 5000.0, step=100.0, format="%.0f", key="abf_monat")
    jahre = c2.number_input("Betriebszugehörigkeit (Jahre)", 0.0, 60.0, 10.0, step=0.5, key="abf_jahre")
    c3, c4 = st.columns(2)
    faktor = c3.number_input("Faktor (Monatsgehälter je Jahr)", 0.0, 5.0, 0.5, step=0.05, key="abf_faktor",
                             help="Gesetzliche Faustformel § 1a KSchG: 0,5. In Verhandlungen meist 0,5 bis 1,5 – "
                                  "höher bei guten Chancen im Kündigungsschutzprozess.")
    regel = abfindung_regel(monat, jahre, faktor)
    eigen = c4.number_input("Oder fester Betrag (€, 0 = Formel)", 0.0, 1e8, 0.0, step=1000.0, format="%.0f",
                            key="abf_eigen", help="Wenn du schon ein Angebot hast")
    abf = eigen if eigen > 0 else regel
    st.markdown(f'<div style="margin:2px 0 10px">Abfindung brutto: <b>{_de(abf)} €</b>'
                + ("" if eigen > 0 else f' <span style="color:#A1A1AA">({_de(faktor, 2)} × {_de(monat)} € × '
                                        f'{_de(jahre, 1)} J.)</span>') + "</div>", unsafe_allow_html=True)

    st.markdown("##### 2 · Steuerliche Situation im Auszahlungsjahr")
    c5, c6 = st.columns(2)
    zve = c5.number_input("Übriges zu versteuerndes Einkommen (€)", -1e6, 1e8, round(monat * 12 * 0.8, -2),
                          step=1000.0, format="%.0f", key="abf_zve",
                          help="Einkommen im Auszahlungsjahr OHNE Abfindung, nach Werbungskosten, Sonderausgaben "
                               "usw. (Faustwert: ca. 80 % des Jahresbruttos). Bei Zusammenveranlagung: beide "
                               "Partner zusammen.")
    veranl = c6.selectbox("Veranlagung", ["Einzeln", "Zusammen (Splitting)"], key="abf_veranl")
    c7, c8 = st.columns(2)
    kirche = {"keine": 0.0, "8 % (BY, BW)": 0.08, "9 % (übrige Länder)": 0.09}[
        c7.selectbox("Kirchensteuer", ["keine", "8 % (BY, BW)", "9 % (übrige Länder)"], key="abf_kirche")]
    zve2 = c8.number_input("Vergleich: Einkommen im Folgejahr (€)", -1e6, 1e8, 0.0, step=1000.0, format="%.0f",
                           key="abf_zve2",
                           help="Z. B. wenn die Abfindung erst im Januar ausgezahlt wird und du danach wenig "
                                "Einkommen hast. Achtung: Arbeitslosengeld ist steuerfrei, erhöht aber über den "
                                "Progressionsvorbehalt den Steuersatz – das ist hier nicht eingerechnet.")
    split = veranl.startswith("Zusammen")

    e = rechne(abf, zve, split, kirche)
    f_, o_ = e["fuenftel"], e["ohne"]

    st.markdown("##### 3 · Ergebnis")
    k1, k2 = st.columns(2)
    k1.metric("Netto mit Fünftelregelung", f"{_de(f_['netto'])} €", f"Steuern {_de(f_['summe'])} € · {_pct(f_['satz'])}",
              delta_color="off")
    k2.metric("Netto ohne Fünftelregelung", f"{_de(o_['netto'])} €", f"Steuern {_de(o_['summe'])} € · {_pct(o_['satz'])}",
              delta_color="off")
    k3, k4 = st.columns(2)
    k3.metric("Vorteil Fünftelregelung", f"{_de(e['ersparnis'])} €")
    k4.metric("Sozialabgaben", "0 €", "Abfindung ist SV-frei", delta_color="off")

    zeilen = [("Abfindung brutto", abf, abf),
              ("Einkommensteuer", -o_["est"], -f_["est"]),
              ("Solidaritätszuschlag", -o_["soli"], -f_["soli"]),
              ("Kirchensteuer", -o_["kirche"], -f_["kirche"]),
              ("Netto", o_["netto"], f_["netto"])]
    st.dataframe(pd.DataFrame([{"": z[0], "ohne Fünftel": f"{_de(z[1])} €", "mit Fünftel": f"{_de(z[2])} €"}
                               for z in zeilen]), hide_index=True, width="stretch")
    st.caption("Seit 2025 rechnet der Arbeitgeber die Fünftelregelung nicht mehr bei der Auszahlung ein: Zunächst "
               f"wird ungefähr die Steuer „ohne Fünftel“ einbehalten (≈ {_de(o_['summe'])} €), den Vorteil von "
               f"≈ {_de(e['ersparnis'])} € gibt es erst mit der Steuererklärung zurück. Werte gerechnet auf das "
               "zu versteuernde Einkommen (Näherung, Lohnsteuerabzug weicht ab).")

    st.markdown("##### 4 · Auszahlung im Folgejahr?")
    e2 = rechne(abf, zve2, split, kirche)
    diff = e2["fuenftel"]["netto"] - f_["netto"]
    st.markdown(f'Mit übrigem Einkommen von <b>{_de(zve2)} €</b> im Folgejahr: Netto <b>{_de(e2["fuenftel"]["netto"])} €</b> '
                f'(Steuern {_pct(e2["fuenftel"]["satz"])}) → '
                f'<b style="color:{"#16C784" if diff >= 0 else "#EA3943"}">{"+" if diff >= 0 else "−"}{_de(abs(diff))} €</b> '
                f'gegenüber Auszahlung in diesem Jahr.', unsafe_allow_html=True)

    st.markdown("##### 5 · Verhandlungsspielraum")
    tab = []
    for fk in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
        b = abfindung_regel(monat, jahre, fk)
        x = rechne(b, zve, split, kirche)["fuenftel"]
        tab.append({"Faktor": _de(fk, 2), "Brutto": f"{_de(b)} €", "Netto": f"{_de(x['netto'])} €",
                    "Steuersatz": _pct(x["satz"]), "Netto in Monatsgehältern": _de(x["netto"] / monat, 1) if monat else "–"})
    st.dataframe(pd.DataFrame(tab), hide_index=True, width="stretch")

    with st.expander("ℹ️ Gut zu wissen", expanded=False):
        st.markdown(
            "- **Fünftelregelung** gilt nur bei *Zusammenballung*: Die Abfindung muss in einem Jahr fließen und "
            "zusammen mit dem übrigen Einkommen höher sein als das, was ohne Kündigung verdient worden wäre.\n"
            "- **Arbeitslosengeld**: Bei einem Aufhebungsvertrag droht meist eine Sperrzeit (bis 12 Wochen); wird "
            "die Kündigungsfrist nicht eingehalten, ruht der Anspruch zusätzlich (Teil der Abfindung wird "
            "angerechnet).\n"
            "- **Steuer senken**: Auszahlung in ein Jahr mit wenig Einkommen legen, Einzahlung in die gesetzliche "
            "Rentenversicherung (Ausgleich von Rentenabschlägen) oder bAV mitverhandeln.\n"
            "- Rechnung ohne Kinderfreibeträge, Progressionsvorbehalt und Lohnsteuer-Details – für eine "
            "verbindliche Auskunft Steuerberater oder Lohnsteuerhilfeverein fragen.")
