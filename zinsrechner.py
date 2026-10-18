"""Zinseszins- / Sparrechner (wie die klassischen Bank-Sparrechner) mit Permanentlink und PDF.

Rechenweise (deutsche Bankpraxis): Innerhalb einer Zinsperiode einfache (lineare)
Verzinsung je angefangenem Monat, am Periodenende Gutschrift (Zinseszins) oder Auszahlung.
Relativer Periodenzins = Zinssatz p.a. x Periodenlaenge / 12. Vorschuessig = Einzahlung am
Monatsanfang (der Monat zaehlt mit), nachschuessig = am Monatsende. Bei Sparintervallen > 1 Monat
wird vorschuessig am Anfang des Intervalls, nachschuessig am Ende des Intervalls eingezahlt
(z. B. jaehrlich nachschuessig = am Jahresende, im ersten Jahr also ohne Zinsen).
Zinsgutschrift und Sparerpauschbetrag richten sich nach dem KALENDERJAHR (wie bei Banken):
jaehrliche Gutschrift zum 31.12., halb-/vierteljaehrlich zum Ende des Kalenderhalbjahres/-quartals,
ausgehend vom Monat des Startdatums (monatsgenau). Der Rest am Laufzeitende wird zum Laufzeitende
gutgeschrieben. Bei Start am 1. Januar entspricht das genau den Vertragsjahren.
Cent-Rundung wie auf dem Kontoauszug: jede Zinsgutschrift wird kaufmaennisch auf den Cent gerundet
(ab 0,5 Cent auf), die Steuer darauf auf den Cent abgerundet (Bruchteile eines Cents bleiben ausser Ansatz).
Optional: Dynamik (Erhoehung der Rate), Festlegungsfrist (danach keine Raten mehr, Kapital
verzinst sich weiter), Abgeltungsteuer mit Sparerpauschbetrag je Kalenderjahr.
Jede Groesse (Anfangskapital, Rate, Dynamik, Zinssatz, Laufzeit, Endkapital) kann berechnet werden.
"""
import datetime
import math
import re
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

INTERVALLE = {1: "monatlich", 3: "vierteljährlich", 6: "halbjährlich", 12: "jährlich"}
ZIEL_FELDER = {"e": "Endkapital", "a": "Anfangskapital", "s": "Sparrate", "dy": "Dynamik", "z": "Zinssatz",
               "n": "Ansparzeit"}
STANDARD = {"a": 0.0, "s": 100.0, "si": 1, "ea": "v", "dy": 0.0, "dya": "j", "z": 5.0, "zp": 12, "ze": 1,
            "n": 10, "ne": "j", "f": 0, "fe": "j", "e": 0.0, "calc": "e", "st": 0.0, "fb": 1000.0, "am": "", "sd": "", "sp": "", "ep": ""}
ABGELTUNG = 26.375
# Wertebereiche wie in den Eingabefeldern (fuer Links von aussen)
GRENZEN = {"a": (0.0, 1e10), "s": (0.0, 1e9), "dy": (0.0, 100.0), "z": (-99.0, 100.0), "n": (0, 1200),
           "f": (0, 1200), "e": (0.0, 1e12), "st": (0.0, 60.0), "fb": (0.0, 1e6)}
AUSWAHL = {"ea": ("v", "n"), "dya": ("j", "i"), "ne": ("j", "m"), "fe": ("j", "m")}
# Zahlenfelder, die bei einem neuen (normalen) Benutzer beim ersten Start auf 0 stehen
NULL_FELDER = ("a", "s", "dy", "z", "n", "f", "e", "st", "fb")
# weitere gemerkte Felder ausserhalb von STANDARD (Zielwert, Wachstum bei Entnahme)
EXTRA_FELDER = {"zr_zielwert": None, "zr_wg": 2.0}
MAX_PLAN_MONATE = 1200                                  # Plaene in Phasen: hoechstens 100 Jahre
MAX_BETRAG = 1e12


# ===========================================================================
# Rechnung
# ===========================================================================
def _monate(wert, einheit):
    return int(round(float(wert))) * (12 if einheit == "j" else 1)


def _zahl_text(v):
    """Zahl verlustfrei als kurzer Text (fuer Link und Plaene): 1000.0 -> '1000', 123456.78 -> '123456.78'."""
    v = float(v)
    if v.is_integer() and abs(v) < 1e15:
        return str(int(v))
    return repr(v)


def _phasen_teile(text):
    """Text in einzelne 'JxB'-Teile zerlegen; Komma als Dezimalzeichen wird erkannt:
    '0,5x100' -> ['0.5x100'], '1x100,5' -> ['1x100.5'], '1x1000,3x500' -> ['1x1000', '3x500']."""
    roh = [t.strip().lower().replace(" ", "") for t in re.split(r"[,;]", str(text or ""))]
    teile = []
    i = 0
    while i < len(roh):
        t = roh[i]
        if t and "x" not in t and re.fullmatch(r"\d+", t):
            if i + 1 < len(roh) and re.match(r"\d+x", roh[i + 1]):
                teile.append(t + "." + roh[i + 1])       # '0,5x100' -> Jahre mit Dezimalkomma
                i += 2
                continue
            if teile and "." not in teile[-1].split("x", 1)[1]:
                teile[-1] = teile[-1] + "." + t          # '1x100,5' -> Betrag mit Dezimalkomma
        elif t:
            teile.append(t)
        i += 1
    return teile


_CENT = Decimal("0.01")
_MIKRO = Decimal("0.000001")


def _dezimal(x):
    """float -> Decimal, vorher auf 1/10.000 Cent geglaettet: Gleitkomma-Rest wie 47.4799999999
    (eigentlich genau 47,48) soll nicht ueber die Cent-Rundung entscheiden."""
    return Decimal(repr(float(x))).quantize(_MIKRO, rounding=ROUND_HALF_UP)


def _cent_kaufm(x):
    """Kaufmaennisch auf Cent runden (ab 0,5 Cent auf, negative Werte betragsmaessig)."""
    if not math.isfinite(x) or abs(x) >= 1e13:            # Cent hier bedeutungslos (Decimal-Genauigkeit)
        return x
    return float(_dezimal(x).quantize(_CENT, rounding=ROUND_HALF_UP))


def _cent_ab(x):
    """Auf Cent abrunden (Steuer: Bruchteile eines Cents bleiben ausser Ansatz)."""
    if not math.isfinite(x) or abs(x) >= 1e13:
        return x
    return float(_dezimal(x).quantize(_CENT, rounding=ROUND_DOWN))


def phasen(text):
    """'1x1000,3x500' -> [(12, 1000.0), (36, 500.0)]  (Jahre x Euro pro Monat, nacheinander ab Start).
    Robust fuer Links: 'X' wie 'x', Dezimalkomma, keine inf/nan, insgesamt hoechstens MAX_PLAN_MONATE."""
    aus = []
    summe = 0
    for teil in _phasen_teile(text):
        if teil.count("x") != 1:
            continue
        try:
            j, b = teil.split("x", 1)
            j, b = float(j), float(b)
        except ValueError:
            continue
        if not (math.isfinite(j) and math.isfinite(b)) or j <= 0 or b < 0:
            continue
        monate = int(round(min(j, MAX_PLAN_MONATE / 12.0) * 12))
        monate = min(monate, MAX_PLAN_MONATE - summe)
        if monate <= 0:
            continue
        aus.append((monate, min(b, MAX_BETRAG)))
        summe += monate
        if summe >= MAX_PLAN_MONATE:
            break
    return aus


def phasen_text(liste):
    """[(Jahre, Betrag)] -> '1x1000,3x500' (Betrag verlustfrei, Jahre auf 6 Nachkommastellen)."""
    def jahre(j):
        return _zahl_text(round(float(j), 6))
    return ",".join(f"{jahre(j)}x{_zahl_text(b)}" for j, b in liste if j > 0)


def phase_betrag(ph, m):
    """Monatsbetrag im Monat m (1-basiert) laut Phasen; nach der letzten Phase 0."""
    bis = 0
    for monate, betrag in ph:
        bis += monate
        if m <= bis:
            return betrag
    return 0.0


