"""Jahr-fuer-Jahr-Rechnung: Arbeit -> Altersteilzeit (Arbeits-/Freistellungsphase) -> ggf. ALG/Luecke -> Rente.

berechne(e, p, heute) rechnet eine Variante:
- "plan":  die eingegebene Planung (Altersteilzeit, vorzeitige Rente, Abfindung, ALG ...)
- "regel": Vergleich - Vollzeit bis zur Regelaltersgrenze, dann Regelaltersrente ohne Abschlag
Eingaben e: siehe STANDARD (JSON-faehig, so werden auch Szenarien gespeichert).
Alle Betraege nominal; "real" = in Kaufkraft von heute (Inflation aus den Eingaben).
"""
import copy
import datetime

from . import kapital as K
from . import rente as R
from . import steuer as S
from .parameter import kirchensteuer_satz

STEUERKLASSEN = ["I", "II", "III", "IV", "V"]
VERHEIRATET = {"III", "IV", "V"}
VERTRAG_ARTEN = ["Kapital-LV", "Private Rentenversicherung", "Riester", "Rürup (Basisrente)"]
AUSZAHLUNG = ["Kapital", "Rente"]
BAV_WEGE = {"dv": "Direktversicherung / Pensionskasse / Pensionsfonds",
            "dz": "Direktzusage / Unterstützungskasse"}
PARTNER_ARTEN = {"rente": "Gesetzliche Rente", "pension": "Pension (Beamte)", "lohn": "Arbeitslohn"}
RENTE_WAHL = {"abschlagsfrei": "Frühester Beginn ohne Abschlag", "frueh": "Frühestmöglich (ggf. mit Abschlag)",
              "wunsch": "Wunschtermin"}
RENTE_EINGABE = {"ep": "Entgeltpunkte", "anwartschaft": "Bisher erreichte Anwartschaft (€)",
                 "prognose": "Prognose Regelaltersrente (€)"}
ATZ_MODELLE = ["Blockmodell", "Gleichverteilungsmodell"]
ALTER_ENDE = 95

STANDARD = {
    # Person
    "geb_jahr": 1964, "geb_monat": 6, "geb_erster": False, "steuerklasse": "I", "kirche": False,
    "bundesland": "Nordrhein-Westfalen", "kinder": True, "schwerbehindert": False,
    "jahre_pflicht": 38.0, "jahre_kinder": 0.0, "jahre_pflege": 0.0, "jahre_ausbildung": 0.0, "jahre_alg": 0.0,
    "kv_art": "gesetzlich", "kvdr": True, "pkv_beitrag": 600.0, "pkv_rente": 600.0, "pkv_steigerung": 3.0,
    # Rente
    "rente_eingabe": "ep", "ep": 40.0, "anwartschaft": 1700.0, "prognose": 2200.0,
    "rente_wahl": "abschlagsfrei", "rente_jahr": 2029, "rente_monat": 1,
    "ausgleich": False, "ausgleich_betrag": 0.0,
    # Arbeit / Altersteilzeit
    "brutto_jahr": 60000.0, "lohnsteigerung": 2.0,
    "atz_an": True, "atz_jahr": 2027, "atz_monat": 1, "atz_auto": True, "atz_dauer": 48,
    "atz_modell": "Blockmodell", "atz_aufstockung": 20.0, "atz_rv": 80.0,
    "abfindung": 0.0, "abfindung_jahr": 2031, "fuenftel": True,
    "alg_an": False, "alg_monate": 24, "alg_sperrzeit": True, "alg_kind": False,
    # Betriebsrente
    "bav_betrag": 0.0, "bav_form": "Rente", "bav_weg": "dv", "bav_jahr": 2031, "bav_monat": 1,
    "bav_abschlag": 0.0, "bav_dynamik": 1.0, "bav_fuenftel": False,
    # Versicherungen: [{art, auszahlung, jahr, betrag, eingezahlt, vertragsbeginn}]
    "vertraege": [],
    # Kapital
    "kapital": 50000.0, "einstand": 50000.0, "sparrate": 300.0, "rendite": 5.0, "spanne": 2.0,
    "inflation": 2.0, "teilfreistellung": True, "entnahme_modus": "luecke", "entnahme_alter": 90,
    "entnahme_fest": 800.0, "pflegepuffer": 0.0,
    # Oft vergessen
    "miete": 0.0, "miete_steuer_pct": 100.0, "hinzuverdienst": 0.0, "hinzuverdienst_bis": 70,
    "partner_art": "rente", "partner_lohn": 0.0, "partner_rente": 0.0, "partner_jahr": 2030,
    "partner_kv": 0.0, "bedarf": 2600.0,
    "kredite": [],       # [{name, rate, bis_jahr}]
    "einmal": [],        # [{name, jahr, betrag}]
    "tarif_index": True,
}


def _zahl(x, standard=0.0):
    try:
        v = float(x)
        return v if v == v else standard
    except (TypeError, ValueError):
        return standard


def normalisieren(e):
    """Fehlende Schluessel mit Standard fuellen, Typen angleichen (gespeicherte Szenarien bleiben lesbar)."""
    aus = copy.deepcopy(STANDARD)
    for k, v in (e or {}).items():
        if k not in aus:
            continue
        s = STANDARD[k]
        if isinstance(s, bool):
            aus[k] = bool(v)
        elif isinstance(s, int):
            aus[k] = int(_zahl(v, s))
        elif isinstance(s, float):
            aus[k] = _zahl(v, s)
        elif isinstance(s, list):
            aus[k] = [dict(x) for x in (v or []) if isinstance(x, dict)]
        else:
            aus[k] = v if v is not None else s
    return aus