def rechne(p):
    """p: Parameter (siehe STANDARD). -> dict mit Endkapital, Summen, Jahrestabelle, Monatsverlauf.
    Zinsgutschrift (Zinsperiode zp) und Freibetrag nach Kalenderjahr ab dem Monat des Startdatums
    (startdatum(p)): Monat m endet im Kalendermonat (Startmonat - 1 + m) mod 12; Gutschrift, wenn das
    ein Periodenende ist (jaehrlich: Dezember), sowie am Laufzeitende. Freibetrag neu ab Januar.
    Jede Gutschrift wird kaufmaennisch auf Cent gerundet, die Steuer darauf auf Cent abgerundet.
    Die Jahrestabelle ("jahre") zeigt weiterhin die Stände je Vertragsjahr (Jahrestag)."""
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
    ein_kum, zins_kum, wert = [k], [0.0], [k]               # Monatswerte fuer den Chart
    zins_netto_kum = 0.0
    jz = {"ein": 0.0, "zins": 0.0, "steuer": 0.0, "ent": 0.0}
    frei_rest = freib
    rate = rate0
    sp_ph, ep_ph = phasen(p.get("sp")), phasen(p.get("ep"))
    # Laufzeit reicht mindestens bis zum Ende der Plaene
    n_ges = max(n_ges, sum(mo for mo, _ in sp_ph), sum(mo for mo, _ in ep_ph))
    entnommen = 0.0
    leer_monat = None
    ent_kum = [0.0]
    versatz = startdatum(p).month - 1                       # Monate vom 1.1. bis zum Startmonat
    for m in range(1, n_ges + 1):
        einz = 0.0
        ent = 0.0
        # Sparintervall: vorschuessig am Intervallanfang (Monat 1, 1+si, ...), nachschuessig am
        # Intervallende (Monat si, 2*si, ...); intervall_start = erster Monat des Intervalls
        faellig = (m - 1) % si == 0 if vorschuessig else m % si == 0
        intervall_start = m if vorschuessig else m - si + 1
        if sp_ph:                                           # Sparplan in Phasen (monatlich) statt fester Rate
            einz = phase_betrag(sp_ph, m)
            if einz:
                k += einz
                einzahlungen += einz
                jz["ein"] += einz
                if vorschuessig:
                    verzinst += einz
        elif m <= n_spar and faellig:
            if dyn:
                schritte = (intervall_start - 1) // 12 if p["dya"] == "j" else (intervall_start - 1) // si
                rate = rate0 * (1 + dyn) ** schritte
            einz = rate
            k += einz
            einzahlungen += einz
            jz["ein"] += einz
            if vorschuessig:
                verzinst += einz                            # zaehlt schon in diesem Monat
        if ep_ph and vorschuessig:                          # Entnahme am Monatsanfang
            ent = min(phase_betrag(ep_ph, m), max(k, 0.0))
            k -= ent
            verzinst = max(verzinst - ent, 0.0)
        periode_zins += verzinst * i_m
        if einz and not vorschuessig:
            verzinst += einz                                # erst ab dem naechsten Monat
        if ep_ph and not vorschuessig:                      # Entnahme am Monatsende
            ent = min(phase_betrag(ep_ph, m), max(k, 0.0))
            k -= ent
            verzinst = max(verzinst - ent, 0.0)
        if ent:
            entnommen += ent
            jz["ent"] += ent
        if ep_ph and leer_monat is None and phase_betrag(ep_ph, m) > 0 and k <= 0.005:
            leer_monat = m
        kal = versatz + m                                   # Kalendermonate seit Jahresbeginn (Ende Monat m)
        if kal % zp == 0 or m == n_ges:                     # Gutschrift am Ende der Kalenderperiode / Laufzeitende
            z_ = _cent_kaufm(periode_zins)                  # Gutschrift auf Cent (kaufmaennisch)
            st_ = 0.0
            if steuer and z_ > 0:
                steuerbar = max(z_ - frei_rest, 0.0)
                frei_rest = max(frei_rest - z_, 0.0)
                st_ = _cent_ab(steuerbar * steuer)          # Steuer auf Cent abgerundet
            zinsen_ges += z_
            steuer_ges += st_
            jz["zins"] += z_
            jz["steuer"] += st_
            zins_netto_kum += z_ - st_
            if zinseszins:
                k = round(k + z_ - st_, 9)                  # Gleitkomma-Staub (1e-16) entfernen
            else:
                ausgezahlt = round(ausgezahlt + z_ - st_, 9)
            verzinst = k
            periode_zins = 0.0
        if kal % 12 == 0:
            frei_rest = freib                               # Sparerpauschbetrag je Kalenderjahr
        verlauf.append(k)
        # Chart: aufgelaufene, noch nicht gutgeschriebene Zinsen schon mitzeigen (glatter Verlauf);
        # Steuer darauf erst, soweit der restliche Freibetrag des Kalenderjahres verbraucht ist
        if periode_zins > 0 and steuer:
            offen = periode_zins - max(periode_zins - frei_rest, 0.0) * steuer
        else:
            offen = periode_zins
        ein_kum.append(einzahlungen)
        ent_kum.append(entnommen)
        zins_kum.append(zins_netto_kum + offen)
        wert.append(max(einzahlungen - entnommen + zins_netto_kum + offen, 0.0))
        if m % 12 == 0 or m == n_ges:
            jahre.append({"jahr": (m - 1) // 12 + 1, "monat": m, "ein": jz["ein"], "zins": jz["zins"],
                          "steuer": jz["steuer"], "ent": jz["ent"], "stand": k})
            jz = {"ein": 0.0, "zins": 0.0, "steuer": 0.0, "ent": 0.0}
    return {"end": k, "einzahlungen": einzahlungen, "zinsen": zinsen_ges, "steuer": steuer_ges,
            "ausgezahlt": ausgezahlt, "jahre": jahre, "verlauf": verlauf, "monate": n_ges, "spar_monate": n_spar,
            "ein_kum": ein_kum, "zins_kum": zins_kum, "wert": wert, "start": float(p["a"]),
            "ent_kum": ent_kum, "entnommen": entnommen, "leer_monat": leer_monat,
            "letzte_rate": rate}


def loese(p):
    """Berechnet die in p["calc"] gewaehlte Groesse so, dass das Endkapital p["e"] erreicht wird.
    Ergebnis ist immer der kleinste Wert, der das Ziel sicher erreicht (Betraege auf den Cent,
    Prozentsaetze auf 4 Nachkommastellen aufgerundet). Zinssatz bei Zinsauszahlung (ze=0): Ziel =
    Endkapital + ausgezahlte Zinsen (der Kontostand allein haengt dann nicht vom Zins ab).
    -> (p mit eingesetztem Wert, Ergebnis, Hinweis)"""
    ziel = p["calc"]
    if ziel == "e":
        return p, rechne(p), ""
    soll = float(p["e"])
    q = dict(p)
    # Zinsauszahlung (kein Zinseszins): der Kontostand haengt nicht vom Zinssatz ab -> fuer den
    # Zinssatz zaehlen Endkapital + ausgezahlte Zinsen (wie in noetiger_zins)
    mit_auszahlung = ziel == "z" and not int(p.get("ze", 1))
    hinweis_aus = ("Zinsen werden ausgezahlt: Ziel = Endkapital + ausgezahlte Zinsen."
                   if mit_auszahlung else "")

    def end(wert, feld):
        q[feld] = wert
        r_ = rechne(q)
        return r_["end"] + (r_["ausgezahlt"] if mit_auszahlung else 0.0)
    if ziel in ("a", "s"):
        # Endkapital steigt monoton mit Anfangskapital/Rate (auch mit Steuer und Entnahmeplan,
        # dort aber nicht linear) -> Bisektion statt linearer Hochrechnung
        f0 = end(0.0, ziel)
        if f0 >= soll:
            q[ziel] = 0.0
            return q, rechne(q), "Das Endkapital wird schon ohne diesen Betrag erreicht."
        grenze = GRENZEN[ziel][1]
        hi = 1.0
        while end(hi, ziel) < soll:
            if hi >= grenze:
                if end(grenze, ziel) <= f0 + 1e-9:
                    return p, rechne(p), "Nicht berechenbar (z. B. keine Sparzeit für die Rate)."
                q[ziel] = grenze
                return q, rechne(q), f"Auch mit {_de(grenze, 0)} € nicht erreichbar."
            hi = min(hi * 2, grenze)
        lo = 0.0
        for _ in range(60):
            mi = (lo + hi) / 2
            if end(mi, ziel) >= soll:
                hi = mi
            else:
                lo = mi
        wert = math.ceil(hi * 100) / 100                   # auf den Cent aufrunden -> Ziel sicher erreicht
        for _ in range(1000):
            if end(wert, ziel) >= soll:
                break
            wert = round(wert + 0.01, 2)
        for _ in range(3):                                 # kleinster Cent-Betrag, der das Ziel erreicht
            if wert >= 0.01 and end(round(wert - 0.01, 2), ziel) >= soll:
                wert = round(wert - 0.01, 2)
            else:
                break
        q[ziel] = wert
        return q, rechne(q), ""
    if ziel in ("z", "dy"):
        lo, hi = (-0.99 * 100, 100.0) if ziel == "z" else (0.0, 100.0)
        if end(hi, ziel) < soll:
            q[ziel] = hi
            return q, rechne(q), " ".join(x for x in (f"Auch mit {hi:.0f} % nicht erreichbar.", hinweis_aus) if x)
        if end(lo, ziel) >= soll:
            q[ziel] = lo
            return q, rechne(q), " ".join(x for x in ("Wird schon mit dem kleinsten Wert erreicht.", hinweis_aus)
                                          if x)
        for _ in range(100):
            mi = (lo + hi) / 2
            if end(mi, ziel) >= soll:
                hi = mi
            else:
                lo = mi
        wert = math.ceil(hi * 1e4) / 1e4                   # aufrunden (4 Stellen) -> Ziel sicher erreicht
        for _ in range(100):
            if end(wert, ziel) >= soll or wert >= 100.0:
                break
            wert = round(wert + 1e-4, 4)
        q[ziel] = wert
        return q, rechne(q), hinweis_aus
    if ziel == "n":
        q["ne"] = "m"
        max_n = GRENZEN["n"][1]
        if float(p["z"]) >= 0 and not phasen(p.get("ep")) and float(p["s"]) >= 0:
            # ohne Entnahmen und negative Zinsen steigt das Endkapital mit jedem Monat -> Bisektion
            # (statt bis zu 1.200 Rechnungen); Ergebnis unten noch einmal geprueft
            if end(max_n, "n") < soll:
                q["n"] = max_n
                return q, rechne(q), "In 100 Jahren nicht erreichbar."
            lo, hi = -1, max_n
            while hi - lo > 1:
                mi = (lo + hi) // 2
                if end(mi, "n") >= soll:
                    hi = mi
                else:
                    lo = mi
            if end(hi, "n") >= soll and (hi == 0 or end(hi - 1, "n") < soll):
                q["n"] = hi
                return q, rechne(q), ""
        for monate in range(0, max_n + 1):
            if end(monate, "n") >= soll:
                q["n"] = monate
                return q, rechne(q), ""
        return q, rechne(q), "In 100 Jahren nicht erreichbar."
    return p, rechne(p), ""