def heute_idx(datum=None):
    d = datum or datetime.date.today()
    return R.idx(d.year, d.month)


# ---------------------------------------------------------------------------
# Zeitachse: Phasen, Rentenbeginn, Entgeltpunkte
# ---------------------------------------------------------------------------
def _alg_monate(e):
    """(Sperrzeit-Monate, bezahlte Monate) - Sperrzeit 12 Wochen ~ 3 Monate, Anspruch -1/4 (§ 159 SGB III)."""
    if not e["alg_an"] or e["alg_monate"] <= 0:
        return 0, 0
    if e["alg_sperrzeit"]:
        return 3, int(round(e["alg_monate"] * 0.75))
    return 0, int(e["alg_monate"])


def _gehalt_monat(e, jahr):
    return e["brutto_jahr"] / 12.0 * (1 + e["lohnsteigerung"] / 100.0) ** max(jahr - 2026, 0)


def _ep_bis(e, p, von, bis, t):
    """Entgeltpunkte aus den Monaten [von, bis) gemaess Phasen t."""
    ep = 0.0
    for i in range(von, bis):
        j = i // 12
        ph = phase(t, i)
        g = _gehalt_monat(e, j)
        if ph == "arbeit":
            ep += R.ep_monat(g, p, j)
        elif ph in ("atz_arbeit", "atz_frei", "atz"):
            atz = g * 0.5
            bbg90 = 0.9 * p["bbg_rv"] * R.lohnfaktor(p, j) / 12.0
            zusatz = min(atz * t["atz_rv"] / 100.0, max(bbg90 - atz, 0.0))
            ep += R.ep_monat(atz + zusatz, p, j)
        elif ph == "alg":
            ep += R.ep_monat(t["alg_basis"] * p["alg_rv_basis"] / 100.0, p, j)
    return ep


def phase(t, i):
    if i >= t["rente"]:
        return "rente"
    if t["atz_start"] is not None and t["atz_start"] <= i < t["erwerb_ende"]:
        if t["modell"] == "Blockmodell":
            return "atz_arbeit" if i < t["atz_mitte"] else "atz_frei"
        return "atz"
    if i < t["erwerb_ende"]:
        return "arbeit"
    if t["alg_von"] <= i < t["alg_bis"]:
        return "alg"
    if t["erwerb_ende"] <= i < t["alg_von"]:
        return "sperrzeit"
    return "luecke"


PHASEN_NAMEN = {"arbeit": "Arbeit", "atz_arbeit": "ATZ-Arbeitsphase", "atz_frei": "ATZ-Freistellung",
                "atz": "Altersteilzeit", "alg": "Arbeitslosengeld", "sperrzeit": "Sperrzeit",
                "luecke": "Ohne Einkommen", "rente": "Rente"}


def _jahre_bei(e, t, i, j35_0, j45_0, h):
    """Wartezeiten (35/45) zum Monat i: bisherige + Beschaeftigung/ATZ ab heute + ALG (45 J.: ohne ALG in den
    letzten 2 Jahren vor Rentenbeginn, § 51 Abs. 3a)."""
    arbeit = max(min(i, t["erwerb_ende"]) - h, 0)
    alg_m = max(min(i, t["alg_bis"]) - t["alg_von"], 0)
    alg45 = max(min(i - 24, t["alg_bis"]) - t["alg_von"], 0)
    return j35_0 + (arbeit + alg_m) / 12.0, j45_0 + (arbeit + alg45) / 12.0


def zeitachse(e, p, h, variante="plan"):
    """Phasen und Rentenbeginn. -> dict mit Monatsindizes, Rentenart, Abschlag, Warnungen."""
    jg = e["geb_jahr"]
    g = R.grenzen(jg)
    regel_idx = R.beginn_idx(jg, e["geb_monat"], g["regel"][0], e["geb_erster"])
    j35_0, j45_0 = R.wartezeit_jahre({"pflicht": e["jahre_pflicht"], "kinder": e["jahre_kinder"],
                                      "pflege": e["jahre_pflege"], "ausbildung": e["jahre_ausbildung"],
                                      "alg": e["jahre_alg"]})
    warn = []
    t = {"regel_idx": regel_idx, "atz_start": None, "atz_mitte": None, "modell": e["atz_modell"],
         "atz_rv": e["atz_rv"], "alg_von": 0, "alg_bis": 0, "alg_basis": 0.0, "variante": variante}
    if variante == "regel":
        start = max(regel_idx, h + 1)
        t.update(erwerb_ende=start, rente=start, alg_von=start, alg_bis=start)
        j35, j45 = _jahre_bei(e, t, start, j35_0, j45_0, h)
        t.update(art="regel" if j35 >= 5 else None, abschlag=0.0, jahre35=j35, jahre45=j45)
        if j35 < 5:
            warn.append("Die allgemeine Wartezeit von 5 Jahren ist nicht erfüllt – keine Regelaltersrente.")
        t["warnungen"] = warn
        return t

    sperr, bezahlt = _alg_monate(e)
    brucke = sperr + bezahlt
    atz_start = R.idx(e["atz_jahr"], e["atz_monat"]) if e["atz_an"] else None
    if atz_start is not None and atz_start <= h:
        atz_start = h + 1
    manuelles_ende = (atz_start + max(int(e["atz_dauer"]), 0)) if (e["atz_an"] and not e["atz_auto"]) else None

    def setze(erwerb_ende, rente_i):
        t.update(erwerb_ende=erwerb_ende, rente=rente_i, alg_von=erwerb_ende + sperr,
                 alg_bis=erwerb_ende + sperr + bezahlt)

    if e["rente_wahl"] == "wunsch":
        r = max(R.idx(e["rente_jahr"], e["rente_monat"]), h + 1)
        ende = manuelles_ende if manuelles_ende is not None else max(r - brucke, h + 1)
        setze(min(ende, r), r)
    else:
        r = None
        untergrenze = (manuelles_ende + brucke) if manuelles_ende is not None else h + 1
        for i in range(max(untergrenze, h + 1), max(regel_idx, untergrenze) + 1):
            ende = manuelles_ende if manuelles_ende is not None else max(i - brucke, h + 1)
            setze(min(ende, i), i)
            j35, j45 = _jahre_bei(e, t, i, j35_0, j45_0, h)
            arten = R.moegliche_arten(jg, e["schwerbehindert"], j35, j45)
            alter = R.lebensalter(jg, e["geb_monat"], i, e["geb_erster"])
            art, a = R.beste_art(jg, alter, arten, p)
            if art and (e["rente_wahl"] != "abschlagsfrei" or a <= 1e-12):
                r = i
                break
        if r is None:
            r = max(regel_idx, untergrenze)
            ende = manuelles_ende if manuelles_ende is not None else max(r - brucke, h + 1)
            setze(min(ende, r), r)

    j35, j45 = _jahre_bei(e, t, t["rente"], j35_0, j45_0, h)
    arten = R.moegliche_arten(jg, e["schwerbehindert"], j35, j45)
    alter = R.lebensalter(jg, e["geb_monat"], t["rente"], e["geb_erster"])
    art, a = R.beste_art(jg, alter, arten, p)
    if art is None:
        warn.append("Zum gewählten Rentenbeginn ist keine Altersrente möglich (Alter oder Wartezeit nicht erreicht). "
                    "Gerechnet wird ab der Regelaltersgrenze.")
        t["rente"] = max(regel_idx, t["rente"])
        alter = R.lebensalter(jg, e["geb_monat"], t["rente"], e["geb_erster"])
        j35, j45 = _jahre_bei(e, t, t["rente"], j35_0, j45_0, h)
        art, a = R.beste_art(jg, alter, R.moegliche_arten(jg, e["schwerbehindert"], j35, j45) or ["regel"], p)
        art, a = art or "regel", a or 0.0
    t.update(art=art, abschlag=a, jahre35=j35, jahre45=j45)

    if atz_start is not None:
        if t["erwerb_ende"] - atz_start <= 0:
            warn.append("Die Altersteilzeit hätte keine Dauer (Beginn liegt nach dem Ende der Beschäftigung) – "
                        "ohne Altersteilzeit gerechnet.")
        else:
            t["atz_start"] = atz_start
            t["atz_mitte"] = atz_start + (t["erwerb_ende"] - atz_start + 1) // 2
            alter_atz = R.lebensalter(jg, e["geb_monat"], atz_start, e["geb_erster"])
            if alter_atz < 55 * 12:
                warn.append(f"Altersteilzeit nach dem AltTZG ist erst ab 55 möglich (bei Beginn: {R.alter_text(alter_atz)}).")
            if t["erwerb_ende"] < t["rente"] and not e["alg_an"]:
                warn.append("Zwischen Ende der Altersteilzeit und Rentenbeginn liegt eine Lücke ohne Einkommen "
                            "(Krankenversicherung freiwillig weiterzahlen!).")
    if e["alg_an"]:
        t["alg_basis"] = min(_gehalt_monat(e, t["erwerb_ende"] // 12), p["bbg_rv"] * R.lohnfaktor(p, t["erwerb_ende"] // 12) / 12)
        if t["alg_bis"] < t["rente"]:
            warn.append("Nach dem Arbeitslosengeld bleibt eine Lücke bis zum Rentenbeginn.")
    t["warnungen"] = warn
    return t


def ep_heute(e, p, h):
    """Entgeltpunkte heute je nach Eingabeart."""
    if e["rente_eingabe"] == "anwartschaft":
        return max(e["anwartschaft"], 0.0) / R.rentenwert(p, h)
    if e["rente_eingabe"] == "prognose":
        # Renteninformation: Hochrechnung mit gleichbleibenden Beitraegen bis zur Regelaltersgrenze
        regel_idx = R.beginn_idx(e["geb_jahr"], e["geb_monat"], R.regelaltersgrenze(e["geb_jahr"]), e["geb_erster"])
        je_monat = R.ep_monat(e["brutto_jahr"] / 12.0, p, 2026)
        return max(e["prognose"] / R.rentenwert(p, h) - je_monat * max(regel_idx - h, 0), 0.0)
    return max(e["ep"], 0.0)


# ---------------------------------------------------------------------------
# Jahresrechnung
# ---------------------------------------------------------------------------
def berechne(e, p, heute=None, variante="plan", rendite=None):
    e = normalisieren(e)
    h = heute_idx(heute)
    jg, gm, erster = e["geb_jahr"], e["geb_monat"], e["geb_erster"]
    t = zeitachse(e, p, h, variante)
    plan = variante == "plan"
    split = e["steuerklasse"] in VERHEIRATET
    kist = kirchensteuer_satz(p, e["bundesland"], e["kirche"])
    sachsen = e["bundesland"] == "Sachsen"
    gesetzlich = e["kv_art"] == "gesetzlich"
    infl = e["inflation"] / 100.0
    r_pa = (e["rendite"] if rendite is None else rendite) / 100.0
    tf = p["teilfreistellung"] / 100.0 if e["teilfreistellung"] else 0.0
    abg = S.abgeltung_satz(p, kist)
    pv_kl = 0.0 if e["kinder"] else p["pv_kinderlos"] / 100.0

    # Entgeltpunkte und Rente
    ep0 = ep_heute(e, p, h)
    ep_neu = _ep_bis(e, p, h, t["rente"], t)
    ep_summe = ep0 + ep_neu
    zf = 1.0 - t["abschlag"]
    ausgleich = {"kosten": 0.0, "ep": 0.0, "jahr": None, "break_even": None}
    if plan and e["ausgleich"] and t["abschlag"] > 0:
        z_jahr = max(t["rente"] // 12 - 1, h // 12)
        voll = R.ausgleichszahlung(ep_summe, t["abschlag"], p, z_jahr)
        kosten = voll["kosten"] if e["ausgleich_betrag"] <= 0 else min(e["ausgleich_betrag"], voll["kosten"])
        ep_x = R.ep_aus_beitrag(kosten, p, z_jahr)
        mehr = ep_x * zf * R.rentenwert(p, t["rente"])
        bem = R.break_even_monate(kosten, mehr, p["rentenanpassung"])
        alter_rente = R.lebensalter(jg, gm, t["rente"], erster)
        ausgleich = {"kosten": kosten, "voll": voll["kosten"], "ep": ep_x, "jahr": z_jahr, "mehr_rente": mehr,
                     "break_even": None if bem is None else alter_rente + bem}
        ep_summe += ep_x

    def rente_monat(i):
        return ep_summe * zf * R.rentenwert(p, i) if i >= t["rente"] else 0.0

    rente_start_jahr = t["rente"] // 12
    voll_jahr = rente_start_jahr + 1
    rentenfreibetrag = (1 - S.besteuerungsanteil(rente_start_jahr)) * sum(
        rente_monat(R.idx(voll_jahr, m)) for m in range(1, 13))

    sperr, _ = _alg_monate(e) if plan else (0, 0)
    alg_monat = (S.alg_schaetzung(t["alg_basis"], p, split, e["alg_kind"], R.lohnfaktor(p, t["erwerb_ende"] // 12))
                 if plan and e["alg_an"] else 0.0)

    # Betriebsrente
    bav_start = R.idx(e["bav_jahr"], e["bav_monat"])
    bav_vfb = None
    if e["bav_weg"] == "dz" and e["bav_betrag"] > 0:
        pct, hoechst, zuschlag = S.versorgungsfreibetrag(e["bav_jahr"])
        basis = e["bav_betrag"] * (1 - e["bav_abschlag"] / 100.0) * (12 if e["bav_form"] == "Rente" else 1)
        bav_vfb = min(pct * basis, hoechst) + zuschlag

    def bav_monat(i):
        if e["bav_form"] != "Rente" or e["bav_betrag"] <= 0 or i < bav_start:
            return 0.0
        return e["bav_betrag"] * (1 - e["bav_abschlag"] / 100.0) * (1 + e["bav_dynamik"] / 100.0) ** ((i - bav_start) // 12)

    bav_kapital = e["bav_betrag"] * (1 - e["bav_abschlag"] / 100.0) if e["bav_form"] == "Kapital" else 0.0

    vertraege = [v for v in e["vertraege"] if _zahl(v.get("betrag")) > 0]

    def vertrag_rente(v, jahr):
        if v.get("auszahlung") != "Rente" and v.get("art") != "Rürup (Basisrente)":
            return 0.0
        return _zahl(v.get("betrag")) * 12 if jahr >= int(_zahl(v.get("jahr"), 9999)) else 0.0

    kredite = [k for k in e["kredite"] if _zahl(k.get("rate")) > 0]
    einmal = [x for x in e["einmal"] if _zahl(x.get("betrag")) > 0]
    pkv_lf = 1 + e["pkv_steigerung"] / 100.0

    zeilen = []
    kap = max(e["kapital"], 0.0)
    einstand = min(max(e["einstand"], 0.0), kap) if kap > 0 else 0.0
    alter_x = e["entnahme_alter"]
    verzehr_w = None
    leer_ab = None
    ende_jahr = jg + ALTER_ENDE
    for jahr in range(h // 12, ende_jahr + 1):
        von = max(h, R.idx(jahr, 1))
        monate = list(range(von, R.idx(jahr + 1, 1)))
        n = len(monate)
        lf = R.lohnfaktor(p, jahr)
        ff = (1 + infl) ** max(jahr - 2026, 0)
        fak = ff if e["tarif_index"] else 1.0
        alter_ende = jahr - jg
        s = dict.fromkeys(("lohn", "atz", "aufst", "alg", "rente", "bav", "vers", "miete", "hinzu", "hinzu_mini",
                           "partner", "sv", "sv_partner", "vorsorge", "rv_an", "bav_kv_basis"), 0.0)
        post_monate = 0
        post_brutto = 0.0
        post_sv = 0.0
        phasen = []
        priv_renten_jahr = sum(vertrag_rente(v, jahr) for v in vertraege) / 12.0
        for i in monate:
            ph = phase(t, i)
            if ph not in phasen:
                phasen.append(ph)
            gm_ = _gehalt_monat(e, jahr)
            brutto = {"lohn": 0.0, "atz": 0.0, "aufst": 0.0, "alg": 0.0, "rente": rente_monat(i), "bav": bav_monat(i),
                      "vers": priv_renten_jahr, "miete": e["miete"] * ff, "hinzu": 0.0, "partner": 0.0}
            if ph == "arbeit":
                brutto["lohn"] = gm_
            elif ph in ("atz", "atz_arbeit", "atz_frei"):
                brutto["atz"] = gm_ * 0.5
                brutto["aufst"] = gm_ * 0.5 * e["atz_aufstockung"] / 100.0
            elif ph == "alg":
                brutto["alg"] = alg_monat
            alter_m = R.lebensalter(jg, gm, i, erster)
            if ph == "rente" and alter_m < e["hinzuverdienst_bis"] * 12 and e["hinzuverdienst"] > 0:
                brutto["hinzu"] = e["hinzuverdienst"] * ff
            if split:
                if i >= R.idx(e["partner_jahr"], 1):
                    brutto["partner"] = e["partner_rente"] * (1 + p["rentenanpassung"] / 100.0) ** max(jahr - e["partner_jahr"], 0)
                else:
                    brutto["partner"] = e["partner_lohn"] * (1 + e["lohnsteigerung"] / 100.0) ** max(jahr - 2026, 0)
            # KV-Basis Versorgungsbezuege: Kapital-bAV 10 Jahre lang mit 1/120 je Monat (§ 229 Abs. 1 S. 3 SGB V)
            bav_kv = brutto["bav"] + (bav_kapital / 120.0 if bav_kapital and bav_start <= i < bav_start + 120 else 0.0)
            # Sozialversicherung (eigene)
            sv = 0.0
            vorsorge = 0.0
            pkv = e["pkv_beitrag"] * pkv_lf ** max(jahr - 2026, 0)
            if ph in ("arbeit", "atz", "atz_arbeit", "atz_frei"):
                a = S.sv_arbeitnehmer(brutto["lohn"] + brutto["atz"], p, e["kinder"], sachsen, not gesetzlich, pkv,
                                      jahr, lf)
                sv, vorsorge = a["summe"], a["vorsorge"]
                s["rv_an"] += a["rv"]
            elif ph == "alg":
                sv = 0.0                     # Agentur fuer Arbeit zahlt KV/PV/RV
            elif ph in ("sperrzeit", "luecke"):
                if gesetzlich:
                    basis = max(min(brutto["miete"] + brutto["bav"] + priv_renten_jahr + kap * max(r_pa, 0) / 12.0,
                                    p["bbg_kv"] * lf / 12.0), p["kv_mindest"] * lf)
                    sv = basis * ((p["kv_satz_erm"] + p["kv_zusatz"]) / 100.0 + p["pv_satz"] / 100.0 + pv_kl)
                else:
                    sv = pkv
                vorsorge = sv
            else:  # Rente
                pkv_r = e["pkv_rente"] * pkv_lf ** max(jahr - 2026, 0)
                if gesetzlich and e["kvdr"]:
                    sv = brutto["rente"] * ((p["kv_satz"] + p["kv_zusatz"]) / 200.0 + p["pv_satz"] / 100.0 + pv_kl)
                    fb = p["bav_freibetrag"] * lf
                    sv += max(bav_kv - fb, 0.0) * (p["kv_satz"] + p["kv_zusatz"]) / 100.0
                    if bav_kv > fb:
                        sv += bav_kv * (p["pv_satz"] / 100.0 + pv_kl)
                elif gesetzlich:
                    basis = (brutto["rente"] + bav_kv + priv_renten_jahr + brutto["miete"]
                             + kap * max(r_pa, 0) / 12.0)
                    basis = max(min(basis, p["bbg_kv"] * lf / 12.0), p["kv_mindest"] * lf)
                    sv = basis * ((p["kv_satz_erm"] + p["kv_zusatz"]) / 100.0 + p["pv_satz"] / 100.0 + pv_kl)
                    sv -= brutto["rente"] * (p["kv_satz"] + p["kv_zusatz"]) / 200.0     # Zuschuss der DRV
                else:
                    sv = pkv_r - min(pkv_r / 2.0, brutto["rente"] * (p["kv_satz"] + p["kv_zusatz"]) / 200.0)
                vorsorge = sv
                if brutto["hinzu"] > p["minijob_grenze"]:
                    sv += brutto["hinzu"] * p["sv_hinzuverdienst"] / 100.0
                    vorsorge += brutto["hinzu"] * p["sv_hinzuverdienst"] / 100.0
            # Partner-Sozialversicherung
            svp = 0.0
            if brutto["partner"] > 0:
                if i >= R.idx(e["partner_jahr"], 1):
                    if e["partner_art"] == "rente":
                        svp = brutto["partner"] * ((p["kv_satz"] + p["kv_zusatz"]) / 200.0 + p["pv_satz"] / 100.0)
                    else:
                        svp = e["partner_kv"] * ff
                else:
                    svp = S.sv_arbeitnehmer(brutto["partner"], p, True, sachsen, jahr=jahr, lohnfaktor=lf)["summe"]
            for k, v in brutto.items():
                s[k] += v
            if brutto["hinzu"] and brutto["hinzu"] <= p["minijob_grenze"]:
                s["hinzu_mini"] += brutto["hinzu"]
            s["sv"] += sv
            s["sv_partner"] += svp
            s["vorsorge"] += vorsorge + svp
            m_brutto = sum(brutto.values())
            if i >= t["erwerb_ende"]:
                post_monate += 1
                post_brutto += m_brutto
                post_sv += sv + svp

        # Einmalzahlungen dieses Jahres (Kapital, Abfindung)
        ao = 0.0            # Fuenftelregelung
        zve_einmal = 0.0    # voll progressiv
        abg_einmal = 0.0    # Abgeltungsteuer-Bemessung
        einmal_brutto = 0.0
        if plan and e["abfindung"] > 0 and jahr == e["abfindung_jahr"]:
            einmal_brutto += e["abfindung"]
            if e["fuenftel"]:
                ao += e["abfindung"]
            else:
                zve_einmal += e["abfindung"]
        if bav_kapital > 0 and jahr == e["bav_jahr"]:
            einmal_brutto += bav_kapital
            stpfl = bav_kapital - (bav_vfb or 0.0)
            if e["bav_fuenftel"]:
                ao += max(stpfl, 0.0)
            else:
                zve_einmal += max(stpfl, 0.0)
        for v in vertraege:
            if v.get("auszahlung") != "Kapital" or v.get("art") == "Rürup (Basisrente)":
                continue
            if int(_zahl(v.get("jahr"), 0)) != jahr:
                continue
            betrag = _zahl(v.get("betrag"))
            einmal_brutto += betrag
            if v.get("art") == "Riester":
                zve_einmal += betrag
            else:
                ertrag = max(betrag - _zahl(v.get("eingezahlt")), 0.0)
                regel = S.halbeinkuenfte(int(_zahl(v.get("vertragsbeginn"), 2010)), jahr, jahr - jg)
                if regel == "halb":
                    zve_einmal += ertrag / 2.0
                elif regel == "voll":
                    abg_einmal += ertrag

        # Einkuenfte fuer die Einkommensteuer
        lohn_stpfl = s["lohn"] + s["atz"] + max(s["hinzu"] - s["hinzu_mini"], 0.0)
        eink_lohn = max(lohn_stpfl - (min(p["wk_arbeitnehmer"], lohn_stpfl) if lohn_stpfl > 0 else 0.0), 0.0)
        bav_jahr_brutto = s["bav"]
        if e["bav_weg"] == "dz":
            versorg = max(bav_jahr_brutto - (bav_vfb or 0.0) * (n / 12.0) - (p["wk_rente"] if bav_jahr_brutto else 0.0), 0.0)
            sonst22 = 0.0
        else:
            versorg = 0.0
            sonst22 = bav_jahr_brutto
        rente_stpfl = 0.0
        if s["rente"] > 0:
            rente_stpfl = s["rente"] - (rentenfreibetrag if jahr > rente_start_jahr else
                                        (1 - S.besteuerungsanteil(rente_start_jahr)) * s["rente"])
        for v in vertraege:
            r = vertrag_rente(v, jahr) * n / 12.0
            if not r:
                continue
            art = v.get("art")
            if art == "Riester":
                sonst22 += r
            elif art == "Rürup (Basisrente)":
                rente_stpfl += r * S.besteuerungsanteil(int(_zahl(v.get("jahr"), jahr)))
            else:
                beginn = int(_zahl(v.get("jahr"), jahr))
                sonst22 += r * S.ertragsanteil(beginn - jg)
        if sonst22 or rente_stpfl:
            abzug = min(p["wk_rente"], sonst22 + rente_stpfl)
            sonst22 = max(sonst22 + rente_stpfl - abzug, 0.0)
        else:
            sonst22 = 0.0
        miete_stpfl = s["miete"] * e["miete_steuer_pct"] / 100.0
        aeb = 0.0
        if jahr >= jg + 65:
            pct, hoechst = S.altersentlastung(jg + 65)
            aeb = min(pct * max(lohn_stpfl + max(miete_stpfl, 0.0), 0.0), hoechst)
        # Partner
        partner_eink = 0.0
        if split and s["partner"] > 0:
            if e["partner_jahr"] <= jahr:
                if e["partner_art"] == "rente":
                    partner_eink = s["partner"] * S.besteuerungsanteil(e["partner_jahr"]) - p["wk_rente"]
                elif e["partner_art"] == "pension":
                    pct, hoechst, zuschlag = S.versorgungsfreibetrag(e["partner_jahr"])
                    partner_eink = s["partner"] - min(pct * s["partner"], hoechst) - zuschlag - p["wk_rente"]
                else:
                    partner_eink = s["partner"] - p["wk_arbeitnehmer"]
            else:
                partner_eink = s["partner"] - p["wk_arbeitnehmer"]
            partner_eink = max(partner_eink, 0.0)
        # Sonderausgaben (+ Ausgleichszahlung als Altersvorsorgeaufwand)
        sa = s["vorsorge"] + p["sonderausgaben_pausch"] * (2 if split else 1)
        ausgleich_jahr = ausgleich["kosten"] if ausgleich["jahr"] == jahr else 0.0
        if ausgleich_jahr:
            rest = max(p["hoechst_altersvorsorge"] * (2 if split else 1) - 2 * s["rv_an"], 0.0)
            sa += min(ausgleich_jahr, rest)
        zve_ohne = eink_lohn + versorg + sonst22 + miete_stpfl + partner_eink - aeb - sa
        pv = s["aufst"] + s["alg"]
        st_ohne = S.steuern(S.est(max(zve_ohne, 0.0), p, split, pv, fak), p, split, kist, fak)["summe"]
        st_mit = S.steuern(S.est_fuenftel(zve_ohne + zve_einmal, ao, p, split, pv, fak), p, split, kist, fak)["summe"] \
            if (ao or zve_einmal) else st_ohne
        pausch = p["sparerpausch"] * (2 if split else 1)
        abg_lv = max(abg_einmal - pausch, 0.0) * abg
        pausch_rest = max(pausch - abg_einmal, 0.0)
        einmal_netto = einmal_brutto - (st_mit - st_ohne) - abg_lv

        laufend_brutto = sum(s[k] for k in ("lohn", "atz", "aufst", "alg", "rente", "bav", "vers", "miete", "hinzu",
                                            "partner"))
        sozial = s["sv"] + s["sv_partner"]
        netto = laufend_brutto - sozial - st_ohne

        # Ausgaben ab Ende des Erwerbslebens
        ausgaben = 0.0
        if post_monate:
            ausgaben = e["bedarf"] * ff * post_monate
            for k in kredite:
                if jahr <= int(_zahl(k.get("bis_jahr"), 0)):
                    ausgaben += _zahl(k.get("rate")) * post_monate
        einmal_aus = sum(_zahl(x.get("betrag")) for x in einmal if int(_zahl(x.get("jahr"), 0)) == jahr)
        # Netto der Monate nach dem Erwerbsleben (Steuer anteilig nach Brutto)
        if post_monate:
            post_netto = post_brutto - post_sv - (st_ohne * post_brutto / laufend_brutto if laufend_brutto > 0 else 0.0)
        else:
            post_netto = 0.0

        # Kapital
        zufluss = 0.0
        vor = n - post_monate
        if vor > 0:
            zufluss += e["sparrate"] * vor
            einstand += e["sparrate"] * vor
        zufluss += einmal_netto - einmal_aus - ausgleich_jahr
        einstand = max(einstand + max(einmal_netto, 0.0), 0.0)
        puffer = e["pflegepuffer"] * ff
        verfuegbar = max(kap - puffer, 0.0)
        entnahme = 0.0
        steuer_kap = 0.0
        bedarf_luecke = max(ausgaben - post_netto, 0.0)
        modus = e["entnahme_modus"]
        if post_monate:
            if modus == "luecke":
                ziel_netto = bedarf_luecke
            elif modus == "verzehr":
                if verzehr_w is None:
                    jahre = max(alter_x - alter_ende, 1)
                    verzehr_w = K.annuitaet(verfuegbar, r_pa, jahre, infl)
                    verzehr_basisjahr = jahr
                ziel_netto = verzehr_w * (1 + infl) ** (jahr - verzehr_basisjahr) * post_monate / 12.0 \
                    if alter_ende <= alter_x else 0.0
            elif modus == "ertraege":
                ziel_netto = max(verfuegbar * r_pa, 0.0) * post_monate / 12.0
            else:
                ziel_netto = e["entnahme_fest"] * post_monate
            if modus == "luecke":
                brutto_e = min(K.brutto_fuer_netto(ziel_netto, kap, einstand, abg, pausch_rest, tf), verfuegbar)
            else:
                brutto_e = min(ziel_netto, verfuegbar)
            steuer_kap, _, _ = K.steuer_auf_entnahme(brutto_e, kap, einstand, abg, pausch_rest, tf)
            entnahme = brutto_e
            if kap > 0:
                einstand -= einstand * entnahme / kap
            zufluss -= entnahme
            if modus == "luecke" and post_netto > ausgaben:
                zufluss += post_netto - ausgaben        # Ueberschuss wird angelegt
                einstand += post_netto - ausgaben
        kap = max(K.jahr_fortschreiben(kap, r_pa, zufluss, n), 0.0)
        einstand = min(max(einstand, 0.0), kap)
        entnahme_netto = entnahme - steuer_kap
        saldo = (post_netto + entnahme_netto - ausgaben) if post_monate else 0.0
        if post_monate and leer_ab is None and ziel_netto > (entnahme_netto if modus == "luecke" else entnahme) + 1:
            leer_ab = alter_ende            # gewuenschte Entnahme nicht mehr voll moeglich
        zeilen.append({
            "jahr": jahr, "alter": alter_ende, "monate": n,
            "phase": " → ".join(PHASEN_NAMEN[x] for x in phasen),
            "lohn": s["lohn"] + s["atz"], "aufstockung": s["aufst"], "alg": s["alg"], "rente": s["rente"],
            "bav": s["bav"], "versicherungen": s["vers"], "miete": s["miete"], "hinzuverdienst": s["hinzu"],
            "partner": s["partner"], "einmal_brutto": einmal_brutto, "einmal_netto": einmal_netto,
            "steuer": st_ohne + (st_mit - st_ohne) + abg_lv + steuer_kap, "steuer_laufend": st_ohne,
            "sozial": sozial, "netto": netto, "post_netto": post_netto, "post_monate": post_monate,
            "ausgaben": ausgaben, "einmal_ausgaben": einmal_aus + ausgleich_jahr, "entnahme": entnahme,
            "entnahme_netto": entnahme_netto, "saldo": saldo, "kapital": kap, "kapital_real": kap / ff,
            "inflationsfaktor": ff,
        })

    return {"zeilen": zeilen, "zeit": t, "ep_heute": ep0, "ep_neu": ep_neu, "ep_summe": ep_summe,
            "rente_start_brutto": rente_monat(t["rente"]), "ausgleich": ausgleich, "alg_monat": alg_monat,
            "leer_ab": leer_ab, "rendite": r_pa, "e": e, "sperr": sperr}


# ---------------------------------------------------------------------------
# Auswertung
# ---------------------------------------------------------------------------
def rentenarten(e, p, heute=None):
    """Uebersicht je Rentenart: abschlagsfrei ab / fruehestens ab (Datum + Alter), Wartezeit erfuellt?"""
    e = normalisieren(e)
    h = heute_idx(heute)
    t = zeitachse(e, p, h, "plan")
    g = R.grenzen(e["geb_jahr"])
    aus = []
    for art in R.ARTEN:
        if art == "schwerbehindert" and not e["schwerbehindert"]:
            continue
        frei, frueh = g[art]
        noetig = 45 if art == "besonders" else (5 if art == "regel" else 35)
        vorhanden = t["jahre45"] if art == "besonders" else t["jahre35"]
        aus.append({"art": art, "name": R.NAMEN[art],
                    "frei_alter": frei, "frei_idx": R.beginn_idx(e["geb_jahr"], e["geb_monat"], frei, e["geb_erster"]),
                    "frueh_alter": frueh, "frueh_idx": R.beginn_idx(e["geb_jahr"], e["geb_monat"], frueh, e["geb_erster"]),
                    "max_abschlag": R.abschlag(frei - frueh, p), "wartezeit": noetig,
                    "jahre": vorhanden, "erfuellt": vorhanden >= noetig})
    return aus


def kennzahlen(erg, vergleich=None):
    """Kennzahlen fuer die Kopfzeile."""
    t = erg["zeit"]
    zeilen = erg["zeilen"]
    voll = next((z for z in zeilen if z["jahr"] == t["rente"] // 12 + 1), None) or \
        next((z for z in zeilen if z["jahr"] >= t["rente"] // 12), zeilen[-1])
    f = voll["inflationsfaktor"]
    netto_m = voll["netto"] / max(voll["monate"], 1)
    ausgaben_m = voll["ausgaben"] / max(voll["post_monate"], 1) if voll["post_monate"] else 0.0
    luecke_m = max(ausgaben_m - voll["post_netto"] / max(voll["post_monate"], 1), 0.0) if voll["post_monate"] else 0.0
    k = {"rente_idx": t["rente"], "art": t["art"], "abschlag": t["abschlag"], "rente_brutto": erg["rente_start_brutto"],
         "netto_monat": netto_m, "netto_monat_real": netto_m / f, "luecke_monat": luecke_m,
         "luecke_monat_real": luecke_m / f, "ausgaben_monat": ausgaben_m, "leer_ab": erg["leer_ab"],
         "kapital_ende": zeilen[-1]["kapital"], "kapital_ende_real": zeilen[-1]["kapital_real"],
         "voll_jahr": voll["jahr"], "break_even": None}
    if vergleich is not None:
        k["break_even"] = break_even_alter(erg, vergleich)
    return k


def break_even_alter(frueh, regel):
    """Alter, ab dem die kumulierte gesetzliche Rente bei regulaerem Beginn die der vorzeitigen einholt."""
    if frueh["zeit"]["rente"] >= regel["zeit"]["rente"]:
        return None
    a = b = 0.0
    for zf, zr in zip(frueh["zeilen"], regel["zeilen"]):
        a += zf["rente"]
        b += zr["rente"]
        if zr["rente"] > 0 and b >= a:
            return zf["alter"]
    return None


def vergleich_tabelle(plan, regel):
    """Je Jahr: Netto (laufend + Einmalzahlungen) beider Varianten, Differenz monatlich und kumuliert."""
    aus = []
    kum = 0.0
    for a, b in zip(plan["zeilen"], regel["zeilen"]):
        na = a["netto"] + a["einmal_netto"]
        nb = b["netto"] + b["einmal_netto"]
        diff = na - nb
        kum += diff
        aus.append({"jahr": a["jahr"], "alter": a["alter"], "plan": na, "regel": nb,
                    "diff_monat": diff / max(a["monate"], 1), "diff_kumuliert": kum,
                    "kapital_plan": a["kapital"], "kapital_regel": b["kapital"]})
    return aus


def ampel(erg):
    """gruen: Einkommen deckt den Bedarf; gelb: nur mit Kapital (reicht bis 95); rot: Kapital reicht nicht."""
    zeilen = [z for z in erg["zeilen"] if z["post_monate"]]
    if not zeilen:
        return "gruen", "Kein Bedarf nach dem Erwerbsleben eingegeben."
    luecke = any(z["ausgaben"] - z["post_netto"] > 1 for z in zeilen)
    fehlt = [z for z in zeilen if z["saldo"] < -1 or (erg["leer_ab"] is not None and z["alter"] >= erg["leer_ab"])]
    if not luecke:
        return "gruen", "Die laufenden Einkünfte decken den Bedarf in jedem Jahr."
    if not fehlt:
        return "gelb", "Der Bedarf ist gedeckt, aber nur mit Entnahmen aus dem Kapital."
    return "rot", f"Ab Alter {fehlt[0]['alter']} ({fehlt[0]['jahr']}) reicht das Geld nicht für den Bedarf."


def netto_vorher_waehrend(e, p):
    """Monatsnetto 2026: Vollzeit vs. Altersteilzeit (50 % + Aufstockung, Progressionsvorbehalt)."""
    e = normalisieren(e)
    split = e["steuerklasse"] in VERHEIRATET
    kist = kirchensteuer_satz(p, e["bundesland"], e["kirche"])
    sachsen = e["bundesland"] == "Sachsen"
    privat = e["kv_art"] != "gesetzlich"
    partner = max(e["partner_lohn"] * 12 - p["wk_arbeitnehmer"], 0.0) if split else 0.0
    g = e["brutto_jahr"] / 12.0
    vorher = S.netto_arbeitnehmer(g, p, split, kist, e["kinder"], sachsen, privat, e["pkv_beitrag"], 0.0, partner)
    atz = g * 0.5
    waehrend = S.netto_arbeitnehmer(atz, p, split, kist, e["kinder"], sachsen, privat, e["pkv_beitrag"],
                                    atz * e["atz_aufstockung"] / 100.0, partner)
    return vorher, waehrend