IMMER_ERREICHT = float("-inf")       # noetiger_zins: Ziel wird mit jedem Zinssatz (auch -99 %) erreicht


def noetiger_zins(p, ziel_end):
    """Zinssatz p.a., bei dem das Endkapital ziel_end erreicht.
    -> Zinssatz (auf 4 Stellen aufgerundet), None = selbst mit 100 % nicht erreichbar,
       IMMER_ERREICHT (-inf) = wird schon mit dem kleinsten Zinssatz erreicht.
    Bei Zinsauszahlung (ze=0) zaehlen die ausgezahlten Zinsen mit (Kontostand + ausgezahlt),
    sonst waere Kapitalerhalt bei Entnahmen nie erreichbar."""
    soll = float(ziel_end)
    mit_auszahlung = not int(p.get("ze", 1))

    def wert(z):
        r = rechne(dict(p, z=z))
        return r["end"] + (r["ausgezahlt"] if mit_auszahlung else 0.0)
    lo, hi = GRENZEN["z"]
    if wert(hi) < soll:
        return None
    if wert(lo) >= soll:
        return IMMER_ERREICHT
    for _ in range(60):
        mi = (lo + hi) / 2
        if wert(mi) >= soll:
            hi = mi
        else:
            lo = mi
    return math.ceil(hi * 1e4) / 1e4


def entnahme_analyse(p, r, wachstum=0.02):
    """Wie viel Zins braucht der Entnahmeplan?
    - gesamt: Kapitalerhalt = Endkapital so hoch wie alles Eingezahlte; Wachstum = zusaetzlich +wachstum p.a.
    - je Phase: Zins, bei dem die Zinsen eines Jahres genau die Entnahmen dieses Jahres decken
      (Kapital zu Beginn der Phase bleibt gleich) bzw. es um +wachstum waechst; Deckung mit dem aktuellen Zins."""
    if not r.get("entnommen"):
        return None
    jahre = r["monate"] / 12
    eingezahlt = r["einzahlungen"]
    basis = dict(p, sp=p.get("sp", ""), calc="e")
    gesamt = {"erhalt": noetiger_zins(basis, eingezahlt),
              "wachstum": noetiger_zins(basis, eingezahlt * (1 + wachstum) ** jahre)}
    phasen_ = []
    sd = startdatum(p)
    ab = 0
    z_akt = float(p["z"])
    for monate, betrag in phasen(p.get("ep")):
        if betrag <= 0:
            ab += monate
            continue
        k0 = r["verlauf"][min(ab, len(r["verlauf"]) - 1)]
        if k0 <= 0:
            phasen_.append({"von": plus_monate(sd, ab), "bis": plus_monate(sd, ab + monate) - datetime.timedelta(days=1),
                            "betrag": betrag, "kapital": 0.0, "erhalt": None, "wachstum": None, "deckung": 0.0})
            ab += monate
            continue
        test = dict(STANDARD, a=k0, s=0.0, si=1, ea=p["ea"], z=z_akt, zp=p["zp"], ze=p["ze"], n=1, ne="j",
                    f=0, st=p.get("st", 0.0), fb=p.get("fb", 1000.0), ep=f"1x{_zahl_text(betrag)}", sp="",
                    sd=plus_monate(sd, ab).isoformat(), am="")
        erhalt = noetiger_zins(test, k0)
        wachs = noetiger_zins(test, k0 * (1 + wachstum))
        jr = rechne(test)
        # Deckung mit den Zinsen NACH Steuer - passt damit zu "Erhalt" (Kapital bleibt gleich <=> Deckung >= 100 %)
        deckung = (jr["zinsen"] - jr["steuer"]) / (12 * betrag) if betrag else None
        phasen_.append({"von": plus_monate(sd, ab), "bis": plus_monate(sd, ab + monate) - datetime.timedelta(days=1),
                        "betrag": betrag, "kapital": k0, "erhalt": erhalt, "wachstum": wachs, "deckung": deckung})
        ab += monate
    return {"gesamt": gesamt, "phasen": phasen_, "wachstum": wachstum, "zins": z_akt, "eingezahlt": eingezahlt,
            "auszahlung": not int(p.get("ze", 1))}


def _noetig_text(x):
    """Noetiger Zinssatz als Text (None = nicht erreichbar, IMMER_ERREICHT = jeder Zinssatz reicht)."""
    if x is None:
        return "über 100 %"
    if x == IMMER_ERREICHT:
        return "jeder Zinssatz"
    return f"{_de(x, 2)} %"


# ===========================================================================
# Permanentlink (URL-Parameter)
# ===========================================================================
def standard_werte(null=False):
    """Startwerte: STANDARD bzw. (null=True, neuer Benutzer) alle Zahlenfelder auf 0."""
    p = dict(STANDARD)
    if null:
        for k in NULL_FELDER:
            p[k] = type(STANDARD[k])(0)
    return p


def aus_url(qp, basis=None):
    """URL-Parameter -> Parameter-dict (unbekannte/kaputte Werte -> Standard bzw. basis)."""
    p = dict(basis or STANDARD)
    for k, std in STANDARD.items():
        if k in qp:
            roh = qp[k]
            try:
                if isinstance(std, (int, float)) and not isinstance(std, bool):
                    x = float(str(roh).strip().replace(",", "."))
                    if not math.isfinite(x):
                        continue                       # inf/nan -> Standard
                    if k in GRENZEN:
                        x = min(max(x, GRENZEN[k][0]), GRENZEN[k][1])
                    p[k] = type(std)(x)
                else:
                    p[k] = str(roh)
            except (TypeError, ValueError, OverflowError):
                pass
    if p["si"] not in INTERVALLE:
        p["si"] = 1
    if p["zp"] not in INTERVALLE:
        p["zp"] = 12
    if p["calc"] not in ZIEL_FELDER:
        p["calc"] = "e"
    p["ze"] = 1 if p["ze"] else 0
    for k, erlaubt in AUSWAHL.items():
        if p[k] not in erlaubt:
            p[k] = STANDARD[k]
    for feld, fmt in (("sd", "%Y-%m-%d"), ("am", "%Y-%m")):
        if p[feld] and _datum(p[feld], fmt) is None:
            p[feld] = ""                               # ungueltiges/unplausibles Datum -> heute
    return p


def in_url(p):
    """Nur Abweichungen vom Standard in den Link (kurz, lesbar und verlustfrei)."""
    aus = {"ansicht": "zins"}
    for k, std in STANDARD.items():
        if k == "e" and p.get("calc", "e") == "e":
            continue                                   # Endkapital wird dann berechnet
        v = p.get(k, std)
        if v != std:
            aus[k] = (_zahl_text(v) if isinstance(v, float) else str(v))
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


JAHR_MIN, JAHR_MAX = 1900, 2200         # plausibler Bereich fuer das Startdatum


def _datum(text, fmt):
    """Datum aus Text oder None (auch bei Jahren ausserhalb JAHR_MIN..JAHR_MAX)."""
    try:
        d = datetime.datetime.strptime(str(text), fmt).date()
    except (TypeError, ValueError):
        return None
    return d if JAHR_MIN <= d.year <= JAHR_MAX else None


def startdatum(p):
    """Startdatum aus p["sd"] (JJJJ-MM-TT), alt: p["am"] (JJJJ-MM) - sonst heute."""
    for feld, fmt in (("sd", "%Y-%m-%d"), ("am", "%Y-%m")):
        if p.get(feld):
            d = _datum(p[feld], fmt)
            if d is not None:
                return d
    return datetime.date.today()


def plus_monate(d, monate):
    import calendar
    j, m = divmod(d.month - 1 + int(monate), 12)
    jahr, monat = d.year + j, m + 1
    return datetime.date(jahr, monat, min(d.day, calendar.monthrange(jahr, monat)[1]))


def zeitachse(p, r):
    """Tabellenzeilen: Start (Anfangskapital) und je volles Jahr (bzw. Laufzeitende) mit Datum."""
    sd = startdatum(p)
    zeilen = [{"datum": sd, "text": "Start", "ein": r["start"], "zins": 0.0, "steuer": 0.0, "ent": 0.0,
               "stand": r["start"]}]
    for z in r["jahre"]:
        zeilen.append({"datum": plus_monate(sd, z["monat"]), "text": "", "ein": z["ein"], "zins": z["zins"],
                       "steuer": z["steuer"], "ent": z.get("ent", 0.0), "stand": z["stand"]})
    if zeilen:
        zeilen[-1]["text"] = "Ende" if len(zeilen) > 1 else "Start"
    return zeilen


def _jahr_label(z, p):
    if p.get("am"):
        try:
            j0, m0 = (int(x) for x in str(p["am"]).split("-")[:2])
            ende = datetime.date(j0 + (m0 - 1 + z["monat"] - 1) // 12, (m0 - 1 + z["monat"] - 1) % 12 + 1, 1)
            return ende.strftime("%m/%Y")
        except Exception:
            pass
    return str(z["jahr"])


def phasen_zeitraeume(p, feld):
    """[(von, bis, betrag)] je Phase mit echten Daten."""
    sd = startdatum(p)
    aus, ab = [], 0
    for monate, betrag in phasen(p.get(feld)):
        aus.append((plus_monate(sd, ab), plus_monate(sd, ab + monate) - datetime.timedelta(days=1), betrag))
        ab += monate
    return aus


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
    zei.append(["Startdatum", startdatum(p).strftime("%d.%m.%Y")])
    for feld, name in (("sp", "Sparplan"), ("ep", "Entnahmeplan")):
        for von, bis, betrag in phasen_zeitraeume(p, feld):
            zei.append([f"{name} {von.strftime('%d.%m.%Y')} – {bis.strftime('%d.%m.%Y')}", f"{_de(betrag)} € / Monat"])
    if phasen(p.get("sp")):
        zei[1] = ["Sparrate", "laut Sparplan (siehe unten)"]
    return zei


def _pdf_chart(pdf, p, r, hoehe=170):
    """Gestapelte Flaechen (Eingezahlt / Zinsen) als Vektorgrafik im PDF."""
    n = len(r["wert"])
    if n < 2:
        return
    pdf.ueberschrift("Verlauf")
    pdf.platz(hoehe + 30)
    x0, x1 = pdf.RAND + 52, pdf.B - pdf.RAND - 4
    y0 = pdf.y - hoehe
    y1 = pdf.y - 6
    vmax = (max(max(r["wert"]), max(r.get("ent_kum") or [0.0])) or 1.0) * 1.08
    # "schoene" Obergrenze
    import math as _m
    stufe = 10 ** _m.floor(_m.log10(vmax))
    for f in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if vmax <= f * stufe:
            top = f * stufe
            break

    def X(i):
        return x0 + (x1 - x0) * i / (n - 1)

    def Y(v):
        return y0 + (y1 - y0) * v / top
    # Gitter + Achsenbeschriftung
    for k in range(5):
        v = top * k / 4
        pdf.linie(x0, Y(v), x1, Y(v), (0.88, 0.88, 0.88), 0.4)
        pdf.text(x0 - 6, Y(v) - 3, f"{_de(v, 0)} €", 7, farbe=(0.45, 0.45, 0.45), rechts=True)
    sd = startdatum(p)
    jahre_n = (n - 1) / 12
    schritt = (1 if jahre_n <= 12 else (2 if jahre_n <= 24 else 5)) * 12
    for i in range(0, n, schritt):
        pdf.linie(X(i), y0, X(i), y0 - 3, (0.6, 0.6, 0.6), 0.5)
        pdf.text(X(i) - 8, y0 - 12, plus_monate(sd, i).strftime("%Y"), 7, farbe=(0.45, 0.45, 0.45))

    def flaeche(unten, oben, farbe):
        pts = [(X(i), Y(oben[i])) for i in range(n)] + [(X(i), Y(unten[i])) for i in reversed(range(n))]
        pdf.ops.append(f"{farbe[0]:.3f} {farbe[1]:.3f} {farbe[2]:.3f} rg " + f"{pts[0][0]:.2f} {pts[0][1]:.2f} m "
                       + " ".join(f"{a:.2f} {b:.2f} l" for a, b in pts[1:]) + " h f")

    def linie(werte, farbe, strich=""):
        pdf.ops.append(f"{farbe[0]:.3f} {farbe[1]:.3f} {farbe[2]:.3f} RG 1.4 w {strich} {X(0):.2f} {Y(werte[0]):.2f} m "
                       + " ".join(f"{X(i):.2f} {Y(werte[i]):.2f} l" for i in range(1, n)) + " S [] 0 d")
    ent = r.get("ent_kum") or [0.0] * n
    basis = [max(e - a, 0.0) for e, a in zip(r["ein_kum"], ent)]
    mit_ent = r.get("entnommen", 0) > 0
    null = [0.0] * n
    blau, orange, gruen = (0.224, 0.529, 0.898), (0.851, 0.349, 0.149), (0.098, 0.620, 0.439)
    flaeche(null, basis, (0.80, 0.87, 0.97))
    flaeche(basis, r["wert"], (0.98, 0.85, 0.79))
    linie(basis, blau)
    linie(r["wert"], orange)
    if mit_ent:
        linie(ent, gruen, "[3 2] 0 d")
    # Wert je Jahr ueber dem Punkt (bei vielen Jahren nur jedes k-te, Ende immer)
    from abfindung import _breite
    idx = [0] + [z["monat"] for z in r["jahre"]]
    gr = 6.8 if len(idx) > 8 else 7.5
    for i in idx:
        xx, yy = X(i), Y(r["wert"][i])
        pdf.ops.append(f"1 1 1 rg 0.851 0.349 0.149 RG 1.2 w {xx - 2.2:.2f} {yy - 2.2:.2f} 4.4 4.4 re B")
    # Beschriftung je Jahr: Start und Ende zuerst, dann alle anderen, die nicht ueberlappen
    belegt = []
    reihenfolge = [0, len(idx) - 1] + list(range(1, len(idx) - 1))
    for nr in dict.fromkeys(reihenfolge):
        i = idx[nr]
        xx, yy = X(i), Y(r["wert"][i])
        txt = _de(r["wert"][i], 0)
        fett = nr in (0, len(idx) - 1)
        b_ = _breite(txt, gr, fett)
        tx = min(max(xx - b_ / 2, x0), x1 - b_)
        box = (tx - 2, tx + b_ + 2, yy + 4, yy + 4 + gr)
        if any(not (box[1] < a[0] or box[0] > a[1] or box[3] < a[2] or box[2] > a[3]) for a in belegt):
            continue
        belegt.append(box)
        pdf.text(tx, yy + 5, txt, gr, fett, (0.12, 0.12, 0.12))
    # Legende
    ly = y1 + 6
    lx = x0
    for farbe, txt in ([(blau, "Eingezahlt abzgl. Entnahmen" if mit_ent else "Eingezahlt"),
                        (orange, "Zinsen" if int(p["ze"]) else "Zinsen (ausgezahlt)")]
                       + ([(gruen, "Entnahmen gesamt")] if mit_ent else [])):
        pdf.rechteck(lx, ly, 8, 8, farbe)
        pdf.text(lx + 12, ly + 1, txt, 8, farbe=(0.25, 0.25, 0.25))
        from abfindung import _breite
        lx += 24 + _breite(txt, 8)
    pdf.y = y0 - 20


def pdf_bericht(p, r, hinweis="", link="", analyse=None):
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
             + (f" · ausgezahlt {_de(r['ausgezahlt'])} €" if r["ausgezahlt"] else "")
             + (f" · Entnahmen {_de(r['entnommen'])} €" if r.get("entnommen") else ""), 9)
    if hinweis:
        pdf.text(pdf.RAND + 10, pdf.y - 54, hinweis, 8.5, farbe=(0.6, 0.2, 0.1))
    pdf.y -= 72
    _pdf_chart(pdf, p, r)
    pdf.ueberschrift("Kenndaten")
    pdf.tabelle(["Angabe", "Wert"], zeilen_kenndaten(p), [2, 2.4])
    pdf.ueberschrift("Entwicklung")
    za = zeitachse(p, r)
    mit_st = bool(r["steuer"])
    mit_ent = any(z.get("ent") for z in za)
    pdf.tabelle(["Datum", "Einzahlungen"] + (["Entnahmen"] if mit_ent else []) + ["Zinsen"]
                + (["Steuern"] if mit_st else []) + ["Kontostand"],
                [[z["datum"].strftime("%d.%m.%Y") + (f"  ({z['text']})" if z["text"] else ""),
                  f"{_de(z['ein'])} €"] + ([f"-{_de(z['ent'])} €" if z.get("ent") else "0,00 €"] if mit_ent else [])
                 + [f"{_de(z['zins'])} €"] + ([f"{_de(z['steuer'])} €"] if mit_st else [])
                 + [f"{_de(z['stand'])} €"] for z in za],
                [1.4, 1.1] + ([1.1] if mit_ent else []) + [1.1] + ([0.9] if mit_st else []) + [1.3], groesse=8,
                hervor={0, len(za) - 1})
    if r.get("leer_monat"):
        pdf.absatz(f"Achtung: Das Kapital ist am {plus_monate(startdatum(p), r['leer_monat']).strftime('%d.%m.%Y')} "
                   "aufgebraucht – danach sind keine Entnahmen mehr möglich.", 8.5, True, (0.6, 0.2, 0.1))
    if analyse:
        pdf.ueberschrift("Entnahme & Zinsen")
        g, z = analyse["gesamt"], analyse["zins"]
        pdf.absatz(f"Gerechnet mit {_de(z, 2)} % p.a. Für Kapitalerhalt über die ganze Laufzeit (Endkapital"
                   + (" + ausgezahlte Zinsen" if analyse.get("auszahlung") else "") + " = "
                   f"eingezahlte {_de(analyse['eingezahlt'])} €) ist nötig: " + _noetig_text(g["erhalt"])
                   + f"; für zusätzlich +{_de(analyse['wachstum'] * 100, 1)} % Wachstum p.a.: "
                   + _noetig_text(g["wachstum"]) + ".", 8.5)
        pdf.tabelle(["Zeitraum", "Entnahme/Monat", "Kapital am Start", "Erhalt", f"+{_de(analyse['wachstum'] * 100, 1)} %",
                     "Deckung"],
                    [[f"{x['von'].strftime('%d.%m.%Y')} - {x['bis'].strftime('%d.%m.%Y')}", f"{_de(x['betrag'])} €",
                      f"{_de(x['kapital'])} €", _noetig_text(x["erhalt"]) if x["erhalt"] is not None else "-",
                      _noetig_text(x["wachstum"]) if x["wachstum"] is not None else "-",
                      f"{_de((x['deckung'] or 0) * 100, 0)} %"] for x in analyse["phasen"]],
                    [1.9, 1, 1.1, 0.7, 0.7, 0.7], groesse=8)
        pdf.absatz("Erhalt = Zinssatz, bei dem die Zinsen eines Jahres die Entnahmen dieses Jahres genau decken (Kapital "
                   "bleibt gleich). Deckung = Anteil der Entnahmen, den die Zinsen (nach Steuer) beim gewählten Zinssatz decken.", 7.5)
    if link:
        pdf.y -= 6
        pdf.absatz("Permanentlink: " + link, 7.5, farbe=(0.2, 0.3, 0.6))
    pdf.absatz("Rechenweise: innerhalb der Zinsperiode lineare Verzinsung je Monat, Zinsgutschrift am Ende der "
               "Zinsperiode im Kalenderjahr (jährlich zum 31.12.) und zum Laufzeitende, Sparerpauschbetrag je "
               "Kalenderjahr (Bankpraxis); Zinsen je Gutschrift kaufmännisch auf Cent gerundet, Steuer auf Cent "
               "abgerundet. Szenariorechnung ohne Gewähr.", 7.5)
    return pdf.bytes()


# ===========================================================================
# Chart (Plotly) - Eingezahltes und Zinsen gestapelt, Datum auf der Zeitachse
# ===========================================================================
FARBEN = {"ein": "#3987e5", "zins": "#d95926", "ent": "#199e70", "text": "#e8e6df", "text2": "#a9a79c", "grid": "#2a2a28",
          "flaeche": "#0e1117"}


def _rgba(hexfarbe, a):
    h = hexfarbe.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


def analyse_html(a):
    """Status + Tabelle je Entnahme-Phase (Icon + Text, nie nur Farbe)."""
    z = a["zins"]
    g = a["gesamt"]

    def status(noetig):
        if noetig is None:
            return '<span style="color:#e66767">⚠ selbst mit 100 % nicht erreichbar</span>'
        if noetig == IMMER_ERREICHT:
            return '<span style="color:#4cc38a">✓ erreicht (mit jedem Zinssatz)</span>'
        if z >= noetig - 1e-9:
            return f'<span style="color:#4cc38a">✓ erreicht ({_de(z, 2)} % ≥ {_de(noetig, 2)} %)</span>'
        return f'<span style="color:#f0a27f">⚠ fehlen {_de(noetig - z, 2)} Prozentpunkte</span>'

    def wert(x):
        if x == IMMER_ERREICHT:
            return "jeder"
        return f"{_de(x, 2)} %" if x is not None else "–"
    aus_txt = (" + ausgezahlte Zinsen" if a.get("auszahlung") else "")
    zeilen_g = (
        f'<div style="display:grid;grid-template-columns:1fr auto;gap:6px 10px;font-size:.86rem;margin:4px 0 12px">'
        f'<div>Kapitalerhalt über die ganze Laufzeit<br><span style="color:#a9a79c;font-size:0.8rem">Endkapital'
        f'{aus_txt} = alles Eingezahlte ({_de(a["eingezahlt"], 0)} €)</span></div><div style="text-align:right"><b>{wert(g["erhalt"])}</b>'
        f'<br><span style="font-size:0.8rem">{status(g["erhalt"])}</span></div>'
        f'<div>Zusätzlich +{_de(a["wachstum"] * 100, 1)} % Wachstum p.a.</div><div style="text-align:right">'
        f'<b>{wert(g["wachstum"])}</b><br><span style="font-size:0.8rem">{status(g["wachstum"])}</span></div></div>')
    th = "".join(f'<th style="text-align:{"left" if i == 0 else "right"};padding:6px 4px;color:#a9a79c;font-weight:600;'
                 f'border-bottom:1px solid #2a2a28;white-space:nowrap">{k}</th>'
                 for i, k in enumerate(["Phase", "€/Monat", "Erhalt", f"+{_de(a['wachstum'] * 100, 1)} %",
                                        "Deckung"]))
    tr = []
    for x in a["phasen"]:
        dk = (x["deckung"] or 0) * 100
        farbe = "#4cc38a" if dk >= 100 else "#f0a27f"
        tr.append("<tr>" + "".join(
            f'<td style="text-align:{"left" if i == 0 else "right"};padding:6px 4px;border-bottom:1px solid #2a2a28;'
            f'white-space:nowrap;vertical-align:top">{c}</td>' for i, c in enumerate([
                f'{x["von"].strftime("%m/%Y")}–{x["bis"].strftime("%m/%Y")}<div style="font-size:0.8rem;color:#a9a79c">'
                f'Start {_de(x["kapital"], 0)} €</div>',
                _de(x["betrag"], 0), wert(x["erhalt"]), wert(x["wachstum"]),
                f'<span style="color:{farbe}">{"✓" if dk >= 100 else "⚠"} {_de(dk, 0)} %</span>'])) + "</tr>")
    return (zeilen_g + '<table style="width:100%;border-collapse:collapse;font-size:.8rem;color:#e8e6df;'
            f'font-variant-numeric:tabular-nums"><thead><tr>{th}</tr></thead><tbody>{"".join(tr)}</tbody></table>'
            '<div style="font-size:0.8rem;color:#a9a79c;margin-top:6px">Erhalt = Zinssatz, bei dem die Zinsen eines Jahres '
            'die Entnahmen dieser Phase genau decken (Kapital bleibt gleich). Deckung = so viel der Entnahmen zahlen die '
            f'Zinsen (nach Steuer) beim gewählten Zinssatz von {_de(z, 2)} %.'
            + (' Zinsen werden ausgezahlt (kein Zinseszins): Kapitalerhalt zählt Kontostand plus ausgezahlte Zinsen.'
               if a.get("auszahlung") else "") + '</div>')


def tabelle_html(za, r):
    """Kompakte Tabelle: Datum (darunter klein 'Anfangskapital'/'Endkapital'), Betraege rechtsbuendig,
    feste Spaltenbreiten - passt aufs iPhone ohne seitliches Scrollen."""
    import html as _h
    mit_ein = any(z["ein"] for z in za[1:])
    mit_st = bool(r["steuer"])
    mit_ent = any(z.get("ent") for z in za[1:])
    kopf = ["Datum"] + (["Einzahlung €"] if mit_ein else []) + (["Entnahme €"] if mit_ent else []) + ["Zinsen €"] + \
           (["Steuer €"] if mit_st else []) + ["Kontostand €"]
    spalten = len(kopf)
    groesse = {3: ".86rem", 4: ".8rem", 5: ".72rem"}.get(spalten, ".64rem")
    pad = "7px 6px" if spalten <= 4 else ("6px 3px" if spalten == 5 else "5px 2px")
    th = "".join(f'<th style="text-align:{"left" if i == 0 else "right"};padding:{pad};font-weight:600;white-space:nowrap;'
                 f'color:{FARBEN["text2"]};border-bottom:1px solid {FARBEN["grid"]}">{k}</th>'
                 for i, k in enumerate(kopf))
    zeilen = []
    for z in za:
        rand = z["text"] in ("Start", "Ende")
        label = {"Start": "Anfangskapital", "Ende": "Endkapital"}.get(z["text"], "")
        zellen = [f'{z["datum"].strftime("%d.%m.%Y")}'
                  + (f'<div style="font-size:0.8rem;color:{FARBEN["text2"]};line-height:1.1">{label}</div>'
                     if label else "")]
        leer = z["text"] == "Start"
        if mit_ein:
            zellen.append("" if leer else _de(z['ein']))
        if mit_ent:
            zellen.append("" if leer else ("−" + _de(z['ent']) if z.get("ent") else _de(0)))
        zellen.append("" if leer else _de(z['zins']))
        if mit_st:
            zellen.append("" if leer else _de(z['steuer']))
        zellen.append(f"<b>{_de(z['stand'])}</b>" if rand else _de(z['stand']))
        td = "".join(f'<td style="text-align:{"left" if i == 0 else "right"};padding:{pad};white-space:nowrap;'
                     f'vertical-align:top;border-bottom:1px solid {FARBEN["grid"]}">{c}</td>'
                     for i, c in enumerate(zellen))
        zeilen.append(f"<tr>{td}</tr>")
    return (f'<table style="width:100%;border-collapse:collapse;table-layout:auto;font-size:{groesse};'
            f'font-variant-numeric:tabular-nums;color:{FARBEN["text"]}"><thead><tr>{th}</tr></thead>'
            f'<tbody>{"".join(zeilen)}</tbody></table>')


def chart(p, r):
    import plotly.graph_objects as go
    sd = startdatum(p)
    x = [plus_monate(sd, i) for i in range(len(r["wert"]))]
    zins_txt = "Zinsen" if int(p["ze"]) else "Zinsen (ausgezahlt)"
    mit_ent = r.get("entnommen", 0) > 0
    basis = [max(e - a, 0.0) for e, a in zip(r["ein_kum"], r.get("ent_kum") or [0.0] * len(r["ein_kum"]))]
    zinsteil = [max(w - b, 0.0) for w, b in zip(r["wert"], basis)]
    ein_txt = "Eingezahlt abzgl. Entnahmen" if mit_ent else "Eingezahlt"
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=basis, name=ein_txt, stackgroup="eins", mode="lines",
        line=dict(color=FARBEN["ein"], width=2, shape="spline", smoothing=0.3),
        fillcolor=_rgba(FARBEN["ein"], 0.30), hovertemplate=ein_txt + ": %{y:,.2f} €<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=x, y=zinsteil, name=zins_txt, stackgroup="eins", mode="lines",
        line=dict(color=FARBEN["zins"], width=2, shape="spline", smoothing=0.3),
        fillcolor=_rgba(FARBEN["zins"], 0.30), hovertemplate=zins_txt + ": %{y:,.2f} €<extra></extra>"))
    if mit_ent:
        fig.add_trace(go.Scatter(
            x=x, y=r["ent_kum"], name="Entnahmen gesamt", mode="lines",
            line=dict(color=FARBEN["ent"], width=2, dash="dot"),
            hovertemplate="Entnahmen gesamt: %{y:,.2f} €<extra></extra>"))
    # Jahrespunkte: Start + jedes volle Jahr + Ende, auf der Gesamtlinie
    za = zeitachse(p, r)
    idx = [0] + [z["monat"] for z in r["jahre"]]
    fig.add_trace(go.Scatter(
        x=[x[i] for i in idx], y=[r["wert"][i] for i in idx], name="Kontostand", mode="markers",
        marker=dict(size=8, color=FARBEN["text"], line=dict(width=2, color=FARBEN["flaeche"])),
        hovertemplate="<b>Kontostand: %{y:,.2f} €</b><extra></extra>", showlegend=False))
    # direkte Beschriftung nur Start und Ende
    ende = za[-1]
    fig.add_annotation(x=x[-1], y=r["wert"][-1], text=f"<b>{_de(r['wert'][-1], 0)} €</b><br>"
                       f"<span style='color:{FARBEN['text2']}'>{ende['datum'].strftime('%d.%m.%Y')}</span>",
                       showarrow=False, xanchor="right", yanchor="bottom", yshift=10, align="right",
                       font=dict(size=13, color=FARBEN["text"]))
    if r["start"] > 0:
        fig.add_annotation(x=x[0], y=r["wert"][0], text=f"{_de(r['start'], 0)} €<br>"
                           f"<span style='color:{FARBEN['text2']}'>{sd.strftime('%d.%m.%Y')}</span>",
                           showarrow=False, xanchor="left", yanchor="top", xshift=6, yshift=-10, align="left",
                           font=dict(size=11, color=FARBEN["text"]))
    jahre = len(r["wert"]) / 12
    schritt = 1 if jahre <= 12 else (2 if jahre <= 24 else 5)
    tick_i = list(range(0, len(r["wert"]), 12 * schritt))
    tick_x = [x[i] for i in tick_i]
    tick_t = [x[i].strftime("%Y") for i in tick_i]
    fig.update_layout(
        height=360, margin=dict(l=8, r=12, t=36, b=8), separators=",.",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=FARBEN["text2"], size=12),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#1a1a19", bordercolor="#3a3a37", font=dict(color=FARBEN["text"], size=12)),
        legend=dict(orientation="h", x=0, y=1.12, xanchor="left", font=dict(color=FARBEN["text"]),
                    bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(showgrid=False, linecolor=FARBEN["grid"], ticks="outside", tickcolor=FARBEN["grid"],
                   tickmode="array", tickvals=tick_x, ticktext=tick_t, hoverformat="%d.%m.%Y", fixedrange=True,
                   range=[x[0] - datetime.timedelta(days=40), x[-1] + datetime.timedelta(days=40)]),
        yaxis=dict(gridcolor=FARBEN["grid"], zeroline=False, tickformat=",.0f", ticksuffix=" €", rangemode="tozero",
                   fixedrange=True, side="right"),
    )
    return fig


# ===========================================================================
# Oberflaeche
# ===========================================================================
FORM_CSS = """<style>
/* Breite Bildschirme: Eingabekarten nebeneinander (so viele, wie Platz ist), sonst untereinander */
@media (min-width: 1100px) {
  .st-key-zr_form { display: grid !important; grid-template-columns: repeat(auto-fit, minmax(480px, 1fr));
                    gap: 0.7rem 16px !important; align-items: start; }
  .st-key-zr_form > *:not([class*="st-key-zr_karte_"]):not(:has([class*="st-key-zr_karte_"])) { grid-column: 1 / -1; }
}
/* Zinsrechner: Abschnitte als Karten, Feldbeschriftungen einheitlich und klein */
.st-key-zr_form [data-testid="stVerticalBlockBorderWrapper"],
.st-key-zr_form [class*="st-key-zr_karte_"] {
    background: #12151c; border: 1px solid #2c313d !important; border-radius: 16px !important;
}
.zr-kopf { display: flex; gap: 12px; align-items: center; margin: 2px 0 8px; padding-bottom: 10px;
           border-bottom: 1px solid #2c313d; }
.zr-symbol { font-size: 1.35rem; width: 38px; height: 38px; border-radius: 10px; background: #1d2330;
             display: flex; align-items: center; justify-content: center; flex: 0 0 38px; }
.zr-titel { font-size: 1.05rem; font-weight: 700; color: #ffffff; letter-spacing: .2px; line-height: 1.2; }
.zr-text { font-size: .8rem; color: #a9a79c; margin-top: 2px; line-height: 1.25; }
/* Dropdown-Beschriftungen hier wie normale Feldbeschriftungen (nicht wie Ueberschriften) */
.st-key-zr_form [data-testid="stSelectbox"] label,
.st-key-zr_form [data-testid="stSelectbox"] label p,
.st-key-zr_form [data-testid="stWidgetLabel"] p {
    font-family: inherit !important; font-size: .85rem !important; font-weight: 500 !important;
    letter-spacing: normal !important; text-transform: none !important; text-shadow: none !important;
    color: #d6d4cc !important;
}
.st-key-zr_form [data-testid="stSelectbox"] label { margin: 0 0 4px 0 !important; }
.st-key-zr_form [data-testid="stSelectbox"] > div,
.st-key-zr_form [data-testid="stSelectbox"] [data-baseweb="select"] {
    outline: 1px solid #3a4152 !important; box-shadow: none !important; animation: none !important;
    border-radius: 10px !important;
}
/* ---- Alle bearbeitbaren Felder gleich deutlich als Eingabefeld zeigen ---- */
.st-key-zr_form [data-baseweb="input"],
.st-key-zr_form [data-testid="stNumberInputContainer"] {
    background: #0b0d12 !important; border: 1.5px solid #4a5468 !important; border-radius: 10px !important;
    box-shadow: none !important;
}
.st-key-zr_form [data-baseweb="input"] input { color: #ffffff !important; font-weight: 600 !important; }
.st-key-zr_form [data-baseweb="input"]:focus-within,
.st-key-zr_form [data-testid="stNumberInputContainer"]:focus-within,
.st-key-zr_form [data-testid="stSelectbox"] > div:focus-within {
    border-color: #3987e5 !important; outline-color: #3987e5 !important;
    box-shadow: 0 0 0 3px rgba(57,135,229,.25) !important;
}
/* Plus/Minus ausblenden: auf dem iPhone tippt man den Wert ein (Zahlentastatur) - mehr Platz fuer die Zahl */
.st-key-zr_form [data-testid="stNumberInputStepUp"],
.st-key-zr_form [data-testid="stNumberInputStepDown"] { display: none !important; }
.st-key-zr_form [data-testid="stSelectbox"] > div,
.st-key-zr_form [data-testid="stSelectbox"] [data-baseweb="select"] { background: #0b0d12 !important; }
.st-key-zr_form [data-testid="stSelectbox"] > div { outline: 1.5px solid #4a5468 !important; }
/* berechnetes Feld: gestrichelt + Akzentfarbe -> "nicht eingeben, wird ausgerechnet" */
.st-key-zr_form [data-baseweb="input"]:has(input:disabled) {
    border: 1.5px dashed #d95926 !important; background: rgba(217,89,38,.08) !important;
}
.st-key-zr_form [data-baseweb="input"] input:disabled { color: #f0a27f !important; -webkit-text-fill-color: #f0a27f !important; }
/* Beschriftungen gleich hoch, damit Felder nebeneinander auf einer Linie liegen
   (Dropdown-Labels haben app-weit einen eigenen Abstand nach oben - hier angleichen) */
.st-key-zr_form [data-testid="stWidgetLabel"],
.st-key-zr_form [data-testid="stSelectbox"] label {
    display: flex !important; align-items: flex-end !important; min-height: 1.5rem !important;
    margin: 0 0 4px 0 !important; padding: 0 !important; width: auto !important;
}
.st-key-zr_form [data-testid="stSelectbox"],
.st-key-zr_form [data-testid="stNumberInput"],
.st-key-zr_form [data-testid="stTextInput"],
.st-key-zr_form [data-testid="stDateInput"] { margin-top: 0 !important; padding-top: 0 !important; }
.zr-hilfe { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 12px; font-size: 0.8rem; color: #c3c2b7;
            margin: 0 0 4px; padding: 10px 12px; border-radius: 12px; background: #12151c; border: 1px solid #2c313d; }
.zr-hilfe span { display: inline-flex; align-items: center; gap: 6px; }
.zr-muster { display: inline-block; width: 26px; height: 16px; border-radius: 5px; background: #0b0d12;
             border: 1.5px solid #4a5468; }
.zr-muster.calc { border: 1.5px dashed #d95926; background: rgba(217,89,38,.08); }
/* Paare (Wert + Einheit) auch auf dem iPhone nebeneinander lassen */
.st-key-zr_form [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 10px !important; }
.st-key-zr_form [data-testid="stHorizontalBlock"] > div { min-width: 0 !important; flex: 1 1 0 !important; }
</style>"""


def _kopf(symbol, titel, text=""):
    return (f'<div class="zr-kopf" style="margin-top:18px"><span class="zr-symbol">{symbol}</span><div>'
            f'<div class="zr-titel">{titel}</div>' + (f'<div class="zr-text">{text}</div>' if text else "")
            + "</div></div>")


def _phasen_setzen(session_state, feld, liste):
    """Phasenliste [(jahre, betrag)] als Text speichern und die Eingabefelder neu aufbauen."""
    session_state[f"zr_{feld}"] = phasen_text([(j, b) for j, b in liste if j > 0])
    session_state[f"zr_{feld}_ver"] = session_state.get(f"zr_{feld}_ver", 0) + 1
    session_state[f"zr_{feld}_leer"] = not liste          # bewusst leer -> kein Beispiel nachladen


def _phasen_editor(st, pd, feld, titel, hilfe, beispiel, p):
    """Plan in Phasen (Jahre x Euro pro Monat): je Phase eine Zeile mit zwei Feldern und
    einem eigenen 🗑️-Knopf, dazu „Phase hinzufügen“ und „Alle löschen“. -> Text fuer p[feld]."""
    ss = st.session_state
    aktiv = st.toggle(titel, value=bool(ss.get(f"zr_{feld}")), key=f"zr_{feld}_an", help=hilfe)
    if not aktiv:
        ss[f"zr_{feld}"] = ""
        ss.pop(f"zr_{feld}_leer", None)
        return ""
    liste = [(mo / 12, b) for mo, b in phasen(ss.get(f"zr_{feld}"))]
    if not liste and not ss.get(f"zr_{feld}_leer"):
        liste = [(mo / 12, b) for mo, b in phasen(beispiel)]   # beim Einschalten ein Beispiel
    ver = ss.get(f"zr_{feld}_ver", 0)

    def loeschen(i):
        rest = [x for k, x in enumerate(_aktuell()) if k != i]
        _phasen_setzen(ss, feld, rest)

    def hinzufuegen():
        _phasen_setzen(ss, feld, _aktuell() + [(1.0, 0.0)])

    def alle_loeschen():
        _phasen_setzen(ss, feld, [])

    def _aktuell():
        aus = []
        for i, (j, b) in enumerate(liste):
            jj = ss.get(f"zr_{feld}_j_{ver}_{i}", j)
            bb = ss.get(f"zr_{feld}_b_{ver}_{i}", b)
            aus.append((float(jj or 0), float(bb or 0)))
        return aus

    if not liste:
        st.caption("Noch keine Phase – unten „➕ Phase hinzufügen“ antippen.")
    for i, (j, b) in enumerate(liste):
        c1, c2, c3 = st.columns([2, 3, 1], vertical_alignment="bottom")
        c1.number_input("Jahre" if i == 0 else f"Jahre ({i + 1}.)", min_value=0.0833, max_value=100.0,
                        value=float(max(j, 0.0833)), step=0.5, format="%.2g", key=f"zr_{feld}_j_{ver}_{i}",
                        label_visibility="visible" if i == 0 else "collapsed",
                        help="Dauer dieser Phase (0,5 = 6 Monate)")
        c2.number_input("€ pro Monat" if i == 0 else f"€ pro Monat ({i + 1}.)", min_value=0.0, value=float(b),
                        step=50.0, format="%.2f", key=f"zr_{feld}_b_{ver}_{i}",
                        label_visibility="visible" if i == 0 else "collapsed")
        c3.button("🗑️", key=f"zr_{feld}_del_{ver}_{i}", on_click=loeschen, args=(i,),
                  help=f"Phase {i + 1} löschen", width="stretch")
    k1, k2 = st.columns(2)
    k1.button("➕ Phase hinzufügen", key=f"zr_{feld}_neu", on_click=hinzufuegen, width="stretch")
    k2.button("🧹 Alle löschen", key=f"zr_{feld}_leeren", on_click=alle_loeschen, width="stretch",
              disabled=not liste)

    text = phasen_text([(jj, bb) for jj, bb in _aktuell() if jj > 0])
    ss[f"zr_{feld}"] = text
    zeilen = phasen_zeitraeume(dict(p, **{feld: text}), feld)
    if zeilen:
        st.caption(" · ".join(f"{a.strftime('%d.%m.%Y')}–{e.strftime('%d.%m.%Y')}: {_de(x)} €/Monat"
                              for a, e, x in zeilen) + " · danach 0 €")
    return text


def init_werte(session_state, query_params, gespeichert=None, null=False):
    """Erstbelegung beim Oeffnen der Ansicht (setzt zr_*-Schluessel in session_state).
    - Permanentlink MIT Werten (?a=...&z=...): der Link legt die Variante komplett fest
      (fehlende Felder = STANDARD, wie beim Erzeugen des Links) - ueberschreibt alles.
    - Sonst (kein Link oder nur ?ansicht=zins): vorhandene Sitzungswerte bleiben; fehlende
      kommen aus den gemerkten Eingaben (gespeichert, {"zr_a": ...}), sonst Standard
      (null=True: neuer Benutzer, Zahlenfelder 0). -> True, wenn ein Link galt."""
    url = {k: query_params.get(k) for k in STANDARD if k in query_params}
    if url:
        p0 = aus_url(url)
        p0["dy"] = max(float(p0["dy"]), 0.0)
        for k, v in p0.items():
            session_state[f"zr_{k}"] = v
        return True
    gespeichert = gespeichert or {}
    quelle = {}
    for k in STANDARD:
        key = f"zr_{k}"
        if session_state.get(key) is not None:          # Sitzung (auch frisch vorbelegt) zuerst
            quelle[k] = session_state[key]
        elif gespeichert.get(key) is not None:
            quelle[k] = gespeichert[key]
    p0 = aus_url(quelle, standard_werte(null))           # wie ein Link geprueft und begrenzt
    p0["dy"] = max(float(p0["dy"]), 0.0)
    for k, v in p0.items():
        session_state[f"zr_{k}"] = v
    for key, std in EXTRA_FELDER.items():
        if key in session_state:
            continue
        wert = gespeichert.get(key)
        if isinstance(wert, (int, float)) and not isinstance(wert, bool) and math.isfinite(wert) and wert >= 0:
            session_state[key] = float(wert)
        elif key == "zr_wg":
            session_state[key] = 0.0 if null else std
    return False


def render(basis_url="", gespeichert=None, null=False):
    """gespeichert: gemerkte Eingaben des Benutzers ({"zr_a": ...}); null=True: neuer
    (normaler) Benutzer - ohne gemerkte Werte starten alle Zahlenfelder bei 0."""
    import streamlit as st
    import pandas as pd

    # Erstaufruf: Link > Sitzung > gemerkte Eingaben > Standard (danach gelten die Eingaben)
    if not st.session_state.get("zr_init"):
        init_werte(st.session_state, st.query_params, gespeichert, null)
        st.session_state["zr_init"] = True

    st.markdown(FORM_CSS, unsafe_allow_html=True)
    form = st.container(key="zr_form")

    def karte(schluessel, symbol, titel, text=""):
        k_ = form.container(border=True, key=f"zr_karte_{schluessel}")
        k_.markdown(f'<div class="zr-kopf"><span class="zr-symbol">{symbol}</span><div><div class="zr-titel">{titel}</div>'
                    + (f'<div class="zr-text">{text}</div>' if text else "") + "</div></div>",
                    unsafe_allow_html=True)
        return k_

    form.markdown('<div class="zr-hilfe"><span><i class="zr-muster"></i>antippen &amp; Wert eintippen</span>'
                  '<span><i class="zr-muster calc"></i>wird berechnet</span>'
                  '<span>⌄ antippen = auswählen</span><span>⚡ Ergebnis sofort</span></div>', unsafe_allow_html=True)

    # 1) Was berechnen?
    k_ziel = karte("ziel", "🎯", "Was soll berechnet werden?", "Die gewählte Größe wird aus allen anderen Angaben ermittelt")
    calc = k_ziel.selectbox("Gesuchte Größe", list(ZIEL_FELDER), format_func=ZIEL_FELDER.get, key="zr_calc")
    p = {"calc": calc}
    if calc == "e":
        # Kann-Feld: wird ein Zielwert eingetragen, rechnet der Rechner den noetigen Zinssatz
        # fuer die eingestellte Laufzeit aus (sonst normal: Endkapital aus dem Zinssatz)
        zielwert = k_ziel.number_input("🎯 Zielwert (€) – optional", min_value=0.0, max_value=1e12, value=None,
                                       step=1000.0, format="%.2f", key="zr_zielwert",
                                       placeholder="leer lassen = Endkapital berechnen",
                                       help="Trag ein, wie viel am Ende da sein soll – der nötige Zinssatz wird "
                                            "dann passend zur Laufzeit automatisch berechnet.")
        if zielwert:
            calc = "z"
            p = {"calc": "z", "e": float(zielwert)}
            k_ziel.caption("➜ Zinssatz wird aus Zielwert und Laufzeit berechnet (Feld unten gestrichelt). "
                           "Zielwert leeren, um wieder selbst einen Zinssatz einzugeben.")
        else:
            p["e"] = float(st.session_state.get("zr_e", 0.0))
    else:
        p["e"] = float(k_ziel.number_input("Gewünschtes Endkapital (€)", 0.0, 1e12, step=1000.0, format="%.2f",
                                           key="zr_e"))

    berechnet_platz = {}

    def zahl(feld, label, mini, maxi, step, fmt="%.2f", hilfe=None, spalte=st):
        if calc == feld:
            berechnet_platz[feld] = (spalte.empty(), label)
            return float(st.session_state.get(f"zr_{feld}", STANDARD[feld]))
        return float(spalte.number_input(label, mini, maxi, step=step, format=fmt, key=f"zr_{feld}", help=hilfe))

    # 2) Kapital & Einzahlungen
    k_ein = karte("ein", "💰", "Kapital & Einzahlungen", "Startbetrag und regelmäßige Sparrate")
    p["a"] = zahl("a", "Anfangskapital (€)", 0.0, 1e10, 1000.0, spalte=k_ein)
    c1, c2 = k_ein.columns(2)
    p["s"] = zahl("s", "Sparrate (€)", 0.0, 1e9, 25.0, spalte=c1)
    p["si"] = c2.selectbox("Intervall", list(INTERVALLE), format_func=INTERVALLE.get, key="zr_si")
    c3, c4 = k_ein.columns(2)
    p["dy"] = zahl("dy", "Dynamik (%)", 0.0, 100.0, 0.5, "%.2f", "Erhöhung der Sparrate", spalte=c3)
    p["dya"] = c4.selectbox("Erhöhung", ["j", "i"], key="zr_dya",
                            format_func={"j": "jährlich", "i": "je Intervall"}.get)
    p["ea"] = k_ein.selectbox("Zahlung", ["v", "n"], key="zr_ea",
                              format_func={"v": "vorschüssig – am Monatsanfang", "n": "nachschüssig – am Monatsende"}.get)

    # 3) Verzinsung
    k_zins = karte("zins", "📈", "Verzinsung", "Zinssatz, Gutschrift und Steuer")
    c7, c8 = k_zins.columns(2)
    p["z"] = zahl("z", "Zinssatz (% p.a.)", -99.0, 100.0, 0.25, "%.3f", spalte=c7)
    p["zp"] = c8.selectbox("Zinsgutschrift", list(INTERVALLE), format_func=INTERVALLE.get, key="zr_zp")
    p["ze"] = k_zins.selectbox("Zinseszins", [1, 0], key="zr_ze",
                               format_func={1: "Ja – Zinsen werden mitverzinst", 0: "Nein – Zinsen werden ausgezahlt"}.get)
    with k_zins.expander("💶 Steuer auf Zinsen (optional)", expanded=bool(float(st.session_state.get("zr_st") or 0))):
        c13, c14 = st.columns(2)
        p["st"] = float(c13.number_input("Steuersatz (%)", 0.0, 60.0, step=0.5, format="%.3f", key="zr_st",
                                         help=f"Abgeltungsteuer + Soli = {ABGELTUNG} % (0 = nicht berücksichtigen)"))
        p["fb"] = float(c14.number_input("Freibetrag/Jahr (€)", 0.0, 1e6, step=100.0, format="%.0f", key="zr_fb",
                                         help="Sparerpauschbetrag: 1.000 € (Ehepaare 2.000 €)"))

    # 4) Laufzeit
    k_zeit = karte("zeit", "⏳", "Laufzeit", "Ab wann und wie lange")
    sd_wert = startdatum({"sd": st.session_state.get("zr_sd"), "am": st.session_state.get("zr_am")})
    if "zr_sd_d" not in st.session_state:
        st.session_state["zr_sd_d"] = sd_wert
    sd = k_zeit.date_input("Startdatum", key="zr_sd_d", format="DD.MM.YYYY",
                           help="Ab hier wird gerechnet – Tabelle, Chart und PDF zeigen die echten Daten")
    p["sd"] = "" if sd == datetime.date.today() else sd.isoformat()
    st.session_state["zr_sd"] = p["sd"]
    p["am"] = ""
    c9, c10 = k_zeit.columns(2)
    if calc == "n":
        berechnet_platz["n"] = (c9.empty(), "Ansparzeit")
        p["n"], p["ne"] = st.session_state.get("zr_n", 10), st.session_state.get("zr_ne", "j")
    else:
        p["n"] = int(c9.number_input("Ansparzeit", 0, 1200, step=1, key="zr_n"))
        p["ne"] = c10.selectbox("in", ["j", "m"], key="zr_ne", format_func={"j": "Jahren", "m": "Monaten"}.get)
    c11, c12 = k_zeit.columns(2)
    p["f"] = int(c11.number_input("Danach ruhen lassen", 0, 1200, step=1, key="zr_f",
                                  help="Festlegungsfrist: nach der Ansparzeit keine Raten mehr, das Kapital wird "
                                       "weiter verzinst"))
    p["fe"] = c12.selectbox("in ", ["j", "m"], key="zr_fe", format_func={"j": "Jahren", "m": "Monaten"}.get)

    # 5) Plaene
    k_plan = karte("plan", "🗓️", "Pläne in Phasen (optional)", "Sparrate oder Entnahme je Zeitraum unterschiedlich")
    with k_plan:
        p["sp"] = _phasen_editor(st, pd, "sp", "📥 Sparplan in Phasen (statt fester Sparrate)",
                                 "Z. B. 2 Jahre 200 €/Monat, danach 3 Jahre 500 €/Monat – ersetzt Sparrate, Intervall "
                                 "und Dynamik. Die Laufzeit reicht mindestens bis zum Ende des Plans.", "2x200,3x500", p)
        p["ep"] = _phasen_editor(st, pd, "ep", "📤 Entnahmeplan (monatliche Entnahme in Phasen)",
                                 "Z. B. im 1. Jahr 1.000 €/Monat, die nächsten 3 Jahre 500 €/Monat, danach nichts. "
                                 "Entnommen wird zum Monatsanfang (vorschüssig) bzw. -ende.", "1x1000,3x500", p)
    if p["sp"] and calc in ("s", "dy"):
        st.warning("Mit Sparplan in Phasen lassen sich Sparrate/Dynamik nicht berechnen – bitte Plan ausschalten "
                   "oder eine andere Größe berechnen.")

    q, r, hinweis = loese(p)
    # berechneten Wert direkt im (gestrichelten) Feld anzeigen
    for feld, (platz, label) in berechnet_platz.items():
        if feld == "n":
            wert_txt = "= " + _laufzeit_text(_monate(q["n"], q["ne"]))
        elif feld in ("z", "dy"):
            wert_txt = f"= {_de(float(q[feld]), 3)} %"
        else:
            wert_txt = f"= {_de(float(q[feld]))} €"
        platz.text_input(label + " – berechnet", wert_txt, disabled=True, key=f"zr_dis_{feld}_{wert_txt}")
    # berechneten Wert merken (Anzeige + Link)
    if calc != "e":
        st.session_state[f"zr_{calc}"] = q[calc] if calc != "n" else q["n"]
        if calc == "n":
            st.session_state["zr_ne"] = "m"
    else:
        st.session_state["zr_e"] = round(r["end"], 2)     # Vorbelegung, falls danach etwas anderes berechnet wird

    st.markdown(_kopf("📊", "Ergebnis"), unsafe_allow_html=True)
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
    if r.get("entnommen"):
        k5, k6 = st.columns(2)
        k5.metric("Entnahmen gesamt", f"{_de(r['entnommen'])} €")
        if r.get("leer_monat"):
            k6.metric("Kapital aufgebraucht am", plus_monate(startdatum(q), r["leer_monat"]).strftime("%d.%m.%Y"))
        else:
            k6.metric("Kapital reicht", "✓ bis zum Ende")
    if calc != "e":
        st.caption(f"Endkapital damit: {_de(r['end'])} €")

    analyse = None
    if r.get("entnommen"):
        st.markdown(_kopf("🛟", "Entnahme & Zinsen", "Welcher Zinssatz deckt die Entnahmen – und wann wächst das Kapital?"),
                    unsafe_allow_html=True)
        st.session_state.setdefault("zr_wg", 0.0 if null else 2.0)
        wg = float(st.number_input("Gewünschtes Wachstum zusätzlich zur Entnahme (% p.a.)", 0.0, 50.0, step=0.5,
                                   format="%.1f", key="zr_wg",
                                   help="Wie stark das Kapital trotz Entnahme noch wachsen soll")) / 100.0
        analyse = entnahme_analyse(q, r, wg)
        st.markdown(analyse_html(analyse), unsafe_allow_html=True)

    try:
        st.plotly_chart(chart(q, r), width="stretch", config={"displayModeBar": False}, key="zr_chart")
    except Exception as ex:
        st.caption(f"Chart nicht verfügbar: {ex}")

    za = zeitachse(q, r)
    st.markdown(_kopf("📅", "Entwicklung", "Kontostand jeweils am Jahrestag"), unsafe_allow_html=True)
    st.markdown('<div tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)" style="overflow-x:auto">'
                + tabelle_html(za, r) + '</div>', unsafe_allow_html=True)

    # Permanentlink: Browser-Adresse zeigt immer die aktuelle Variante
    params = in_url(q)
    try:
        st.query_params.from_dict(params)
    except Exception:
        pass
    from urllib.parse import urlencode
    link = (basis_url.rstrip("/") + "/?" if basis_url else "?") + urlencode(params)
    st.markdown(_kopf("🔗", "Permanentlink", "Genau diese Variante wieder aufrufen oder teilen"), unsafe_allow_html=True)
    st.code(link, language=None, wrap_lines=True)   # umbrechen statt seitlich scrollen (Tastatur/axe)
    st.caption("Die Adresse im Browser ist jetzt genau dieser Link – als Lesezeichen speichern oder teilen; beim "
               "Öffnen erscheint der Rechner mit allen Werten.")
    st.download_button("📄 Ergebnis als PDF", data=pdf_bericht(q, r, hinweis, link, analyse),
                       file_name="Zinsrechner.pdf", mime="application/pdf", width="stretch", key="zr_pdf")
