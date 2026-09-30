"""
Portfolio-Planer - OBERFLAECHE (Streamlit).

Wird von app.py als Ansicht "💼 Portfolio-Planer" aufgerufen:
    planer_ui.render(hilfen)
hilfen = {"suche_instrument", "get_kurshistorie", "gh_read", "gh_write",
          "gh_read_taeglich", "heute", "benchmarks"}  - die vorhandenen Funktionen der App,
damit Kursdaten, Suche und GitHub-Speicher nicht doppelt implementiert werden.

Aufbau: Rahmen/Methode -> 4 KPI-Karten -> Bereichswahl -> ein Bereich.
Die KPI-Karten werden als Platzhalter angelegt und erst NACH den Eingaben des
Bereichs gefuellt - so zeigen sie immer den aktuellen Stand.

Alle Zahlen: Szenariorechnung, keine Prognose, vor Steuern.
"""
import copy
import datetime
import hashlib
import html
import json
import math
import zlib

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import planer_daten as D
import planer_engine as E

PFAD_SZENARIEN = "state/planer/szenarien.json"
QUALITAET_DETAIL_TEILE = 32          # wie qualitaet_agent.DETAIL_TEILE
HIST_CACHE_SEK = 6 * 3600

# Navigation: 6 Hauptbereiche in Arbeitsreihenfolge, darunter Unterseiten
HAUPT = ["🧩 Portfolio", "⚖️ Gewichtung", "📈 Ergebnis", "⚠️ Risiko", "🔬 Analyse", "🗂️ Daten"]
UNTER = {
    "🧩 Portfolio": ["Bausteine", "Aufteilung"],
    "⚖️ Gewichtung": [],
    "📈 Ergebnis": ["Wachstum", "Ziel", "Szenarien", "Entnahme"],
    "⚠️ Risiko": ["Konzentration", "Sensitivität", "Stress & Reserve"],
    "🔬 Analyse": ["Aktienkorb", "Wikifolios"],
    "🗂️ Daten": ["Annahmen & Quellen", "Gespeicherte Modelle"],
}
BEREICHE = HAUPT      # Kompatibilitaet

FARBEN = ["#4C9AFF", "#16C784", "#F5B942", "#EA3943", "#A78BFA", "#22D3EE", "#F472B6", "#FB923C",
          "#A3E635", "#94A3B8", "#FDE047", "#2DD4BF", "#C084FC", "#F87171"]

QUELLEN = {"historisch": "Kurshistorie (Ist)", "manualScenario": "Eigene Annahme", "historical5Y": "Historisch 5 J.", "historical10Y": "Historisch 10 J.",
           "fundamentalModel": "Fundamental-Modell", "analystInput": "Analysten-Input", "bear": "Bear",
           "base": "Base", "bull": "Bull", "custom": "Custom"}

HINWEIS = "Szenariorechnung · keine Prognose · vor Steuern"

CSS = """
<style>
.pl-phase { font-size: 0.72rem; font-weight: 800; letter-spacing: 1.4px; text-transform: uppercase; color: #FFFFFF;
            margin: 14px 0 4px; padding-bottom: 5px; border-bottom: 1px solid rgba(255, 255, 255, 0.25); }
.pl-hinweis { font-size: 0.72rem; color: var(--label, #8A9099); margin: -2px 0 10px 2px;
              letter-spacing: 0.3px; }
.pl-badge { display: inline-block; font-size: 0.68rem; font-weight: 700; padding: 2px 7px;
            border-radius: 999px; margin: 1px 4px 1px 0; white-space: nowrap; }
.pl-warn { background: rgba(245, 185, 66, 0.14); color: #F5B942; border: 1px solid rgba(245, 185, 66, 0.4); }
.pl-info { background: rgba(76, 154, 255, 0.12); color: #8DBBFF; border: 1px solid rgba(76, 154, 255, 0.35); }
.pl-gut { color: #16C784; } .pl-schlecht { color: #EA3943; }
.q-kpi-v span.pl-gut, .q-kpi-v span.pl-schlecht { font-size: inherit; font-weight: 800; }
.q-kpi-v span.pl-gut { color: #16C784; } .q-kpi-v span.pl-schlecht { color: #EA3943; }
.pl-sub { font-size: 0.72rem; color: var(--label, #8A9099); font-weight: 600; }
.pl-zeile { font-size: 0.8rem; color: #D6D9DE; margin: 2px 0 12px 2px; line-height: 1.5; }
.q-kpi-v.pl-klein { font-size: 1.05rem; }
.pt.ue td.pt-wert.ue-fix { min-width: 110px; max-width: 170px; }
.pl-formhinweis { font-size: 0.8rem; color: #D6D9DE; background: rgba(76, 154, 255, 0.10);
                  border: 1px solid rgba(76, 154, 255, 0.35); border-radius: 8px; padding: 7px 10px; margin: 4px 0 8px; }
/* Formular-Buttons klar beschriftet und farbig statt weisser Flaeche */
[data-testid="stFormSubmitButton"] button {
    background: #16305A !important; border: 1px solid rgba(255, 255, 255, 0.8) !important; min-height: 44px;
    box-shadow: 0 0 6px rgba(255, 255, 255, 0.5), 0 0 16px rgba(255, 255, 255, 0.18) !important;
}
[data-testid="stFormSubmitButton"] button, [data-testid="stFormSubmitButton"] button * {
    color: #FFFFFF !important; font-weight: 700 !important;
}
[data-testid="stColumn"]:nth-child(2) [data-testid="stFormSubmitButton"] button {
    background: #1C1F26 !important; border: 1px solid rgba(255, 255, 255, 0.6) !important;
}
[data-testid="stFormSubmitButton"] button:hover { filter: brightness(1.2); }
@media (max-width: 700px) { .pl-zeile { font-size: 0.84rem; } }
</style>
"""


# ===========================================================================
# Formatierung (deutsch, ohne falsche Praezision)
# ===========================================================================
def _de(x, dec=0):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    s = f"{x:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _eur(x, ungefaehr=True):
    if x is None:
        return "–"
    if ungefaehr:
        return f"≈ {_de(E.runden_ungefaehr(x))} €"
    return f"{_de(x)} €"


def _pct(x, dec=1, vorzeichen=False, anteil=True):
    """x als Anteil (0.1 = 10 %) bzw. mit anteil=False bereits in %."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    v = x * 100 if anteil else x
    return (("+" if vorzeichen and v > 0 else "") + _de(v, dec) + " %").replace("-", "−")


def _esc(t):
    return html.escape(str(t))


def _kacheln(eintraege, klein=False):
    zellen = "".join(
        f'<div class="q-kpi"><div class="q-kpi-l">{_esc(l)}</div>'
        f'<div class="q-kpi-v{" pl-klein" if klein else ""}">{v}</div>'
        + (f'<div class="pl-sub">{s}</div>' if s else "") + "</div>"
        for l, v, s in eintraege)
    st.markdown(f'<div class="q-kpis">{zellen}</div>', unsafe_allow_html=True)


def _tabelle(kopf, zeilen, links=(0,)):
    """HTML-Tabelle im Stil der App (.pt). Breite Tabellen scrollen am iPhone
    seitlich (.ue-wrap), die erste Spalte bleibt dabei stehen."""
    th = "".join(f'<th class="{"ue-fix" if i == 0 else ""}">{_esc(k)}</th>' for i, k in enumerate(kopf))
    umbruch = ' style="white-space:normal;min-width:220px"'
    body = []
    for n, z in enumerate(zeilen):
        tds = "".join(
            f'<td class="{("pt-wert" if i in links else "pt-num") + (" ue-fix" if i == 0 else "")}"'
            f'{umbruch if (i in links and i) else ""}>{c}</td>'
            for i, c in enumerate(z))
        body.append(f'<tr class="{"pt-zebra" if n % 2 else ""}">{tds}</tr>')
    st.markdown(f'<div class="ue-wrap"><table class="pt pt-kompakt ue"><thead><tr>{th}</tr></thead>'
                f'<tbody>{"".join(body)}</tbody></table></div>', unsafe_allow_html=True)


def _kurz_eur(x):
    """Kompakte Beschriftung: 349.667 -> 350 T€, 96.420.874 -> 96,4 Mio €."""
    a = abs(x)
    if a >= 1e9:
        return f"{_de(x / 1e9, 1)} Mrd €"
    if a >= 1e6:
        return f"{_de(x / 1e6, 1)} Mio €"
    if a >= 1e4:
        return f"{_de(x / 1e3)} T€"
    return f"{_de(x)} €"


def _layout(fig, hoehe=360, y_titel=None, legende=True, eur=True):
    fig.update_layout(
        paper_bgcolor="#000000", plot_bgcolor="#000000", height=hoehe, separators=",.",
        margin=dict(l=8, r=8, t=30 if legende else 10, b=30), font=dict(color="#D6D9DE", size=12),
        showlegend=legende, hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        xaxis=dict(showgrid=True, gridcolor="#1A1A1A", zeroline=False),
        yaxis=dict(showgrid=True, gridcolor="#1A1A1A", zeroline=False, title=y_titel,
                   tickformat=",.0f" if eur else None, side="right"),
    )
    return fig


def _chart(fig, key):
    st.plotly_chart(fig, width="stretch", key=key, config={"displayModeBar": False})


def _abschnitt(titel):
    st.markdown(f'<div class="abschnitt">{_esc(titel)}</div>', unsafe_allow_html=True)


def _hinweis(text=HINWEIS):
    st.markdown(f'<div class="pl-hinweis">{_esc(text)}</div>', unsafe_allow_html=True)


# ===========================================================================
# Modell-Zustand
# ===========================================================================
def _k(name):
    """Widget-Key mit Versionszaehler: nach Laden/Normalisieren/Optimieren
    starten alle Eingabefelder mit den Modellwerten neu."""
    return f"pl_{name}_{st.session_state.get('planer_ver', 0)}"


def _neu_zeichnen():
    st.session_state["planer_ver"] = st.session_state.get("planer_ver", 0) + 1


def _migriere(m):
    """Gespeicherte Modelle aelterer Versionen um neue Felder ergaenzen."""
    seed = D.seed_modell()
    m = copy.deepcopy(m)
    for k, v in seed.items():
        m.setdefault(k, v)
    for k, v in seed["rahmen"].items():
        m["rahmen"].setdefault(k, v)
    seed_werte = {x["assetId"]: x["value"] for x in D.SEED_ANNAHMEN if x["sourceType"] == "manualScenario"}
    for x in m["annahmen"]:
        if "auto" not in x and x.get("sourceType") == "manualScenario" and x.get("assetId") != "reserve":
            # unveraenderte Startwerte, leere Annahmen und Katalog-Vorschlaege gelten als automatisch
            x["auto"] = (x.get("value") is None or seed_werte.get(x["assetId"], object()) == x.get("value")
                         or str(x.get("notes", "")).startswith(D.VORSCHLAG["text"]))
    seed_assets = {a["id"]: a for a in seed["assets"]}
    for a in m["assets"]:
        if not a.get("enabled"):
            a["targetWeight"] = 0.0          # inaktive Bausteine haben keinen Anteil
        if a["id"] in seed_assets and not a.get("ticker") and not a.get("isin"):
            a["ticker"], a["isin"] = seed_assets[a["id"]].get("ticker"), seed_assets[a["id"]].get("isin")
        if "fixiert" not in a:
            a["fixiert"] = a["category"] == "cash"
        if "renditequelle" not in a:
            a["renditequelle"] = "historisch" if a["category"] == "wikifolio" else "annahme"
        for k, v in D._asset("x", "x", "cash", 0).items():
            a.setdefault(k, v)
    return m


def _lade_gespeichert(h):
    try:
        daten = h["gh_read"](PFAD_SZENARIEN, {}) or {}
    except Exception:
        daten = {}
    daten.setdefault("szenarien", {})
    return daten


def _norm(x):
    """Zahlen vereinheitlichen (40 und 40.0 gelten als gleich) - sonst loeste
    schon das blosse Oeffnen eines Bereichs eine Speicherung aus."""
    if isinstance(x, bool) or x is None or isinstance(x, str):
        return x
    if isinstance(x, (int, float)):
        return round(float(x), 6)
    if isinstance(x, dict):
        return {str(k): _norm(v) for k, v in x.items() if v is not None}     # fehlend == None
    if isinstance(x, (list, tuple)):
        return [_norm(v) for v in x]
    return str(x)


def _hash(m):
    return hashlib.sha1(json.dumps(_norm(m), sort_keys=True).encode()).hexdigest()


def _modell(h):
    if "planer_modell" not in st.session_state:
        daten = _lade_gespeichert(h)
        eintrag = daten["szenarien"].get(daten.get("aktiv") or "Aktuelles Modell")
        st.session_state["planer_modell"] = _migriere(eintrag["modell"]) if eintrag else D.seed_modell()
        st.session_state["planer_name"] = (daten.get("aktiv") or "Aktuelles Modell") if eintrag else None
        st.session_state.setdefault("planer_ver", 0)
        # Stand beim Laden merken - gespeichert wird erst bei einer Aenderung
        st.session_state["planer_hash"] = _hash(st.session_state["planer_modell"])
    return st.session_state["planer_modell"]


def _auto_speichern(m, h):
    """Automatische Speicherung: jede Aenderung am Modell wird ins aktive
    Szenario geschrieben (Standard "Aktuelles Modell"). Vor dem Schreiben wird
    die Datei frisch gelesen, damit andere gespeicherte Szenarien erhalten
    bleiben (z. B. von einem anderen Geraet)."""
    neu = _hash(m)
    if neu == st.session_state.get("planer_hash"):
        return st.session_state.get("planer_auto")
    name = st.session_state.get("planer_name") or "Aktuelles Modell"
    daten = _lade_gespeichert(h)
    daten["szenarien"][name] = {"modell": copy.deepcopy(m),
                                "gespeichert": datetime.datetime.now().isoformat(timespec="minutes")}
    daten["aktiv"] = name
    try:
        ok = h["gh_write"](PFAD_SZENARIEN, daten, message=f"planer: auto {name} [skip ci]")
    except Exception:
        ok = False
    if ok:
        st.session_state["planer_hash"] = neu
        st.session_state["planer_name"] = name
        st.session_state["planer_auto"] = ("ok", name, datetime.datetime.now().strftime("%H:%M"))
    else:
        st.session_state["planer_auto"] = ("fehler", name, None)
    return st.session_state["planer_auto"]


def _asset(m, aid):
    return next((a for a in m["assets"] if a["id"] == aid), None)


# ===========================================================================
# Historical Layer (echte Kursdaten, ls-tc.de ueber die App-Funktionen)
# ===========================================================================
def _waehle_treffer(treffer, begriff, wiki):
    b = begriff.strip().lower()
    for t in treffer:
        if b and b in (str(t.get("isin", "")).lower(), str(t.get("wkn", "")).lower()):
            return t
    for t in treffer:
        name = str(t.get("name", "")).lower()
        ist_wiki = str(t.get("wkn", "")).upper().startswith("LS9") or \
            "wiki" in (str(t.get("kategorie", "")) + name).lower()
        if wiki and not ist_wiki:
            continue
        if b and b in name:
            return t
    return None


def _reihen_kennzahlen(s):
    s = s.dropna()
    s = s[s > 0]
    if len(s) < 10:
        return None
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    erst, letzt = s.index[0], s.index[-1]
    jahre = (letzt - erst).days / 365.25
    if jahre <= 0:
        return None

    def cagr(n):
        if jahre < n - 0.05:
            return None
        ref = s[s.index <= letzt - pd.DateOffset(years=n)]
        basis = ref.iloc[-1] if not ref.empty else s.iloc[0]
        return float((s.iloc[-1] / basis) ** (1.0 / n) - 1.0)

    abstand = pd.Series(s.index).diff().dt.days.median() or 1.0
    je_jahr = 365.25 / max(abstand, 1.0) if abstand > 1.5 else 252.0
    log_r = (s / s.shift(1)).dropna().apply(math.log)
    vola = float(log_r.std() * math.sqrt(je_jahr)) if len(log_r) > 5 else None
    maxdd = float((s / s.cummax() - 1.0).min() * 100.0)
    s1 = s[s.index >= letzt - pd.DateOffset(years=1)]
    log1 = (s1 / s1.shift(1)).dropna().apply(math.log)
    vola1 = float(log1.std() * math.sqrt(je_jahr)) if len(log1) > 5 and jahre >= 0.95 else None
    try:
        monat = s.resample("ME").last()
    except Exception:
        monat = s.resample("M").last()
    return {
        "jahre": round(jahre, 2), "start": erst.date().isoformat(), "stand": letzt.date().isoformat(),
        "historical1Y": cagr(1), "historical3Y": cagr(3), "historical5Y": cagr(5), "historical10Y": cagr(10),
        "vola1y": vola1,
        "gesamt_cagr": float((s.iloc[-1] / s.iloc[0]) ** (1.0 / jahre) - 1.0) if jahre >= 1 else None,
        "seit_start": float(s.iloc[-1] / s.iloc[0] - 1.0),
        "vola": vola, "maxdd": maxdd,
        "monat": [(d.date().isoformat(), float(v)) for d, v in monat.dropna().items()],
    }


class _KeineDaten(Exception):
    pass


def _hist_eines(begriffe, wiki, heute_iso, _suche, _kurse, inst_id=None):
    """Wie _hist_eines_cache - Fehler werden aber NICHT zwischengespeichert,
    damit ein einmaliger Abruf-Aussetzer nicht stundenlang "fehlt" zeigt."""
    try:
        return _hist_eines_cache(begriffe, wiki, heute_iso, _suche, _kurse, inst_id)
    except _KeineDaten as e:
        return {"fehler": str(e)}
    except Exception as e:
        return {"fehler": f"Kurshistorie nicht ladbar ({e})"}


@st.cache_data(ttl=HIST_CACHE_SEK, show_spinner=False)
def _hist_eines_cache(begriffe, wiki, heute_iso, _suche, _kurse, inst_id=None):
    """Sucht das Instrument (WKN/ISIN/Name) und berechnet die Kennzahlen der
    kompletten verfuegbaren Historie. inst_id: bereits bekannte ls-tc-ID
    (aus config.BENCHMARKS). -> dict oder {"fehler": text}"""
    treffer, gefunden = [], None
    if inst_id:
        gefunden = {"instrument_id": inst_id, "name": begriffe[-1] if begriffe else "", "wkn": "", "isin": ""}
    for b in ([] if gefunden else begriffe):
        if not b:
            continue
        try:
            treffer = _suche(b) or []
        except Exception:
            treffer = []
        gefunden = _waehle_treffer(treffer, b, wiki)
        if gefunden:
            break
    if not gefunden:
        raise _KeineDaten("Instrument nicht gefunden – WKN/ISIN in den Stammdaten eintragen.")
    try:
        heute = datetime.date.fromisoformat(heute_iso)
        s = _kurse(gefunden["instrument_id"], datetime.date(2000, 1, 1), heute)
    except Exception as e:
        raise _KeineDaten(f"Kurshistorie nicht ladbar ({e})")
    if s is None or len(s) == 0:
        raise _KeineDaten("Keine Kurshistorie verfügbar.")
    k = _reihen_kennzahlen(pd.Series(s).astype(float))
    if not k:
        raise _KeineDaten("Kurshistorie zu kurz.")
    k.update({"quelle": "ls-tc.de Kurshistorie", "instrument": gefunden.get("name"),
              "wkn": gefunden.get("wkn"), "isin": gefunden.get("isin"),
              "abgerufen": datetime.datetime.now().strftime("%d.%m.%Y %H:%M")})
    return k


def _parallel(aufgaben):
    """[(schluessel, funktion, args)] parallel ausfuehren (Netzabrufe)."""
    from concurrent.futures import ThreadPoolExecutor
    try:
        from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
        ctx = get_script_run_ctx()
    except Exception:
        add_script_run_ctx, ctx = None, None

    def lauf(f, args):
        if ctx is not None and add_script_run_ctx is not None:
            try:
                import threading
                add_script_run_ctx(threading.current_thread(), ctx)
            except Exception:
                pass
        try:
            return f(*args)
        except Exception as e:
            return {"fehler": str(e)}

    with ThreadPoolExecutor(max_workers=6) as ex:
        zukunft = {k: ex.submit(lauf, f, a) for k, f, a in aufgaben}
        return {k: z.result() for k, z in zukunft.items()}


def _historie(m, h):
    """{asset_id: kennzahlen} + {korb_aktie: kennzahlen} aus echten Kursdaten."""
    heute = h["heute"].isoformat()
    aufgaben = []
    for a in m["assets"]:
        if a["category"] in ("cash", "stock_basket"):
            continue
        wiki = a["category"] == "wikifolio"
        kennung = a.get("ticker") or a.get("isin")
        begriffe = tuple(x for x in (a.get("ticker"), a.get("isin"), None if kennung else a["name"]) if x)
        inst_id = None
        if not kennung:
            # Vergleichswerte der App: Label -> ls-tc-ID (bereits gepflegt)
            for label, iid in (h.get("benchmarks") or {}).items():
                if a["name"].lower() in str(label).lower():
                    inst_id = iid
                    break
        aufgaben.append((("a", a["id"]), _hist_eines, (begriffe, wiki, heute, h["suche_instrument"],
                                                       h["get_kurshistorie"], inst_id)))
    if any(a["category"] == "stock_basket" and a.get("enabled") for a in m["assets"]):
        for k in m["korb"]:
            aufgaben.append((("k", k["id"]), _hist_eines, (tuple(x for x in (k.get("isin"),) if x), False, heute,
                                                           h["suche_instrument"], h["get_kurshistorie"])))
    erg = _parallel(aufgaben)
    assets = {k[1]: v for k, v in erg.items() if k[0] == "a"}
    korb = {k[1]: v for k, v in erg.items() if k[0] == "k"}
    return assets, korb


def _fundamentaldaten(m, h):
    """Kennzahlen der Korb-Aktien aus den Detaildateien des Qualitaets-Agenten."""
    aus, stand = {}, None
    for k in m["korb"]:
        sym = k.get("yahoo")
        if not sym:
            continue
        teil = zlib.crc32(sym.encode()) % QUALITAET_DETAIL_TEILE
        try:
            d = h["gh_read_taeglich"](f"state/qualitaet/details_{teil}.json", None) or {}
        except Exception:
            d = {}
        w = (d.get("werte") or {}).get(sym)
        if w:
            aus[k["id"]] = w
            stand = d.get("stand") or stand
    return aus, stand


def _layer(m, hist_assets, hist_korb, fund):
    """Baut den Historical Layer fuer die Engine:
    {asset_id: {historical5Y, historical10Y, fundamentalModel, jahre, maxdd, vola, ...}}"""
    historie = {}
    for aid, k in hist_assets.items():
        if k and not k.get("fehler"):
            historie[aid] = dict(k)
    korb = m["korb"]
    summe = sum(float(x["gewicht"]) for x in korb) or 1.0
    # Korb: gewichtetes Mittel der Einzel-CAGRs (nur wenn >= 50 % des Korbs Daten haben)
    eintrag = {}
    for feld in ("historical5Y", "historical10Y"):
        w_sum, v_sum = 0.0, 0.0
        for x in korb:
            k = hist_korb.get(x["id"]) or {}
            if k.get(feld) is not None:
                w_sum += float(x["gewicht"])
                v_sum += float(x["gewicht"]) * k[feld]
        if w_sum >= summe * 0.5:
            eintrag[feld] = v_sum / w_sum
    jahre = [(hist_korb.get(x["id"]) or {}).get("jahre") for x in korb]
    jahre = [j for j in jahre if j]
    if jahre:
        eintrag["jahre"] = min(sorted(jahre)[len(jahre) // 2], 10.0)     # Median, max. 10
    dds = [(hist_korb.get(x["id"]) or {}).get("maxdd") for x in korb]
    dds = [d for d in dds if d is not None]
    if dds:
        eintrag["maxdd"] = sum(dds) / len(dds) * 0.8        # Korb faellt weniger tief als der Schnitt der Einzelwerte
    fm, _ = E.korb_fundamental_rendite(korb, fund)
    if fm is not None:
        eintrag["fundamentalModel"] = fm
    if eintrag:
        eintrag["quelle"] = "Einzelwerte (ls-tc.de) / Qualitäts-Agent"
        historie["korb"] = eintrag
    return historie


def _scores(m, fund):
    """Fundamental Score je Korb-Aktie und fuer den Korb (gewichtet)."""
    je = {}
    for x in m["korb"]:
        je[x["id"]] = E.fundamental_score(fund.get(x["id"]), m["bewertungsregeln"],
                                          (m.get("manuell") or {}).get(x["id"]))
    summe, w = 0.0, 0.0
    for x in m["korb"]:
        g = je[x["id"]]["gesamt"]
        if g is not None:
            summe += g * float(x["gewicht"])
            w += float(x["gewicht"])
    korb = summe / w if w else None
    return je, korb


# ===========================================================================
# Rechnen
# ===========================================================================
def _rechne(m, historie, korb_score):
    info = E.alle_renditen(m, historie)
    r = E.rendite_map(info)
    conf = E.confidence_fuer(m, historie)
    reb = m["rebalancing"]
    zus = E.zusammenfassung(m, r, rebalancing=reb)
    scores = {"korb": korb_score}
    return {"info": info, "r": r, "conf": conf, "zus": zus, "scores": scores, "reb": reb}


# ===========================================================================
# Bereiche
# ===========================================================================
def _phase(titel):
    st.markdown(f'<div class="pl-phase">{_esc(titel)}</div>', unsafe_allow_html=True)


def _auto_aktiv(m):
    e = _entnahme_daten(m)
    return bool(e.get("aktiv", True) and e.get("rendite_quelle", "eigen") == "eigen" and e.get("auto_gewichtung"))


def _auto_gewichtung(m, R):
    """Automatische Gewichtung auf die Entnahme-Rendite (falls eingeschaltet).
    -> True, wenn Gewichte geaendert wurden"""
    if not _auto_aktiv(m):
        st.session_state.pop("planer_autogew", None)
        return False
    e = _entnahme_daten(m)
    erg = E.gewichtung_fuer_rendite(m, R["r"], float(e["rendite_pa"]) / 100.0)
    st.session_state["planer_autogew"] = erg
    if erg.get("fehler"):
        return False
    geaendert = False
    for a in m["assets"]:
        if a["id"] in erg["gewichte"] and abs(float(a.get("targetWeight") or 0) - erg["gewichte"][a["id"]]) > 0.005:
            a["targetWeight"] = round(erg["gewichte"][a["id"]], 3)
            geaendert = True
    return geaendert


def _auto_hinweis(m):
    if _auto_aktiv(m):
        st.info(f"Automatische Gewichtung ist aktiv: Die Prozente werden laufend auf "
                f"{_de(_entnahme_daten(m)['rendite_pa'], 1)} % p.a. (Rendite in der Entnahme) ausgerichtet – "
                "eigene Gewichte und Vorschläge werden überschrieben. Ausschalten unter „⚙️ Planung → Phase 2“.")


def _entnahme_daten(m):
    e = m.setdefault("entnahme", copy.deepcopy(D.ENTNAHME))
    for k, v in D.ENTNAHME.items():
        e.setdefault(k, v)
    e["start"] = "modell"             # Entnahme beginnt immer mit dem Modell-Endwert der Aufbauphase
    return e


def _rahmen(m):
    """EINE Planung in zwei Phasen: Aufbau (Startkapital, Sparrate, Jahre) und
    direkt anschliessend Entnahme aus dem Endwert. Alle Eingaben an einer Stelle."""
    rahmen = m["rahmen"]
    e = _entnahme_daten(m)
    with st.expander("⚙️ Planung: Aufbau → Entnahme", expanded=False):
        _phase("Phase 1 · Aufbau")
        c1, c2 = st.columns(2)
        rahmen["startkapital"] = float(c1.number_input("Startkapital (€)", 0.0, 1e9, float(rahmen["startkapital"]),
                                                       step=1000.0, format="%.0f", key=_k("start")))
        rahmen["sparrate_monat"] = float(c2.number_input("Monatliche Sparrate (€)", 0.0, 1e6,
                                                         float(rahmen.get("sparrate_monat") or 0.0), step=50.0,
                                                         format="%.0f", key=_k("spar")))
        c3, c4 = st.columns(2)
        rahmen["horizont_jahre"] = int(c3.number_input("Dauer Aufbau (Jahre)", 0, 40, int(rahmen["horizont_jahre"]),
                                                       key=_k("jahre"),
                                                       help="0 = kein Aufbau, die Entnahme startet sofort mit dem Startkapital"))
        rahmen["zielvermoegen"] = float(c4.number_input("Zielvermögen am Ende (€)", 0.0, 1e10,
                                                        float(rahmen["zielvermoegen"]), step=5000.0, format="%.0f",
                                                        key=_k("ziel"), help="0 = kein Ziel"))

        _phase("Phase 2 · Entnahme (ab Ende des Aufbaus)")
        e["aktiv"] = st.toggle("Entnahme einplanen", value=bool(e.get("aktiv", True)), key=_k("en_aktiv"),
                               help="Startet automatisch mit dem Modell-Endwert der Aufbauphase")
        if e["aktiv"]:
            c5, c6 = st.columns(2)
            e["monatlich"] = float(c5.number_input("Entnahme pro Monat (€, netto)", 0.0, 1e7, float(e["monatlich"]),
                                                   step=50.0, format="%.0f", key=_k("en_mon")))
            e["dauer_jahre"] = int(c6.number_input("Dauer Entnahme (Jahre)", 1, 60, int(e["dauer_jahre"]),
                                                   key=_k("en_dauer")))
            c7, c8 = st.columns(2)
            e["dynamik_pa"] = float(c7.number_input("Jährliche Erhöhung (%)", 0.0, 10.0, float(e["dynamik_pa"]),
                                                    step=0.5, key=_k("en_dyn"), help="z. B. Inflationsausgleich"))
            quellen = {"eigen": "Eigene Annahme", "modell": "Wie Aufbauphase"}
            q = c8.selectbox("Rendite in der Entnahme", list(quellen),
                             index=list(quellen).index(e.get("rendite_quelle", "eigen")),
                             format_func=quellen.get, key=_k("en_quelle"))
            e["rendite_quelle"] = q
            if q == "eigen":
                e["rendite_pa"] = float(st.number_input(
                    "Rendite p.a. in der Entnahme (%)", -20.0, 200.0, float(e["rendite_pa"]), step=0.5,
                    key=_k("en_rendite"), help="Ziel-Rendite des Portfolios in der Entnahmephase"))
                e["auto_gewichtung"] = st.toggle(
                    "Portfolio automatisch auf diese Rendite gewichten", value=bool(e.get("auto_gewichtung", False)),
                    key=_k("en_auto"),
                    help="Verteilt die Prozente im Portfolio automatisch so, dass die gewichtete Rendite p.a. genau "
                         "diesem Wert entspricht – ausgehend von einer Gleichverteilung, ausgeglichen über die "
                         "Renditen der Bausteine. Fixierte Bausteine und Reserve bleiben. Manuelle Gewichte werden "
                         "dabei überschrieben.")
            e["steuer"] = st.toggle("Abgeltungsteuer berücksichtigen (vereinfacht)", value=bool(e["steuer"]),
                                    key=_k("en_st"))
            if e["steuer"]:
                c9, c10 = st.columns(2)
                e["steuersatz"] = float(c9.number_input("Steuersatz (%)", 0.0, 60.0, float(e["steuersatz"]), step=0.5,
                                                        key=_k("en_satz"),
                                                        help="Abgeltungsteuer + Soli, ohne Kirchensteuer"))
                e["freibetrag"] = float(c10.number_input("Freibetrag pro Jahr (€)", 0.0, 1e5, float(e["freibetrag"]),
                                                         step=100.0, format="%.0f", key=_k("en_frei"),
                                                         help="Sparerpauschbetrag – bitte aktuellen Wert prüfen"))

        _phase("Weitere Einstellungen")
        rahmen["kosten_beruecksichtigen"] = st.toggle(
            "Kosten berücksichtigen (TER und Performance Fee, soweit hinterlegt)",
            value=bool(rahmen.get("kosten_beruecksichtigen")), key=_k("kosten"))
        arten = list(D.REBALANCING_ARTEN)
        c11, c12 = st.columns(2)
        art = c11.selectbox("Rebalancing", arten, index=arten.index(m["rebalancing"].get("art", "keins")),
                            format_func=D.REBALANCING_ARTEN.get, key=_k("reb"))
        m["rebalancing"]["art"] = art
        if art == "schwelle":
            m["rebalancing"]["schwelle_relativ"] = float(c12.number_input(
                "Band (± % relativ zum Zielgewicht)", 1.0, 100.0,
                float(m["rebalancing"].get("schwelle_relativ", 25.0)), step=2.5, key=_k("band"),
                help="25 % relativ: Zielgewicht 10 % → Band 7,5–12,5 %"))
        methoden = list(D.METHODEN)
        wahl = st.selectbox("Renditequelle der Rechnung", methoden, index=methoden.index(rahmen["methode"]),
                            format_func=D.METHODEN.get, key=_k("methode"),
                            help="Standard „Meine Annahmen“ = Spalte „Annahme %“ bzw. Ist-Werte im Portfolio")
        rahmen["methode"] = wahl
        if rahmen["methode"] == "szenario":
            sz = ["bear", "base", "bull", "custom"]
            rahmen["szenario"] = st.selectbox("Szenario", sz, index=sz.index(rahmen.get("szenario", "base")),
                                              format_func=str.capitalize, key=_k("szenario"))
        if rahmen["methode"] in ("historical5Y", "historical10Y", "fundamentalModel"):
            st.caption("Wo für diese Quelle keine Daten vorliegen, gilt die eigene Annahme.")
        st.caption("Renditen sind effektive Jahresrenditen vor Steuern. Die Nachkaufreserve nimmt am "
                   "Rebalancing nicht teil.")

def _kpis(platz, m, R):
    z = R["zus"]
    rahmen = m["rahmen"]
    jahre_n = int(rahmen.get("horizont_jahre") or 0)
    ziel = float(rahmen.get("zielvermoegen") or 0)
    diff = z["differenz"]
    farbe = "pl-gut" if diff >= 0 else "pl-schlecht"
    w = E.gewichte(m)
    port_r = sum(g * R["r"].get(i, 0.0) for i, g in w.items())      # Portfoliorendite p.a. (gewichtet)
    with platz.container():
        if jahre_n <= 0:
            k1 = ("Aufbau", "–", "keine Aufbauphase (0 Jahre)")
            k2 = ("Portfolio-Rendite p.a.", _pct(port_r), "gewichtet · " + D.METHODEN[rahmen["methode"]])
            k3 = ("Startkapital", _eur(z["endwert"]), "Entnahme startet sofort")
        else:
            k1 = ("Benötigte Rendite p.a.", _pct(z["erforderliche_cagr"]) if ziel > 0 else "–",
                  f'{_de(rahmen["startkapital"])} € → {_de(ziel)} € in {jahre_n} J.' if ziel > 0 else "kein Ziel gesetzt")
            k2 = ("Modellierte Rendite p.a.", _pct(z["modell_cagr"]), D.METHODEN[rahmen["methode"]])
            k3 = ("Modell-Endwert", _eur(z["endwert"]), f'nach {jahre_n} J.' + (f' · Ziel {_de(ziel)} €' if ziel > 0 else ""))
        if ziel > 0 and jahre_n > 0:
            k4 = ("Abstand zum Ziel", f'<span class="{farbe}">{"+" if diff >= 0 else "−"}'
                                      f'{_de(abs(E.runden_ungefaehr(diff) or 0))} €</span>',
                  "Ziel im Modell erreicht" if z["ziel_erreicht"] else "Ziel im Modell nicht erreicht")
        else:
            k4 = ("Portfolio-Rendite p.a." if jahre_n > 0 else "Positionen", _pct(port_r) if jahre_n > 0
                  else str(sum(1 for g in w.values() if g > 0)), "gewichtet" if jahre_n > 0 else "mit Gewicht")
        _kacheln([k1, k2, k3, k4])
        proj = z["projektion"]
        zeilen = []
        if jahre_n > 0:
            zeilen.append(f'Multiplikator <b>{_de(z["multiplikator"], 2)}×</b>'
                          + (f' · Einzahlungen gesamt {_de(proj["eingezahlt"])} €' if rahmen.get("sparrate_monat") else ""))
            zeilen.append(" · ".join(f"J{j}: {_eur(v)}" for j, v in enumerate(proj["jahreswerte"]) if j))
        e = _entnahme_daten(m)
        if e.get("aktiv", True):
            try:
                _kap, _r, _kw, plan = _entnahme_rechnen(m, R, e)
                dauer = "dauerhaft" if plan["reicht_dauerhaft"] else _dauer_text(plan)
                ok = plan["reicht_dauerhaft"] or plan["dauer_monate"] >= int(e["dauer_jahre"]) * 12
                zeilen.append(f'{"Danach" if jahre_n > 0 else "Sofort"} Entnahme <b>{_de(e["monatlich"])} €/Monat</b> '
                              f'aus {_eur(_kap)} bei {_pct(_r)} p.a. · reicht '
                              f'<b class="{"pl-gut" if ok else "pl-schlecht"}">{dauer}</b> (Plan {e["dauer_jahre"]} J.)')
            except Exception:
                pass
        auto = st.session_state.get("planer_autogew")
        if auto and not auto.get("fehler"):
            zeilen.append(("Gewichte automatisch auf " if auto["erreichbar"] else "⚠ Höchstens erreichbar: ")
                          + f'<b>{_pct(auto["rendite"])} p.a.</b> ausgerichtet'
                          + ("" if auto["erreichbar"] else f' (mit diesen Bausteinen max. {_pct(auto["max"])})'))
        st.markdown(f'<div class="pl-zeile">{"<br>".join(zeilen)}</div>', unsafe_allow_html=True)
        _hinweis()


def _gewichtswarnung(platz, m):
    summe = E.gewichte_summe(m)
    if abs(summe - 100.0) > 0.05:
        with platz.container():
            c1, c2 = st.columns([3, 1])
            c1.warning(f"Portfolio = {_de(summe, 1)} % – die Rechnung skaliert auf 100 %.")
            if c2.button("Gewichte normalisieren", key=_k("norm_oben"), width="stretch"):
                E.normalisieren(m)
                _neu_zeichnen()
                st.rerun()


# --- Katalog: Bausteine nach Kennzahlen auswaehlen ---------------------------
PFAD_KATALOG = "state/planer/katalog.json"
KATALOG_GRUPPEN = {
    "Rendite": ["1J %", "3J p.a.", "5J p.a.", "10J p.a."],
    "Risiko": ["Vola 1J", "Max DD", "Risk", "Hebel"],
    "Annahmen": ["Base", "Bear", "Bull", "Conf."],
    "Kosten & Daten": ["Perf.-Fee", "TER", "Historie ab", "Profil", "Gefunden"],
}
KATALOG_SORT = ["5J p.a.", "3J p.a.", "1J %", "10J p.a.", "Vola 1J", "Max DD", "Risk", "Conf.", "Base",
                "Historie ab", "Name"]


def _katalog_daten(h):
    d = st.session_state.get("planer_katalog")
    if d is None:
        try:
            d = h["gh_read"](PFAD_KATALOG, {}) or {}
        except Exception:
            d = {}
        st.session_state["planer_katalog"] = d
    return d


def _katalog_laden(h):
    """Kennzahlen aller Katalogwerte aus der echten Kurshistorie (ls-tc.de) -
    parallel geladen und als Tagesstand im GitHub-Speicher abgelegt, damit
    der naechste Aufruf (auch auf einem anderen Geraet) sofort da ist."""
    heute = h["heute"].isoformat()
    aufgaben = [(k["wkn"], _hist_eines,
                 (tuple(x for x in (k["wkn"], k["isin"]) if x), k["typ"] == "wikifolio", heute,
                  h["suche_instrument"], h["get_kurshistorie"], None)) for k in D.KATALOG]
    werte = {}
    for wkn, k in _parallel(aufgaben).items():
        if k and not k.get("fehler"):
            werte[wkn] = {x: v for x, v in k.items() if x != "monat"}
        else:
            werte[wkn] = {"fehler": (k or {}).get("fehler") or "keine Daten"}
    d = {"stand": heute, "berechnet": datetime.datetime.now().strftime("%d.%m.%Y %H:%M"), "werte": werte}
    st.session_state["planer_katalog"] = d
    try:
        h["gh_write"](PFAD_KATALOG, d, message="planer: katalog-kennzahlen [skip ci]")
    except Exception:
        pass
    return d


def _im_portfolio(m, k):
    return any((a.get("ticker") or "").upper() == k["wkn"] or (k["isin"] and a.get("isin") == k["isin"])
               for a in m["assets"])


def _katalog_zeilen(m, werte):
    zeilen = []
    for k in D.KATALOG:
        kz = werte.get(k["wkn"]) or {}
        ok = bool(kz) and not kz.get("fehler")
        typ = D.KATEGORIEN[k["category"]]["typ"]
        vs = E.vorschlag_renditen(kz, typ) if ok else None

        def pct(feld, _kz=kz):
            v = _kz.get(feld) if ok else None
            return None if v is None else round(v * 100, 1)

        zeilen.append({
            "wkn": k["wkn"], "Name": k["name"], "Typ": D.KATALOG_TYPEN[k["typ"]],
            "1J %": pct("historical1Y"), "3J p.a.": pct("historical3Y"), "5J p.a.": pct("historical5Y"),
            "10J p.a.": pct("historical10Y"),
            "Vola 1J": pct("vola1y") if ok and kz.get("vola1y") is not None else pct("vola"),
            "Max DD": round(kz["maxdd"], 1) if ok and kz.get("maxdd") is not None else None,
            "Risk": E.risiko_score(kz.get("vola1y") or kz.get("vola"), kz.get("maxdd"), k["hebel"], k["profil"])
            if ok else None,
            "Hebel": k["hebel"],
            "Base": None if not vs else round(vs["base"] * 100, 1),
            "Bear": None if not vs else round(vs["bear"] * 100, 1),
            "Bull": None if not vs else round(vs["bull"] * 100, 1),
            "Conf.": E.confidence_score(kz.get("jahre"), typ) if ok else None,
            "Perf.-Fee": None if k["perf_fee"] is None else k["perf_fee"] * 100,
            "TER": None if k["ter"] is None else k["ter"] * 100,
            "Historie ab": _datum(kz.get("start")) if ok and kz.get("start") else "",
            "Profil": k["profil"],
            "Gefunden": (kz.get("instrument") or "") if ok else (kz.get("fehler") or ""),
            "Im Portf.": _im_portfolio(m, k),
            "_k": k, "_vs": vs,
        })
    return zeilen


def _spalte(name, pinned=False, **kw):
    """Spaltenkonfiguration; 'pinned' (Name bleibt beim Wischen stehen) nur,
    wenn die Streamlit-Version es kennt."""
    typ = kw.pop("typ", "zahl")
    f = {"zahl": st.column_config.NumberColumn, "text": st.column_config.TextColumn,
         "check": st.column_config.CheckboxColumn}[typ]
    if pinned:
        try:
            return f(name, pinned=True, **kw)
        except TypeError:
            pass
    return f(name, **kw)


def _katalog(m, h):
    d = _katalog_daten(h)
    werte = d.get("werte") or {}
    heute = h["heute"].isoformat()
    if not werte:
        st.info("Für den Katalog sind noch keine Kennzahlen berechnet. Das Laden der Kurshistorien "
                f"({len(D.KATALOG)} Werte) dauert einmalig etwa eine halbe Minute – danach steht der Tagesstand "
                "gespeichert bereit.")
    c1, c2 = st.columns([3, 1])
    if werte:
        c1.caption(f"Kennzahlen Stand {d.get('berechnet', '–')} · Quelle ls-tc.de Kurshistorie"
                   + ("" if d.get("stand") == heute else " · nicht von heute"))
    if c2.button("📊 Kennzahlen laden" if not werte else "Aktualisieren", key="pl_kat_laden", width="stretch"):
        with st.spinner(f"Lade Kurshistorien für {len(D.KATALOG)} Werte …"):
            d = _katalog_laden(h)
        werte = d["werte"]

    typen = ["Alle"] + list(D.KATALOG_TYPEN.values())
    typ = st.pills("Art", typen, default="Alle", key="pl_kat_typ") or "Alle"
    gruppen = st.pills("Spalten", list(KATALOG_GRUPPEN), default=["Rendite", "Risiko"], selection_mode="multi",
                       key="pl_kat_spalten") or []
    c3, c4 = st.columns([3, 2])
    sortierung = c3.selectbox("Sortieren nach", KATALOG_SORT, key="pl_kat_sort")
    absteigend = c4.toggle("Absteigend", value=sortierung not in ("Risk", "Vola 1J", "Name"), key=f"pl_kat_ab_{sortierung}")

    zeilen = [z for z in _katalog_zeilen(m, werte) if typ == "Alle" or z["Typ"] == typ]

    def wert(z):
        if sortierung == "Historie ab":
            return (werte.get(z["wkn"]) or {}).get("start")
        return z[sortierung].lower() if sortierung == "Name" else z[sortierung]
    mit = [z for z in zeilen if wert(z) not in (None, "")]
    mit.sort(key=wert, reverse=absteigend)
    zeilen = mit + [z for z in zeilen if wert(z) in (None, "")]

    wahl = st.session_state.setdefault("planer_kat_wahl", [])
    spalten = [s_ for g in KATALOG_GRUPPEN if g in gruppen for s_ in KATALOG_GRUPPEN[g]]
    kopf = ["＋", "Name"] + ([] if typ != "Alle" else ["Typ"]) + spalten + ["Im Portf."]
    df = pd.DataFrame([{**{c: z[c] for c in kopf if c != "＋"}, "＋": z["wkn"] in wahl} for z in zeilen])[kopf] \
        if zeilen else pd.DataFrame(columns=kopf)
    cfg = {"＋": _spalte("＋", typ="check", width="small", help="Zum Hinzufügen auswählen"),
           "Name": _spalte("Name", pinned=True, typ="text", width="medium"),
           "Im Portf.": _spalte("Im Portf.", typ="check", width="small")}
    for c in spalten:
        if c in ("Historie ab", "Profil", "Gefunden"):
            cfg[c] = _spalte(c, typ="text")
        elif c == "Hebel":
            cfg[c] = _spalte(c, format="%.0f×", width="small")
        elif c in ("Risk", "Conf."):
            cfg[c] = _spalte(c, format="%d", width="small",
                             help="Risk Score 0–100 (höher = riskanter)" if c == "Risk" else "Datenbasis 0–100")
        else:
            cfg[c] = _spalte(c, format="%.1f", width="small")
    signatur = zlib.crc32(("|".join(df["Name"].astype(str)) + "|".join(kopf)).encode()) if len(df) else 0
    ed = st.data_editor(df, key=_k(f"kat_{signatur}"), hide_index=True, width="stretch", height=_hoehe(len(df)),
                        disabled=[c for c in kopf if c != "＋"], column_config=cfg)
    for i, z in enumerate(zeilen):
        an = bool(ed.iloc[i]["＋"])
        if an and z["wkn"] not in wahl:
            wahl.append(z["wkn"])
        elif not an and z["wkn"] in wahl:
            wahl.remove(z["wkn"])

    st.caption("Renditen = Kursentwicklung (1 J.) bzw. p.a. über 3/5/10 J., Vola = Schwankung der letzten 12 Monate, "
               "Max DD = größter Rückgang seit Beginn der Historie. Risk Score 0–100: 45 % Vola, 35 % Drawdown, "
               "20 % Hebel. Base/Bear/Bull: " + D.VORSCHLAG["text"] + " Performance Fee und TER nur, soweit "
               "hinterlegt. Hohe Vergangenheitsrenditen sind keine Zukunftserwartung (Winner Bias).")

    gewaehlt = [k for k in D.KATALOG if k["wkn"] in wahl]
    c5, c6 = st.columns(2)
    gew = c5.number_input("Startgewicht je Baustein %", 0.0, 100.0, 0.0, step=0.5, key="pl_kat_gew",
                          help="Danach mit „Gewichtung 100k“ oder „Normalisieren“ verteilen")
    vorschlag = c6.toggle("Base/Bear/Bull-Vorschlag als Annahme", value=True, key="pl_kat_vs")
    if st.button(f"➕ {len(gewaehlt)} ausgewählte hinzufügen", key="pl_kat_add", width="stretch",
                 disabled=not gewaehlt):
        doppelt = []
        for k in gewaehlt:
            if _im_portfolio(m, k):
                doppelt.append(k["name"])
                continue
            kz = werte.get(k["wkn"]) or {}
            vs = E.vorschlag_renditen(kz, D.KATEGORIEN[k["category"]]["typ"]) if kz and not kz.get("fehler") else None
            extra = {"subCategory": k["profil"], "sector": k["sektor"], "region": k["region"],
                     "leverage": k["hebel"], "leverageType": k["hebel_typ"], "techAnteil": k["tech"],
                     "semiAnteil": k["semi"], "treiber": k["treiber"], "expenseRatio": k["ter"],
                     "performanceFee": k["perf_fee"],
                     "emittent": "Lang & Schwarz" if k["typ"] == "wikifolio" else None,
                     "historicalWinnerBias": bool(vs and vs["hist"] >= 0.20)}
            nutzen = vorschlag and vs is not None
            aid = _baustein_neu(
                m, k["name"], k["category"], wkn=k["wkn"], isin=k["isin"], gewicht=gew,
                rendite=vs["base"] * 100 if nutzen else None, extra=extra, auto=True,
                notiz=(D.VORSCHLAG["text"] + f" Historisch {vs['quelle']}: {_pct(vs['hist'])} p.a., "
                       f"Confidence {vs['confidence']}/100.") if nutzen else None)
            if nutzen:
                for sz in ("bear", "base", "bull"):
                    E.setze_annahme(m, aid, sz, vs[sz], notiz="Vorschlag aus Katalog – keine Prognose")
        st.session_state["planer_kat_wahl"] = []
        if doppelt:
            st.session_state["planer_meldung"] = ("warnung", "Schon im Portfolio, nicht doppelt angelegt: "
                                               + ", ".join(doppelt), [])
        _neu_zeichnen()
        st.rerun()
    if any(k["typ"] == "aktie" for k in gewaehlt) and any(a["category"] == "stock_basket" and a.get("enabled")
                                                           for a in m["assets"]):
        st.caption("Hinweis: Einige Aktien (z. B. NVIDIA, Broadcom, Quanta, Comfort Systems, Arista) stecken auch im "
                   "Fundamental Growth Basket – einzeln hinzugefügt, zählen sie doppelt.")


# --- 1 Allocation -----------------------------------------------------------
def _suche_hinzufuegen(m, h):
    c4, c5 = st.columns([3, 1])
    suchtext = c4.text_input("WKN oder ISIN", key=_k("add_such"), placeholder="z. B. A1JX52 oder IE00B4L5Y983")
    if c5.button("Suchen", key=_k("add_btn"), width="stretch", disabled=not suchtext.strip()):
        try:
            st.session_state["planer_treffer"] = h["suche_instrument"](suchtext.strip()) or []
        except Exception:
            st.session_state["planer_treffer"] = []
        st.session_state["planer_treffer_q"] = suchtext.strip()
    treffer = st.session_state.get("planer_treffer")
    if treffer is not None and st.session_state.get("planer_treffer_q"):
        if not treffer:
            st.warning(f"Kein Treffer für „{st.session_state['planer_treffer_q']}“.")
        else:
            wahl = st.selectbox("Treffer", list(range(len(treffer))), key=_k("add_wahl"),
                                format_func=lambda i: f'{treffer[i]["name"]} · {treffer[i].get("wkn") or "–"} · '
                                                      f'{treffer[i].get("isin") or ""}'.strip(" ·"))
            t = treffer[wahl]
            kats = list(D.KATEGORIEN)
            c6, c7, c8 = st.columns(3)
            kat = c6.selectbox("Kategorie", kats, index=kats.index(_kategorie_raten(t)),
                               format_func=lambda k: D.KATEGORIEN[k]["titel"], key=_k("add_kat"))
            gew = c7.number_input("Gewicht %", 0.0, 100.0, 0.0, step=0.5, key=_k("add_gew"))
            ren = c8.number_input("Annahme % p.a.", -50.0, 300.0, value=None, step=0.5, key=_k("add_ren"),
                                  placeholder="leer = später")
            if st.button("➕ Zum Portfolio hinzufügen", key=_k("add_ok"), width="stretch"):
                _baustein_neu(m, t["name"], kat, wkn=t.get("wkn"), isin=t.get("isin"), gewicht=gew, rendite=ren)
                st.session_state.pop("planer_treffer", None)
                st.session_state.pop("planer_treffer_q", None)
                _neu_zeichnen()
                st.rerun()
            st.caption("Ohne Annahme rechnet der Baustein mit 0 % – die historische Rendite erscheint nach dem "
                       "Hinzufügen unter „🗂️ Daten → Annahmen & Quellen“.")




def _editor_formular(df, key, **kw):
    """Tabelle als Formular: Aenderungen werden gesammelt und erst mit
    „Änderungen übernehmen“ gerechnet und gespeichert - nicht nach jeder
    einzelnen Zelle. Ohne Klick liefert die Funktion die unveraenderte
    Tabelle zurueck, die nachfolgende Uebernahme-Schleife findet dann nichts."""
    with st.form(key + "_form", border=False):
        st.markdown('<div class="pl-formhinweis">✏️ Werte in der Tabelle ändern – gerechnet und gespeichert wird '
                    'erst mit <b>„Daten aktualisieren“</b>.</div>', unsafe_allow_html=True)
        ed = st.data_editor(df, key=key, **kw)
        c1, c2 = st.columns([3, 2])
        # Bewusst ohne type="primary": primaryColor ist in der App Weiss -
        # ein Primary-Button waere weisse Schrift auf weissem Grund.
        ok = c1.form_submit_button("🔄 Daten aktualisieren", width="stretch",
                                   help="Alle geänderten Werte übernehmen, neu berechnen und speichern")
        verwerfen = c2.form_submit_button("↺ Verwerfen", width="stretch",
                                          help="Nur noch nicht übernommene Änderungen in dieser Tabelle zurücknehmen")
    if verwerfen:
        _neu_zeichnen()
        st.rerun()
    return ed if ok else df


def _hoehe(zeilen):
    """Tabellenhoehe fuer st.data_editor: alle Zeilen sichtbar, kein inneres
    Scrollen. +16 px Reserve fuer eine evtl. waagerechte Scrollleiste, die
    sonst die letzte Zeile verdeckt."""
    return int(35 * (zeilen + 1) + 3 + 16)


def _smartphone():
    """True auf Smartphones (User-Agent). iPad/Desktop -> False: dort ist
    Platz fuer volle Spaltenbreiten. iPadOS meldet sich als Mac - passt."""
    try:
        ua = (st.context.headers.get("User-Agent") or "").lower()
    except Exception:
        return False
    return "iphone" in ua or ("android" in ua and "mobile" in ua) or "ipod" in ua


def _kategorie_raten(t):
    """Kategorie eines Suchtreffers aus Name/WKN/Gattung - in den Stammdaten aenderbar."""
    txt = f'{t.get("name", "")} {t.get("kategorie", "")}'.lower()
    wkn = str(t.get("wkn", "")).upper()
    regeln = [
        (wkn.startswith("LS9") or "wikifolio" in txt, "wikifolio"),
        (any(x in txt for x in ("2x", "3x", "leverag", "hebel", "long x")), "leveraged_etf"),
        (any(x in txt for x in ("bitcoin", "ethereum", "crypto", "krypto")), "crypto"),
        (any(x in txt for x in ("semicond", "halbleiter", "chip")), "semiconductor"),
        (any(x in txt for x in ("gold", "silver", "silber", "miner", "copper", "kupfer", "rohstoff")), "mining"),
        ("small" in txt, "small_cap"),
        (any(x in txt for x in ("momentum", "quality", "value", "min vol", "dividend")), "factor"),
        (any(x in txt for x in ("nasdaq", "tech", "informat")), "technology"),
        (any(x in txt for x in ("etf", "ucits", "fonds", "fund", "index", "msci", "ftse", "s&p")), "global_equity"),
    ]
    return next((k for bed, k in regeln if bed), "single_stock")


def _baustein_neu(m, name, kategorie, *, wkn=None, isin=None, gewicht=0.0, rendite=None, extra=None,
                  notiz=None, auto=False):
    aid = "u_" + str(abs(zlib.crc32((name + (wkn or "") + datetime.datetime.now().isoformat()).encode())))
    a = D._asset(aid, name, kategorie, float(gewicht), isin=isin or None, ticker=wkn or None,
                 hebel=2.0 if kategorie == "leveraged_etf" else 1.0,
                 hebel_typ="daily" if kategorie == "leveraged_etf" else None,
                 notiz="Über den Portfolio Builder hinzugefügt.")
    a.update(extra or {})
    m["assets"].append(a)
    E.setze_annahme(m, aid, "manualScenario", None if rendite is None else float(rendite) / 100.0,
                    notiz=notiz or ("Eigene Annahme" if rendite is not None else "Wird aus der Kurshistorie ergänzt."),
                    auto=rendite is None or auto)
    return aid


def _basis_text(m, a):
    if a["category"] == "cash":
        return "Cash"
    rec = next((x for x in m["annahmen"] if x["assetId"] == a["id"] and x["sourceType"] == "manualScenario"), None)
    if rec is None or rec.get("value") is None:
        return "fehlt"
    if rec.get("auto"):
        src = str(rec.get("source") or "")
        if src.startswith("Kurshistorie ("):
            return "Hist. " + src[len("Kurshistorie ("):].rstrip(")").replace(" p.a.", "")
        if src.startswith("Standard"):
            return "Standard ⚠"
        return "Startwert ⚠"
    return "eigene"


def _baustein_entfernen(m, aid):
    m["assets"] = [a for a in m["assets"] if a["id"] != aid]
    m["annahmen"] = [x for x in m["annahmen"] if x["assetId"] != aid]
    (m.get("holdings") or {}).pop(aid, None)
    if m["nachkauf"].get("ziel_asset") == aid:
        m["nachkauf"]["ziel_asset"] = "etf_allworld"


def _ziel_label(ziel):
    return f"{_de(ziel / 1000)}k" if ziel >= 1000 and ziel % 1000 == 0 else _de(ziel) + " €"


def _b_bausteine(m, R, h):
    _abschnitt("Bausteine")
    _auto_hinweis(m)
    start = m["rahmen"]["startkapital"]
    summe = E.gewichte_summe(m) or 1.0
    zeilen = []
    for a in m["assets"]:
        eig = E.annahme(m, a["id"], "manualScenario")
        info = R["info"].get(a["id"]) or {}
        zeilen.append({
            "Aktiv": bool(a.get("enabled")), "Baustein": a["name"],
            "Gew. %": float(a.get("targetWeight") or 0.0) if a.get("enabled") else 0.0,
            "Annahme %": None if not eig or eig.get("value") is None else round(eig["value"] * 100, 2),
            "Basis": _basis_text(m, a),
            "Ist": a.get("renditequelle") == "historisch",
            "Fix": bool(a.get("fixiert")),
            "Betrag €": round(start * float(a.get("targetWeight") or 0) / summe) if a.get("enabled") else 0,
            "Genutzt %": None if info.get("netto") is None else round(info["netto"] * 100, 2),
            "Conf.": R["conf"].get(a["id"]),
        })
    df = pd.DataFrame(zeilen)
    # iPhone: schmale, feste Spalten, damit Name + Gewicht auf den Schirm passen.
    # iPad/Desktop: Spalten wachsen mit dem Inhalt (volle Namen, alles sichtbar).
    schmal = _smartphone()
    breite = (lambda w: w) if schmal else (lambda w: None)
    ed = _editor_formular(
        df, key=_k("builder"), hide_index=True, width="stretch", num_rows="fixed", height=_hoehe(len(df)),
        disabled=["Baustein", "Basis", "Betrag €", "Genutzt %", "Conf."],
        column_config={
            "Basis": st.column_config.TextColumn(
                "Basis", width=breite("small"),
                help="Woher die Annahme stammt: „Hist. 5 J.“ usw. = automatisch aus der bisherigen Rendite p.a. "
                     "(wird täglich nachgeführt), „Hist. seit Start, N Mon.“ = junge Werte < 1 Jahr (nicht hochgerechnet), "
                     "„Standard ⚠“ = keine Kursdaten gefunden, Kategorie-Standard, „Startwert ⚠“ = Wert aus dem "
                     "Ausgangsmodell, keine Kursdaten, „eigene“ = selbst eingetragen"),
            "Aktiv": st.column_config.CheckboxColumn("Aktiv", width=breite("small")),
            "Baustein": st.column_config.TextColumn("Baustein", width=breite("medium")),
            "Gew. %": st.column_config.NumberColumn("Gew. %", min_value=0.0, max_value=100.0, step=0.5,
                                                    format="%.1f", width=breite("small"),
                                                    help="Anteil am Gesamtportfolio – auch für Wikifolios frei einstellbar"),
            "Annahme %": st.column_config.NumberColumn(
                "Annahme %", step=0.5, format="%.1f", width=breite("small"),
                help="Eigene Renditeannahme p.a. (Szenario, keine Prognose)"),
            "Ist": st.column_config.CheckboxColumn(
                "Ist", width=breite("small"),
                help="Tatsächliche Rendite laut Kurshistorie statt der Annahme verwenden (Standard bei Wikifolios)"),
            "Fix": st.column_config.CheckboxColumn(
                "Fix", width=breite("small"),
                help="Fixierte Gewichte bleiben bei allen Verfahren unter „Gewichtung“ unverändert"),
            "Betrag €": st.column_config.NumberColumn("Betrag €", format="%d"),
            "Genutzt %": st.column_config.NumberColumn("Genutzt %", format="%.1f",
                                                       help="In der Rechnung verwendet (aktive Quelle, ggf. netto)"),
            "Conf.": st.column_config.NumberColumn("Conf.", format="%d",
                                                   help="Belastbarkeit der Datenbasis 0–100"),
        })
    geaendert = False
    for i, a in enumerate(m["assets"]):
        z = ed.iloc[i]
        aktiv = bool(z["Aktiv"])
        gew = 0.0 if pd.isna(z["Gew. %"]) or not aktiv else float(z["Gew. %"])   # inaktiv = 0 %
        if aktiv != bool(a.get("enabled")) or abs(gew - float(a.get("targetWeight") or 0)) > 1e-9:
            a["enabled"], a["targetWeight"] = aktiv, gew
            geaendert = True
        ist = "historisch" if bool(z["Ist"]) else "annahme"
        if a["category"] != "cash" and ist != a.get("renditequelle"):
            a["renditequelle"] = ist
            geaendert = True
        if bool(z["Fix"]) != bool(a.get("fixiert")):
            a["fixiert"] = bool(z["Fix"])
            geaendert = True
        ann = z["Annahme %"]
        if not pd.isna(ann):
            eig = E.annahme(m, a["id"], "manualScenario")
            # Toleranz: die Tabelle zeigt 2 Nachkommastellen - nur echte Aenderungen
            # zaehlen (sonst wuerde jede automatische Annahme zur "eigenen")
            if eig is None or eig.get("value") is None or abs(eig["value"] * 100.0 - float(ann)) > 0.006:
                E.setze_annahme(m, a["id"], "manualScenario", float(ann) / 100.0)
                geaendert = True
    if geaendert:
        st.rerun()

    summe = E.gewichte_summe(m)
    c1, c2 = st.columns(2)
    c1.markdown(f'<div class="pl-zeile">Summe aktiver Gewichte: <b class="{"pl-gut" if abs(summe - 100) <= 0.05 else "pl-schlecht"}">'
                f'{_de(summe, 1)} %</b></div>', unsafe_allow_html=True)
    if c2.button("Auf 100 % normalisieren", key=_k("norm"), width="stretch", disabled=abs(summe - 100) <= 0.05):
        E.normalisieren(m)
        _neu_zeichnen()
        st.rerun()
    if st.button("📥 Alle Annahmen aus bisheriger Rendite p.a.", key=_k("ann_hist"), width="stretch",
                 help="Setzt auch selbst eingetragene Annahmen wieder auf die bisherige Rendite p.a. laut "
                      "Kurshistorie zurück (5 J., sonst 3 J., sonst seit Start, sonst 1 J., bei jungen Werten "
                      "seit Start ohne Hochrechnung; ohne Kursdaten Standardwert der Kategorie)"):
        n = E.annahmen_aus_historie(m, st.session_state.get("planer_historie") or {}, alle=True)
        st.session_state["planer_meldung"] = ("ok", f"{n} Annahmen aus der bisherigen Rendite p.a. übernommen.", [])
        _neu_zeichnen()
        st.rerun()
    _meldung_zeigen()
    st.caption("Spalten: Gew. % = Anteil · Annahme % = Rendite p.a. (Basis zeigt die Herkunft) · Ist = tatsächliche "
               "Rendite laut Kurshistorie statt Annahme · Fix = bleibt beim Gewichten unverändert · Genutzt % = "
               "damit wird gerechnet. Gewichte automatisch verteilen: Bereich „⚖️ Gewichtung“.")

    _abschnitt("Baustein hinzufügen")
    weg_ = st.pills("Hinzufügen über", ["📋 Katalog", "🔎 WKN / ISIN"], default="📋 Katalog", key="pl_add_art")
    if weg_ == "🔎 WKN / ISIN":
        _suche_hinzufuegen(m, h)
    else:
        _katalog(m, h)

    _abschnitt("Baustein entfernen")
    c9, c10 = st.columns([3, 1])
    weg = c9.selectbox("Baustein", [a["id"] for a in m["assets"]], key=_k("del_wahl"),
                       format_func=lambda i: _asset(m, i)["name"])
    if c10.button("🗑 Entfernen", key=_k("del_btn"), width="stretch", disabled=not m["assets"]):
        _baustein_entfernen(m, weg)
        _neu_zeichnen()
        st.rerun()
    st.caption("Entfernen löscht den Baustein samt Annahmen aus diesem Modell; „Aktiv“ abwählen lässt ihn in "
               "der Liste, sein Anteil wird 0 %.")

    _abschnitt("Zurücksetzen")
    st.caption("„↺ Verwerfen“ unter der Tabelle nimmt nur noch nicht übernommene Tabellen-Änderungen zurück. "
               "Hier wird das komplette Modell auf das Ausgangsmodell zurückgesetzt – Bausteine, Gewichte, "
               "Annahmen, Planung und Grenzen.")
    sicher = st.checkbox("Ja, alles auf das Ausgangsmodell zurücksetzen", key=_k("reset_ok"))
    if st.button("↺ Modell komplett zurücksetzen", key=_k("reset_btn"), width="stretch", disabled=not sicher):
        st.session_state["planer_modell"] = D.seed_modell()
        for k in ("planer_vorschlag", "planer_meldung", "planer_autogew"):
            st.session_state.pop(k, None)
        st.session_state["planer_meldung"] = ("ok", "Modell auf das Ausgangsmodell zurückgesetzt.", [])
        _neu_zeichnen()
        st.rerun()


def _meldung_zeigen():
    meldung = st.session_state.get("planer_meldung")
    if meldung:
        art, text, verletzt = meldung
        {"ok": st.success, "warnung": st.warning, "fehler": st.error}[art](text)
        if verletzt:
            st.caption("Hinweis – über den Optimizer-Grenzen: " + " · ".join(verletzt) + ". Reine Rückrechnung aus "
                       "den Annahmen, keine Empfehlung.")


def _b_aufteilung(m, R):
    _abschnitt("Aufteilung")
    start = m["rahmen"]["startkapital"]
    w = E.gewichte(m)
    namen = {a["id"]: a["name"] for a in m["assets"]}
    ids = [i for i in w if w[i] > 0]
    fig = go.Figure(go.Pie(labels=[namen[i] for i in ids], values=[w[i] * 100 for i in ids], hole=0.55,
                           sort=False, marker=dict(colors=FARBEN[:len(ids)], line=dict(color="#000", width=1)),
                           textinfo="percent", hovertemplate="%{label}: %{value:.1f} %<extra></extra>"))
    _layout(fig, 380, legende=True)
    fig.update_layout(legend=dict(orientation="h", y=-0.05, yanchor="top"), margin=dict(t=10, b=10))
    _chart(fig, "pl_alloc")

    # Nach Kategorie
    kat = {}
    for i in ids:
        titel = D.KATEGORIEN.get(_asset(m, i)["category"], {}).get("titel", _asset(m, i)["category"])
        kat[titel] = kat.get(titel, 0.0) + w[i] * 100
    _tabelle(["Kategorie", "Anteil", "Betrag"],
             [[_esc(k), _pct(v, anteil=False), _eur(start * v / 100, False)] for k, v in
              sorted(kat.items(), key=lambda x: -x[1])])




# --- Gewichtung: EIN Assistent statt verstreuter Knoepfe ----------------------
VERFAHREN = {"rendite": "⚖️ Nach Rendite p.a.", "gleich": "🟰 Gleich verteilt", "ziel": "🎯 Auf Ziel rechnen",
             "start": "↺ Startgewichte"}
VERFAHREN_TEXT = {
    "rendite": "Verteilt die freien Prozente im Verhältnis der Rendite p.a. (Spalte „Genutzt %“). Bausteine mit "
               "Rendite ≤ 0 bekommen 0 %. Bezieht auch neue Bausteine mit bisher 0 % ein.",
    "gleich": "Alle aktiven, nicht fixierten Bausteine bekommen denselben Anteil – die neutrale Ausgangsbasis.",
    "ziel": "Rechnet die Gewichte so, dass das Modell ein Ziel trifft: Zielvermögen oder Wunschrendite p.a. "
            "Ohne Grenzen werden die bisherigen Gewichte stufenlos zu den renditestärkeren Bausteinen verschoben "
            "(Bausteine mit 0 % bleiben außen vor). Mit Grenzen verteilt ein Optimizer so breit wie möglich.",
    "start": "Stellt die Platzhalter-Gewichte des Ausgangsmodells wieder her; gelöschte Start-Bausteine kommen zurück.",
}


def _mit_gewichten(m, gew):
    m2 = dict(m)
    m2["assets"] = [dict(a, targetWeight=gew[a["id"]]) if a["id"] in gew else a for a in m["assets"]]
    return m2


def _grenzen_editor(m):
    g = m["grenzen"]
    g["einzelasset_max"] = float(st.number_input("Max. Gewicht je Baustein (%)", 1.0, 100.0,
                                                 float(g["einzelasset_max"]), step=1.0, key=_k("g_einzel")))
    df = pd.DataFrame([{"Grenze": x["titel"], "Max %": x.get("max"), "Min %": x.get("min")} for x in g["gruppen"]])
    ed = st.data_editor(df, key=_k("grenzen"), hide_index=True, height=_hoehe(len(df)), width="stretch",
                        disabled=["Grenze"],
                        column_config={"Max %": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=1.0),
                                       "Min %": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=1.0)})
    for i, x in enumerate(g["gruppen"]):
        mx, mn = ed.iloc[i]["Max %"], ed.iloc[i]["Min %"]
        x["max"] = None if pd.isna(mx) else float(mx)
        x["min"] = None if pd.isna(mn) else float(mn)
    st.caption("Halbleiter zählt den Halbleiteranteil je Baustein (VanEck Semiconductor 100 %, Korb nach "
               "Zusammensetzung); Indizes ohne hinterlegten Anteil zählen 0 – ergänzbar unter „🗂️ Daten“.")


def _vorschlag(m, R, verfahren, ziel_art, wunsch, mit_grenzen):
    """-> dict(gewichte, art, text) - noch NICHT uebernommen."""
    rahmen = m["rahmen"]
    if verfahren == "rendite":
        erg = E.gewichte_nach_rendite(m, R["r"])
        if erg.get("fehler"):
            return {"art": "fehler", "text": erg["fehler"]}
        return {"gewichte": erg["gewichte"], "art": "ok", "text": "Verteilung nach Rendite p.a."}
    if verfahren == "gleich":
        aktiv = E.aktive_assets(m)
        fest = {a["id"]: float(a.get("targetWeight") or 0) for a in aktiv
                if a.get("fixiert") or a["category"] == "cash"}
        frei = [a["id"] for a in aktiv if a["id"] not in fest]
        rest = 100.0 - sum(fest.values())
        if not frei or rest <= 0:
            return {"art": "fehler", "text": "Keine freien Bausteine zum Verteilen."}
        return {"gewichte": {**fest, **{i: rest / len(frei) for i in frei}}, "art": "ok",
                "text": f"Gleich verteilt: {len(frei)} Bausteine je {_pct(rest / len(frei), 1, anteil=False)}."}
    if verfahren == "start":
        seed = {a["id"]: a["targetWeight"] for a in D.SEED_ASSETS}
        gew = {a["id"]: seed.get(a["id"], 0.0) for a in m["assets"]}
        return {"gewichte": gew, "art": "ok", "text": "Startgewichte des Ausgangsmodells (Platzhalter).",
                "start": True}
    # Ziel
    if int(rahmen.get("horizont_jahre") or 0) <= 0:
        return {"art": "fehler", "text": "Keine Aufbauphase (0 Jahre) – für eine Zielrendite in der Entnahme die "
                                         "automatische Gewichtung unter „⚙️ Planung → Phase 2“ nutzen."}
    if ziel_art == "rendite":
        zielwert = E.ziel_aus_rendite(m, wunsch / 100.0)
        ziel_txt = f"{_de(wunsch, 1)} % p.a. (≈ {_de(E.runden_ungefaehr(zielwert))} €)"
    else:
        zielwert = float(rahmen["zielvermoegen"])
        ziel_txt = f"{_de(zielwert)} €"
    if mit_grenzen:
        o = E.optimiere(m, R["r"], R["conf"], ziel=zielwert)
        if not o or o.get("fehler"):
            return {"art": "fehler", "text": (o or {}).get("fehler") or "Keine Lösung."}
        voll = {a["id"]: o["gewichte"].get(a["id"], 0.0) for a in E.aktive_assets(m)}
        if o["erreichbar"]:
            return {"gewichte": voll, "art": "ok", "text": f"Ziel {ziel_txt} innerhalb aller Grenzen erreichbar."}
        return {"gewichte": voll, "art": "warnung",
                "text": f"Ziel {ziel_txt} ist unter den Grenzen nicht erreichbar. Vorschlag = höchster möglicher "
                        f"Endwert unter den Grenzen ({_eur(o['max_endwert'])})."}
    erg = E.gewichtung_fuer_ziel(m, R["r"], ziel=zielwert, rebalancing=R["reb"])
    if erg.get("fehler"):
        return {"art": "fehler", "text": erg["fehler"]}
    if not erg["erreichbar"]:
        return {"art": "fehler", "text": f"Ziel {ziel_txt} ist mit den aktuellen Annahmen auch bei maximaler "
                                         f"Verschiebung nicht erreichbar (höchstens {_eur(erg['max_endwert'])}). "
                                         "Fixierungen lösen, Annahmen prüfen oder Grenzen nutzen."}
    return {"gewichte": erg["gewichte"], "art": "ok", "text": f"Ziel {ziel_txt} exakt erreicht."}


def _b_gewichtung(m, R):
    _abschnitt("Gewichtung")
    _auto_hinweis(m)
    st.caption("Ein Verfahren wählen → Vorschlag berechnen → vergleichen → übernehmen. Fixierte Bausteine "
               "(Spalte „Fix“) und die Reserve bleiben immer unverändert.")
    keys = list(VERFAHREN)
    wahl = st.pills("Verfahren", [VERFAHREN[k] for k in keys], default=VERFAHREN["rendite"], key="pl_verfahren") \
        or VERFAHREN["rendite"]
    verfahren = keys[[VERFAHREN[k] for k in keys].index(wahl)]
    st.markdown(f'<div class="pl-zeile">{_esc(VERFAHREN_TEXT[verfahren])}</div>', unsafe_allow_html=True)

    ziel_art, wunsch, mit_grenzen = "vermoegen", None, False
    if verfahren == "ziel":
        rahmen = m["rahmen"]
        req = R["zus"]["erforderliche_cagr"] or 0.0
        ziel_art = st.radio("Ziel", ["vermoegen", "rendite"], horizontal=True, key=_k("ziel_art"),
                            format_func=lambda x: (f"Zielvermögen {_ziel_label(rahmen['zielvermoegen'])}"
                                                   if x == "vermoegen" else "Wunschrendite p.a."))
        if ziel_art == "rendite":
            wunsch = float(st.number_input("Wunschrendite p.a. (%)", -20.0, 200.0,
                                           float(rahmen.get("wunschrendite") if rahmen.get("wunschrendite") is not None
                                                 else round(req * 100, 1)), step=1.0, key=_k("wunsch")))
            rahmen["wunschrendite"] = wunsch
        else:
            st.caption(f"Benötigt für das Zielvermögen: {_pct(req)} p.a. (Zielvermögen und Dauer unter "
                       "„⚙️ Planung“).")
        mit_grenzen = st.toggle("Optimizer-Grenzen einhalten (breit streuen)", value=False, key=_k("mit_grenzen"))
        with st.expander("Optimizer-Grenzen bearbeiten", expanded=False):
            _grenzen_editor(m)

    sig = (verfahren, ziel_art, wunsch, mit_grenzen)
    if st.button("🔍 Vorschlag berechnen", key=_k("vorschlag_btn"), width="stretch"):
        v = _vorschlag(m, R, verfahren, ziel_art, wunsch, mit_grenzen)
        v["sig"] = sig
        st.session_state["planer_vorschlag"] = v
    v = st.session_state.get("planer_vorschlag")
    if not v or v.get("sig") != sig:
        _meldung_zeigen()
        return
    {"ok": st.success, "warnung": st.warning, "fehler": st.error}[v["art"]](v["text"])
    gew = v.get("gewichte")
    if not gew:
        return

    # Vergleich vorher / nachher
    summe = E.gewichte_summe(m) or 1.0
    vorher = R["zus"]["endwert"]
    try:
        nachher = E.projektion(_mit_gewichten(m, gew), R["r"], rebalancing=R["reb"])["endwert"]
    except Exception:
        nachher = None
    jahre = m["rahmen"]["horizont_jahre"]
    ohne_spar = not m["rahmen"].get("sparrate_monat")
    _kacheln([
        ("Endwert vorher", _eur(vorher), _pct(E.required_cagr(m["rahmen"]["startkapital"], vorher, jahre)) + " p.a."
         if ohne_spar else None),
        ("Endwert nachher", _eur(nachher), (_pct(E.required_cagr(m["rahmen"]["startkapital"], nachher, jahre))
                                            + " p.a.") if ohne_spar and nachher else None),
    ], klein=True)
    namen = {a["id"]: a["name"] for a in m["assets"]}
    zeilen = []
    for aid, neu in sorted(gew.items(), key=lambda x: -x[1]):
        a = _asset(m, aid)
        if a is None:
            continue
        alt = float(a.get("targetWeight") or 0) * 100 / summe if a.get("enabled") else 0.0
        if neu < 0.005 and alt < 0.005:
            continue
        d = neu - alt
        zeilen.append([_esc(namen[aid]), _pct(alt, 1, anteil=False), f"<b>{_pct(neu, 1, anteil=False)}</b>",
                       f'<span class="{"pl-gut" if d > 0.05 else "pl-schlecht" if d < -0.05 else ""}">'
                       f'{_pct(d, 1, vorzeichen=True, anteil=False)}</span>'])
    _tabelle(["Baustein", "Aktuell", "Neu", "Δ"], zeilen)
    verletzt = E.grenzen_verletzungen(m, {i: g for i, g in gew.items() if g > 0})
    if verletzt:
        st.caption("Über den Optimizer-Grenzen: " + " · ".join(verletzt) + ".")
    c1, c2 = st.columns(2)
    if c1.button("✔ Vorschlag übernehmen", key=_k("vorschlag_ok"), width="stretch"):
        if v.get("start"):
            vorhanden = {a["id"] for a in m["assets"]}
            seed_m = D.seed_modell()
            for a in seed_m["assets"]:
                if a["id"] not in vorhanden:
                    m["assets"].append(a)
                    m["annahmen"] += [x for x in seed_m["annahmen"] if x["assetId"] == a["id"]]
            seed = {a["id"]: a for a in D.SEED_ASSETS}
            for a in m["assets"]:
                a["targetWeight"] = seed[a["id"]]["targetWeight"] if a["id"] in seed else 0.0
                if a["id"] in seed:
                    a["enabled"] = seed[a["id"]]["enabled"]
        else:
            for a in m["assets"]:
                if a["id"] in gew:
                    a["targetWeight"] = gew[a["id"]]
        st.session_state["planer_meldung"] = ("ok", f"Gewichtung übernommen: {v['text']}", verletzt)
        st.session_state.pop("planer_vorschlag", None)
        _neu_zeichnen()
        st.rerun()
    if c2.button("✖ Verwerfen", key=_k("vorschlag_weg"), width="stretch"):
        st.session_state.pop("planer_vorschlag", None)
        st.rerun()
    st.caption("Reine Rückrechnung aus den Annahmen – keine Renditeprognose, keine Anlageempfehlung.")


# --- 2 Projected Growth -----------------------------------------------------
def _gesamtverlauf(m, R):
    """Aufbau + Entnahme als EINE Zeitachse (Monatswerte) und Jahrestabelle.
    Funktioniert auch ohne Aufbau (0 Jahre), ohne Ziel und ohne Sparrate."""
    rahmen = m["rahmen"]
    proj = R["zus"]["projektion"]
    aufbau = list(proj["monatswerte"])
    n_auf = len(aufbau) - 1
    spar = float(rahmen.get("sparrate_monat") or 0.0)
    zeilen = []
    for j in range(n_auf // 12):
        anf, ende = aufbau[j * 12], aufbau[(j + 1) * 12]
        zeilen.append({"jahr": j + 1, "phase": "Aufbau", "anfang": anf, "fluss": spar * 12,
                       "ertrag": ende - anf - spar * 12, "steuer": 0.0, "ende": ende})
    e = _entnahme_daten(m)
    ent, rendite, plan = [], None, None
    if e.get("aktiv", True) and float(e.get("monatlich") or 0) > 0:
        _, rendite, _, plan = _entnahme_rechnen(m, R, e)
        jahre = int(e["dauer_jahre"])
        ent = plan["verlauf"][: jahre * 12 + 1]
        for z in plan["jahre_tabelle"][:jahre]:
            zeilen.append({"jahr": n_auf // 12 + z["jahr"], "phase": "Entnahme", "anfang": z["anfang"],
                           "fluss": -z["netto"], "ertrag": z["ertrag"], "steuer": z.get("steuer", 0.0),
                           "ende": z.get("ende", 0.0)})
    return aufbau, ent, zeilen, rendite, plan


def _jahres_chart(zeilen, ziel=0.0, rendite=None):
    """Die Jahresuebersicht als reiner Linienchart (ein Punkt je Jahr):
    Vermoegen (Jahr 0 = Anfangswert, danach Endwert = Anfang des Folgejahres),
    Ertraege je Jahr nach oben, Entnahmen je Jahr und in Summe nach unten."""
    xs = [0] + [z["jahr"] for z in zeilen]
    verm = [zeilen[0]["anfang"]] + [z["ende"] for z in zeilen]
    ertr = [0.0] + [z["ertrag"] for z in zeilen]
    ein = [0.0] + [max(z["fluss"], 0.0) for z in zeilen]
    aus = [0.0] + [min(z["fluss"], 0.0) - z["steuer"] for z in zeilen]
    summe_aus, s_ = [], 0.0
    for v in aus:
        s_ += v
        summe_aus.append(s_)
    # Vergleich: dasselbe Vermoegen OHNE Entnahme (gleiche Rendite, Einzahlungen bleiben)
    ohne, w_ = [verm[0]], verm[0]
    for z in zeilen:
        if z["phase"] == "Entnahme" and rendite is not None:
            w_ = w_ * (1.0 + rendite)
        else:
            w_ = w_ + z["ertrag"] + max(z["fluss"], 0.0)
        ohne.append(w_)
    zeige_ohne = any(aus) and rendite is not None
    n = len(xs)
    schritt = max(1, math.ceil((n - 1) / 5))
    zeige = {0, n - 1} | set(range(0, n, schritt))
    fig = go.Figure()

    def linie(y, name, farbe, breite=2, strich=None, text=False, pos="top", marker=5):
        fig.add_trace(go.Scatter(
            x=xs, y=y, name=name, mode="lines+markers+text" if text else "lines+markers",
            line=dict(color=farbe, width=breite, dash=strich), marker=dict(size=marker, color=farbe),
            text=[_kurz_eur(v).replace("-", "−") if (k in zeige and (k > 0 or pos == "top") and abs(v) > 0.5) else ""
                  for k, v in enumerate(y)] if text else None,
            textposition=[f"{pos} right" if k == 0 else f"{pos} left" if k == n - 1 else f"{pos} center"
                          for k in range(n)],
            textfont=dict(size=11, color=farbe)))

    if zeige_ohne:
        linie(ohne, "Vermögen ohne Entnahme", "#8A9099", 2, "dash", marker=3)
    linie(verm, "Vermögen", "#FFFFFF", 3, text=True, marker=7)
    linie(ertr, "Erträge je Jahr", "#16C784")
    if any(ein):
        linie(ein, "Einzahlung je Jahr", "#A78BFA")
    if any(aus):
        linie(aus, "Entnahme je Jahr", "#EA3943")
        linie(summe_aus, "Entnahmen gesamt", "#FF6B6B", 2, "dot", text=True, pos="bottom")
    if ziel > 0:
        fig.add_hline(y=ziel, line=dict(color="#F5B942", dash="dash", width=1),
                      annotation_text="Ziel", annotation_font_color="#F5B942")
    _layout(fig, 420)
    fig.update_layout(hovermode="x unified", legend=dict(font=dict(size=11)))
    fig.update_xaxes(title="Jahr (0 = heute, Anfangswert)", dtick=max(1, math.ceil((n - 1) / 10)))
    lo = min(summe_aus + ertr + [0.0])
    hi = max(verm + (ohne if zeige_ohne else [])) * 1.12
    lo = lo * 1.35 if lo < 0 else 0.0                          # Platz fuer die Beschriftung unten
    # Ticks selbst setzen, damit auch der Minusbereich beschriftet ist
    stufe = 10 ** math.floor(math.log10(max(hi - lo, 1.0) / 5))
    stufe = next(f * stufe for f in (1, 2, 2.5, 5, 10) if (hi - lo) / (f * stufe) <= 6)
    ticks = [stufe * i for i in range(math.floor(lo / stufe), math.ceil(hi / stufe) + 1)]
    if lo < 0 and not any(t < 0 for t in ticks if t >= lo):
        ticks.append(lo / 1.35)                                # mindestens ein Wert unter null
    fig.update_yaxes(hoverformat=",.0f", zeroline=True, zerolinecolor="#8A9099", zerolinewidth=1,
                     range=[lo, hi], tickvals=ticks, ticktext=[_kurz_eur(t).replace("-", "−") for t in ticks])
    _chart(fig, "pl_growth")
    if zeige_ohne:
        diff = ohne[-1] - verm[-1]
        _kacheln([
            ("Entnommen gesamt", _eur(-summe_aus[-1], False), f"in {n - 1 - sum(1 for z in zeilen if z['phase'] == 'Aufbau')} J. Entnahme"),
            ("Vermögen am Ende", _eur(verm[-1]), "mit Entnahme"),
            ("Ohne Entnahme", _eur(ohne[-1]), "gleiche Rendite"),
            ("Kosten der Entnahme", _eur(diff), "entgangener Zinseszins inkl. Entnahmen"),
        ], klein=True)
    st.caption("Antippen zeigt alle Werte eines Jahres. Vermögen: Jahr 0 = Anfangswert, danach Stand am "
               "Jahresende (= Anfang des nächsten Jahres). Entnahmen zeigen nach unten.")


def _b_growth(m, R):
    rahmen = m["rahmen"]
    proj = R["zus"]["projektion"]
    monate = len(proj["monatswerte"]) - 1
    x = [m_ / 12 for m_ in range(monate + 1)]
    ziel = float(rahmen.get("zielvermoegen") or 0.0)
    aufbau, ent, zeilen, rendite, plan = _gesamtverlauf(m, R)
    e = _entnahme_daten(m)

    _abschnitt("Vermögensverlauf je Jahr" if zeilen else "Projected Growth")
    if zeilen:
        _jahres_chart(zeilen, ziel if monate > 0 else 0.0, rendite)
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x, y=aufbau, name="Aufbau", line=dict(color="#4C9AFF", width=3)))
        _layout(fig, 340)
        fig.update_xaxes(title="Jahre ab heute")
        _chart(fig, "pl_growth")
    _hinweis()

    if zeilen:
        _abschnitt("Jahresübersicht")
        st.caption(("Aufbau: Einzahlung = Sparrate · " if monate > 0 else "")
                   + "Entnahme: " + f"{_de(e['monatlich'])} €/Monat netto"
                   + (f", +{_de(e['dynamik_pa'], 1)} % p.a." if e.get("dynamik_pa") else "")
                   + (f" · Erträge: Kapital wächst mit {_pct(rendite)} p.a. (monatlich verzinst), "
                      "die Entnahme wird jeden Monat abgezogen" if rendite is not None else ""))
        steuer = any(z["steuer"] for z in zeilen)
        kopf = ["Jahr", "Phase", "Anfang", "Ein-/Auszahlung", "Erträge"] + (["Steuer"] if steuer else []) + ["Ende"]
        _eu = lambda v: _eur(round(v), False)
        _tabelle(kopf, [[str(z["jahr"]), z["phase"], _eu(z["anfang"]),
                         ("+" if z["fluss"] > 0 else "") + _eu(z["fluss"]) if z["fluss"] else "–",
                         _eu(z["ertrag"])] + ([_eu(z["steuer"])] if steuer else []) + [_eu(z["ende"])]
                        for z in zeilen])
        if plan is not None and not plan["reicht_dauerhaft"] and plan["dauer_monate"] < int(e["dauer_jahre"]) * 12:
            st.caption(f"⚠ Das Kapital ist nach {_dauer_text(plan)} Entnahme aufgebraucht.")
    if monate == 0:
        st.caption("Keine Aufbauphase (0 Jahre) – Details zur Entnahme unter „Entnahme“.")
        return

    _abschnitt("Wertentwicklung je Baustein")
    fig2 = go.Figure()
    namen = {a["id"]: a["name"] for a in m["assets"]}
    for n, (aid, reihe) in enumerate(proj["asset_verlauf"].items()):
        if reihe[0] <= 0:
            continue
        fig2.add_trace(go.Scatter(x=x, y=reihe, name=namen[aid], stackgroup="a", mode="none",
                                  fillcolor=FARBEN[n % len(FARBEN)]))
    _layout(fig2, 360)
    _chart(fig2, "pl_stack")

    _abschnitt("Rebalancing-Vergleich")
    varianten = [("keins", "Buy & Hold"), ("jaehrlich", "Jährlich")]
    if R["reb"]["art"] not in ("keins", "jaehrlich"):
        varianten.append((R["reb"]["art"], D.REBALANCING_ARTEN[R["reb"]["art"]]))
    fig3 = go.Figure()
    zeilen = []
    for n, (art, titel) in enumerate(varianten):
        reb = dict(R["reb"], art=art)
        p = E.projektion(m, R["r"], rebalancing=reb)
        ps = E.projektion(m, R["r"], rebalancing=reb, stress=m["stress"])
        fig3.add_trace(go.Scatter(x=x, y=ps["monatswerte"], name=f"{titel} (Stresspfad)",
                                  line=dict(color=FARBEN[n], width=2)))
        zeilen.append([_esc(titel), _eur(p["endwert"]), _eur(ps["endwert"]), _pct(ps["max_verlust_pfad"], anteil=False),
                       str(ps["rebalancings"])])
    _layout(fig3, 320)
    _chart(fig3, "pl_rebal")
    _tabelle(["Variante", "Endwert glatt", "Endwert Stresspfad", "Max. Verlust", "Rebal."], zeilen)
    st.caption("Glatte Rechnung: konstante Renditen – Rebalancing verschiebt dort nur Gewicht von stärkeren zu "
               "schwächeren Bausteinen. Stresspfad: zusätzlicher Markteinbruch (Einstellungen unter "
               "„⚠️ Risiko → Stress & Reserve“), in dem Rebalancing antizyklisch wirkt.")


# --- 3 Zielerreichung -------------------------------------------------------
def _b_ziel(m, R):
    z = R["zus"]
    proj = z["projektion"]
    namen = {a["id"]: a["name"] for a in m["assets"]}
    _abschnitt("Zielerreichung")
    _kacheln([
        ("Benötigt p.a.", _pct(z["erforderliche_cagr"]), None),
        ("Modell p.a.", _pct(z["modell_cagr"]), None),
        ("Lücke p.a.", _pct((z["erforderliche_cagr"] or 0) - (z["modell_cagr"] or 0), vorzeichen=True), "Prozentpunkte"),
        ("Endwert / Ziel", _pct(z["endwert"] / m["rahmen"]["zielvermoegen"], 0) if m["rahmen"]["zielvermoegen"] else "–",
         None),
    ], klein=True)
    beitr = sorted(proj["beitraege"].items(), key=lambda x: -x[1])
    fig = go.Figure(go.Bar(x=[v for _, v in beitr], y=[namen[i] for i, _ in beitr], orientation="h",
                           marker_color=["#16C784" if v >= 0 else "#EA3943" for _, v in beitr],
                           hovertemplate="%{y}: %{x:,.0f} €<extra></extra>"))
    _layout(fig, 60 + 30 * len(beitr), legende=False)
    fig.update_yaxes(autorange="reversed", side="left", tickformat=None)
    fig.update_xaxes(tickformat=",.0f")
    fig.update_layout(title=dict(text="Gewinnbeitrag je Baustein (€)", font=dict(size=13)), margin=dict(t=40))
    _chart(fig, "pl_beitrag")

    st.caption("Gewichte auf ein Ziel ausrichten: Bereich „⚖️ Gewichtung“ → „🎯 Auf Ziel rechnen“.")


# --- 4 Fundamental Basket ---------------------------------------------------
def _b_korb(m, R, fund, fund_stand, je_score, korb_score, hist_korb):
    korb_asset = _asset(m, "korb")
    _abschnitt("Fundamental Growth Basket")
    if korb_asset is None:
        st.info("Kein Korb-Baustein im Modell.")
        return
    st.markdown('<span class="pl-badge pl-warn">⚠ Historical Winner Bias</span>'
                '<span class="pl-badge pl-info">Szenarioannahme</span>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    anteil = c1.slider("Anteil des Korbs am Gesamtportfolio (%)", 0.0, 50.0,
                       float(korb_asset.get("targetWeight") or 0.0), step=0.5, key=_k("korb_anteil"))
    if abs(anteil - float(korb_asset.get("targetWeight") or 0)) > 1e-9:
        korb_asset["targetWeight"], korb_asset["enabled"] = anteil, anteil > 0
    methoden = list(E.KORB_METHODEN)
    m["korb_methode"] = c2.selectbox("Gewichtung im Korb", methoden, index=methoden.index(m.get("korb_methode", "manual")),
                                     format_func=E.KORB_METHODEN.get, key=_k("korb_meth"))
    if m["korb_methode"] != "manual":
        neu = E.korb_gewichte(m["korb"], m["korb_methode"], {i: s["gesamt"] for i, s in je_score.items()}, fund)
        for x in m["korb"]:
            x["gewicht"] = neu.get(x["id"], x["gewicht"])

    # Renditeannahmen des Korbs
    c3, c4, c5 = st.columns(3)
    for spalte, sz, titel in ((c3, "bear", "Bear % p.a."), (c4, "base", "Base % p.a."), (c5, "bull", "Bull % p.a.")):
        alt = E.annahme(m, "korb", sz)
        wert = spalte.number_input(titel, -50.0, 100.0, float(alt["value"] * 100) if alt else 0.0, step=1.0,
                                   key=_k(f"korb_{sz}"))
        if alt is None or abs(alt["value"] - wert / 100) > 1e-9:
            E.setze_annahme(m, "korb", sz, wert / 100, notiz="Szenarioannahme")
            if sz == "base":
                E.setze_annahme(m, "korb", "manualScenario", wert / 100,
                                notiz="Default-Modellrendite des Aktienkorbs – Szenarioannahme.")

    manuell = m.setdefault("manuell", {})
    df = pd.DataFrame([{
        "Aktie": x["name"], "Gewicht %": float(x["gewicht"]),
        "Score": je_score[x["id"]]["gesamt"],
        "Moat 0–10": (manuell.get(x["id"]) or {}).get("moat"),
        "Risiko 0–10": (manuell.get(x["id"]) or {}).get("risiko"),
        "5J p.a. %": None if (hist_korb.get(x["id"]) or {}).get("historical5Y") is None
        else round(hist_korb[x["id"]]["historical5Y"] * 100, 1),
        "Sektor": x["sektor"],
    } for x in m["korb"]])
    ed = _editor_formular(
        df, key=_k("korb_ed"), hide_index=True, width="stretch", height=_hoehe(len(df)),
        disabled=["Aktie", "Score", "5J p.a. %", "Sektor"] + ([] if m["korb_methode"] == "manual" else ["Gewicht %"]),
        column_config={
            "Gewicht %": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=0.5, format="%.1f"),
            "Score": st.column_config.NumberColumn(format="%.0f", help="Fundamental Score 0–100"),
            "Moat 0–10": st.column_config.NumberColumn(min_value=0, max_value=10, step=1,
                                                       help="Manuell: Marktstellung, Wechselkosten, Netzwerk, Technologie"),
            "Risiko 0–10": st.column_config.NumberColumn(min_value=0, max_value=10, step=1,
                                                         help="Manuell: 0 = hohes Risiko … 10 = geringes"),
            "5J p.a. %": st.column_config.NumberColumn(format="%.1f", help="Historisch (Winner Bias!)"),
        })
    geaendert = False
    for i, x in enumerate(m["korb"]):
        z = ed.iloc[i]
        if m["korb_methode"] == "manual" and not pd.isna(z["Gewicht %"]) and abs(float(z["Gewicht %"]) - x["gewicht"]) > 1e-9:
            x["gewicht"] = float(z["Gewicht %"])
            geaendert = True
        for feld, spalte in (("moat", "Moat 0–10"), ("risiko", "Risiko 0–10")):
            neu = None if pd.isna(z[spalte]) else float(z[spalte])
            if (manuell.get(x["id"]) or {}).get(feld) != neu:
                manuell.setdefault(x["id"], {})[feld] = neu
                geaendert = True
    if geaendert:
        st.rerun()
    summe = sum(float(x["gewicht"]) for x in m["korb"])
    if abs(summe - 100) > 0.05:
        st.warning(f"Korb = {_de(summe, 1)} % – für die Rechnung wird auf 100 % skaliert.")

    _kacheln([
        ("Korb-Score", _de(korb_score, 0) if korb_score is not None else "–", "gewichtet, 0–100"),
        ("Annahme Base", _pct((E.annahme(m, "korb", "base") or {}).get("value")), "Szenarioannahme"),
        ("Fundamental-Modell", _pct((R["info"].get("korb") or {}).get("brutto")) if m["rahmen"]["methode"] ==
         "fundamentalModel" else _pct(E.korb_fundamental_rendite(m["korb"], fund)[0]),
         "FCF-Rendite + Wachstum"),
        ("Halbleiteranteil", _pct(E.korb_anteile(m["korb"], D.KORB_HALBLEITER)), "im Korb"),
    ], klein=True)

    ids = [x["id"] for x in m["korb"]]
    sc = [je_score[i]["gesamt"] for i in ids]
    fig = go.Figure(go.Bar(
        x=[x["name"] for x in m["korb"]], y=[x["gewicht"] for x in m["korb"]],
        marker_color=["#8A9099" if s is None else "#16C784" if s >= 70 else "#F5B942" if s >= 50 else "#EA3943"
                      for s in sc],
        text=["–" if s is None else f"{s:.0f}" for s in sc], textposition="outside",
        hovertemplate="%{x}: %{y:.1f} % · Score %{text}<extra></extra>"))
    _layout(fig, 320, legende=False, eur=False)
    fig.update_layout(title=dict(text="Gewicht im Korb (%) · Zahl = Fundamental Score", font=dict(size=13)),
                      margin=dict(t=40))
    _chart(fig, "pl_korb")

    with st.expander("Fundamental Score: Kategorien & Gewichte", expanded=False):
        regeln = m["bewertungsregeln"]
        spalten = st.columns(3)
        for n, (key, r) in enumerate(regeln.items()):
            r["gewicht"] = float(spalten[n % 3].number_input(r["titel"], 0.0, 100.0, float(r["gewicht"]), step=5.0,
                                                             key=_k(f"sw_{key}")))
        st.caption(f"Summe {_de(sum(r['gewicht'] for r in regeln.values()), 0)} – wird auf 100 normiert. "
                   "Jede Kennzahl wird linear zwischen einer schwachen und einer starken Schwelle bewertet; "
                   "Kategorien ohne Daten fallen heraus, unter 50 % Abdeckung kein Gesamtwert.")
        kopf = ["Aktie"] + [r["titel"] for r in regeln.values()] + ["Gesamt"]
        zeilen = []
        for x in m["korb"]:
            s = je_score[x["id"]]
            zeilen.append([_esc(x["name"])] + [_de(s["kategorien"].get(k), 0) for k in regeln] + [
                f'<b>{_de(s["gesamt"], 0)}</b>'])
        _tabelle(kopf, zeilen)
    st.caption(f"Kennzahlen: Qualitäts-Agent (Yahoo-Finance-Jahresabschlüsse), Stand "
               f"{_datum(fund_stand)} · {len(fund)} von {len(m['korb'])} Aktien mit Daten. Der Korb wurde aus "
               "Unternehmen gebildet, die zuletzt stark gelaufen sind – deren Vergangenheitsrendite ist keine "
               "faire Zukunftserwartung.")


def _datum(iso):
    try:
        return datetime.datetime.fromisoformat(str(iso)).strftime("%d.%m.%Y")
    except Exception:
        return iso or "–"


# --- 5 Wikifolio Analyse ----------------------------------------------------
def _b_wiki(m, R, hist_assets):
    _abschnitt("Wikifolio Analyse")
    wikis = [a for a in m["assets"] if a["category"] == "wikifolio"]
    if not wikis:
        st.info("Keine Wikifolios im Modell.")
        return
    zeilen = []
    for a in wikis:
        h = hist_assets.get(a["id"]) or {}
        info = R["info"].get(a["id"]) or {}
        herkunft = info.get("herkunft") or {}
        quelle_txt = herkunft.get("source") if herkunft.get("sourceType") == "historisch" else "Annahme"
        conf = R["conf"].get(a["id"]) or E.confidence_score(h.get("jahre"), "wikifolio")
        zeilen.append([
            f'<span class="pt-name">{_esc(a["name"])}</span><span class="pt-sub">'
            f'{_esc(h.get("wkn") or a.get("ticker") or "WKN offen")} · {_esc(a.get("emittent") or "–")}</span>',
            f'<b>{_pct(info.get("brutto"), 1)}</b><span class="pt-sub">{_esc(quelle_txt)}</span>',
            f'{_de(conf)}/100',
            _de(h.get("jahre"), 1) + " J." if h.get("jahre") else "–",
            _pct(h.get("gesamt_cagr")) if h.get("gesamt_cagr") is not None else
            (_pct(h.get("seit_start")) + " ges." if h.get("seit_start") is not None else "–"),
            _pct(h.get("historical5Y")),
            _pct(h.get("vola")),
            _pct(h.get("maxdd"), 0, anteil=False),
            _pct(a.get("performanceFee"), 0),
            _pct(a.get("expenseRatio"), 2),
            _de(a.get("leverage") or 1, 1) + "×",
        ])
    _tabelle(["Wikifolio", "Genutzt p.a.", "Confidence", "Historie", "Ø seit Start", "5 J. p.a.", "Vola",
              "Max. DD", "Perf.-Fee", "Kosten", "Hebel"], zeilen)
    for a in wikis:
        h = hist_assets.get(a["id"]) or {}
        if h.get("fehler"):
            st.caption(f"{a['name']}: {h['fehler']}")
    st.caption("„Genutzt p.a.“ = tatsächliche Rendite laut Kurshistorie (5 J. p.a., sonst 3 J., sonst seit Start, "
               "sonst 1 J.; bei weniger als 1 Jahr Historie die Rendite seit Start, nicht hochgerechnet). "
               "Die eigene Annahme gilt nur, wenn keine Kurshistorie vorliegt oder im Portfolio "
               "Builder „Ist“ abgewählt ist. Vergangene Renditen sind keine Zukunftserwartung. Confidence misst nur, wie lang und belastbar die investierbare Historie ist – z. B. "
               "„Expected Return 50 % / Data Confidence 22/100“. Performance Fee und Kosten nur, soweit unter "
               "„🗂️ Daten → Annahmen & Quellen“ eingetragen.")
    fig = go.Figure()
    for n, a in enumerate(wikis):
        mon = (hist_assets.get(a["id"]) or {}).get("monat") or []
        if len(mon) < 2:
            continue
        basis = mon[0][1]
        fig.add_trace(go.Scatter(x=[d for d, _ in mon], y=[v / basis * 100 for _, v in mon], name=a["name"],
                                 line=dict(color=FARBEN[n % len(FARBEN)], width=2)))
    if fig.data:
        _layout(fig, 320, eur=False)
        fig.update_layout(title=dict(text="Investierbare Historie (Start = 100)", font=dict(size=13)), margin=dict(t=46))
        _chart(fig, "pl_wiki_hist")
    anteil = sum(w for i, w in E.gewichte(m).items() if _asset(m, i)["category"] == "wikifolio")
    st.markdown(f'<div class="pl-zeile">Wikifolio-Anteil am Portfolio: <b>{_pct(anteil)}</b> · '
                f'Anteil am Modell-Endwert: <b>{_pct(sum(v for i, v in R["zus"]["projektion"]["endwerte_asset"].items() if _asset(m, i)["category"] == "wikifolio") / (R["zus"]["endwert"] or 1))}</b></div>',
                unsafe_allow_html=True)


# --- 6 Szenariovergleich ----------------------------------------------------
def _b_szenarien(m, R, historie, h):
    _abschnitt("Szenariovergleich")
    s = E.szenario_vergleich(m, historie, rebalancing=R["reb"])
    rahmen = m["rahmen"]
    ein = rahmen["startkapital"] + (rahmen.get("sparrate_monat") or 0) * 12 * rahmen["horizont_jahre"]
    zeilen = []
    for sz in ("bear", "base", "bull", "custom"):
        v = s[sz]
        zeilen.append([sz.capitalize(), f'<b>{_eur(v["endwert"])}</b>',
                       _pct(v["cagr"]) if v["cagr"] is not None else "–",
                       _pct(v["max_verlust_stress"], 0, anteil=False), _de(ein) + " €",
                       '<span class="pl-gut">ja</span>' if v["ziel_erreicht"] else '<span class="pl-schlecht">nein</span>',
                       ("+" if v["abstand"] >= 0 else "−") + _de(abs(E.runden_ungefaehr(v["abstand"]) or 0)) + " €"])
    _tabelle(["Szenario", "Endwert", "CAGR", "Max. Verlust*", "Einzahlungen", "Ziel", "Abstand"], zeilen)
    st.caption("* im Stresspfad (Markteinbruch unter „⚠️ Risiko → Stress & Reserve“). Custom = eigene Custom-Annahmen, "
               "sonst Base. " + m["szenario_regel"]["text"])
    fig = go.Figure(go.Bar(x=["Bear", "Base", "Bull", "Custom"], y=[s[x]["endwert"] for x in ("bear", "base", "bull", "custom")],
                           marker_color=["#EA3943", "#4C9AFF", "#16C784", "#A78BFA"],
                           hovertemplate="%{x}: %{y:,.0f} €<extra></extra>"))
    fig.add_hline(y=rahmen["zielvermoegen"], line=dict(color="#F5B942", dash="dash"), annotation_text="Ziel",
                  annotation_font_color="#F5B942")
    _layout(fig, 320, legende=False)
    _chart(fig, "pl_szen")



def _b_modelle(m, R, historie, h):
    _abschnitt("Gespeicherte Modelle")
    st.caption(f"Aktives Modell: „{st.session_state.get('planer_name') or 'Aktuelles Modell'}“ – Änderungen werden "
               "automatisch darin gespeichert. Für eine Variante erst unter neuem Namen speichern, dann ändern.")
    daten = _lade_gespeichert(h)
    vorhanden = list(daten["szenarien"])
    c1, c2 = st.columns([2, 1])
    vorschlag = D.SZENARIO_NAMEN + [n for n in vorhanden if n not in D.SZENARIO_NAMEN]
    aktuell = st.session_state.get("planer_name") or "Aktuelles Modell"
    name = c1.selectbox("Name", vorschlag + ["Eigener Name …"],
                        index=vorschlag.index(aktuell) if aktuell in vorschlag else 0, key=_k("sz_name"))
    if name == "Eigener Name …":
        name = c1.text_input("Eigener Name", key=_k("sz_eigen")).strip()
    if c2.button("💾 Speichern", key=_k("sz_save"), width="stretch", disabled=not name):
        daten["szenarien"][name] = {"modell": copy.deepcopy(m), "gespeichert": datetime.datetime.now().isoformat(
            timespec="minutes")}
        daten["aktiv"] = name
        if h["gh_write"](PFAD_SZENARIEN, daten, message=f"planer: szenario {name} [skip ci]"):
            st.session_state["planer_name"] = name
            st.session_state["planer_hash"] = _hash(m)
            st.success(f"„{name}“ gespeichert.")
        else:
            st.error("Speichern nicht möglich (GitHub-Speicher nicht verfügbar).")
    if vorhanden:
        c3, c4, c5 = st.columns([2, 1, 1])
        laden = c3.selectbox("Gespeichertes Modell", vorhanden, key=_k("sz_laden"))
        if c4.button("Laden", key=_k("sz_load"), width="stretch"):
            st.session_state["planer_modell"] = _migriere(daten["szenarien"][laden]["modell"])
            st.session_state["planer_name"] = laden
            st.session_state["planer_hash"] = _hash(st.session_state["planer_modell"])
            st.session_state.pop("planer_opt", None)
            _neu_zeichnen()
            st.rerun()
        if c5.button("Löschen", key=_k("sz_del"), width="stretch"):
            daten["szenarien"].pop(laden, None)
            if daten.get("aktiv") == laden:
                daten["aktiv"] = None
            if st.session_state.get("planer_name") == laden:
                st.session_state["planer_name"] = None      # naechste Aenderung -> "Aktuelles Modell"
                st.session_state["planer_hash"] = None
            h["gh_write"](PFAD_SZENARIEN, daten, message=f"planer: szenario {laden} geloescht [skip ci]")
            _neu_zeichnen()
            st.rerun()
        zeilen = []
        for n, e in daten["szenarien"].items():
            try:
                mm = _migriere(e["modell"])
                r = E.rendite_map(E.alle_renditen(mm, historie))
                zz = E.zusammenfassung(mm, r, rebalancing=mm["rebalancing"])
                rk = E.risiko_kennzahlen(mm, r, E.confidence_fuer(mm, historie), historie)
                zeilen.append([_esc(n), f'<b>{_eur(zz["endwert"])}</b>', _pct(zz["modell_cagr"]),
                               _pct(rk["wikifolio_anteil"], 0, anteil=False), _pct(rk["hebel_anteil"], 0, anteil=False),
                               _pct(rk["max_gewicht"], 0, anteil=False), _de(rk["confidence_gewichtet"]),
                               _datum(e.get("gespeichert"))])
            except Exception as ex:
                zeilen.append([_esc(n), f"Fehler: {_esc(ex)}"] + ["–"] * 6)
        _tabelle(["Modell", "Endwert", "p.a.", "Wikifolios", "Hebel", "Max. Gew.", "Conf.", "Gespeichert"], zeilen)
        st.caption("Alle gespeicherten Modelle mit den heutigen Kursdaten neu gerechnet.")


# --- 7 Risiko & Konzentration -----------------------------------------------
def _b_risiko(m, R, historie):
    rk = E.risiko_kennzahlen(m, R["r"], R["conf"], historie)
    if not rk:
        st.info("Keine aktiven Bausteine.")
        return
    _abschnitt("Risiko & Konzentration")
    _kacheln([
        ("Größte Position", _pct(rk["max_gewicht"], 0, anteil=False), _esc(rk["max_gewicht_name"])),
        ("Effektive Positionen", _de(rk["effektive_positionen"], 1), "1 / Summe Gewicht²"),
        ("Unabhängige Treiber", _de(rk["unabhaengige_treiber"], 1), "Welt, US-Tech, je Wikifolio, Korb"),
        ("Cash-Quote", _pct(rk["cash_quote"], 0, anteil=False), "Nachkaufreserve"),
        ("Wikifolio-Anteil", _pct(rk["wikifolio_anteil"], 0, anteil=False), None),
        ("Hebel-Anteil", _pct(rk["hebel_anteil"], 0, anteil=False),
         f'Exposure {_pct(rk["hebel_exposure"], 0, anteil=False)}'),
        ("Halbleiter (bekannt)", _pct(rk["semi_bekannt"], 0, anteil=False),
         _esc("+ unbekannt in: " + ", ".join(rk["semi_unbekannt"])) if rk["semi_unbekannt"] else None),
        ("Max. Drawdown (Modell)", _pct(rk["drawdown_gewichtet"], 0, anteil=False), "alle gleichzeitig"),
    ], klein=True)
    _kacheln([
        ("Ø Rendite (gewichtet)", _pct(rk["rendite_gewichtet"]), "aktive Quelle"),
        ("Ø Confidence", _de(rk["confidence_gewichtet"]) + "/100", "Datenbasis"),
        ("Confidence-adj. Rendite", _pct(rk["confidence_adjusted_return"]),
         "interne Kennzahl: Rendite × Conf./100"),
        ("Tech (bekannt)", _pct(rk["tech_bekannt"], 0, anteil=False),
         "Indizes ohne Holdings nicht gezählt" if rk["tech_unbekannt"] else None),
    ], klein=True)

    w = E.gewichte(m)
    gruppen = {}
    for i, g in w.items():
        a = _asset(m, i)
        if a["category"] == "cash":
            titel = "Reserve"
        else:
            titel = E.TREIBER_GRUPPEN.get(a["category"], a["name"])
        gruppen[titel] = gruppen.get(titel, 0.0) + g * 100
    gr = sorted(gruppen.items(), key=lambda x: -x[1])
    fig = go.Figure(go.Bar(x=[v for _, v in gr], y=[k for k, _ in gr], orientation="h", marker_color="#4C9AFF",
                           hovertemplate="%{y}: %{x:.1f} %<extra></extra>"))
    _layout(fig, 60 + 32 * len(gr), legende=False, eur=False)
    fig.update_yaxes(autorange="reversed", side="left")
    fig.update_layout(title=dict(text="Anteil je Renditetreiber (%)", font=dict(size=13)), margin=dict(t=40))
    _chart(fig, "pl_treiber")

    _abschnitt("Effektive Exposure")
    x = E.effektive_exposure(m)
    top = list(x["firmen"].items())[:12]
    if top:
        _tabelle(["Unternehmen", "Direkt", "Über ETFs", "Effektiv"],
                 [[_esc(n), _pct(v["direkt"], 2, anteil=False), _pct(v["indirekt"], 2, anteil=False) if v["indirekt"] else "–",
                   f'<b>{_pct(v["effektiv"], 2, anteil=False)}</b>'] for n, v in top])
    c1, c2 = st.columns(2)
    with c1:
        _tabelle(["Sektor", "Anteil"], [[_esc(k), _pct(v, 1, anteil=False)] for k, v in x["sektoren"].items()])
    with c2:
        _tabelle(["Region", "Anteil"], [[_esc(k), _pct(v, 1, anteil=False)] for k, v in x["regionen"].items()])
    st.caption("ETF-Bestände (Holdings) sind noch nicht hinterlegt – die indirekte Exposure über Indizes "
               "(z. B. Nvidia im Nasdaq 100) fehlt daher. Die Struktur ist vorbereitet "
               "(Modellfeld „holdings“: {ETF: {Firma: Anteil %}}).")


# --- 8 Nachkaufreserve ------------------------------------------------------
def _b_reserve(m, R):
    _abschnitt("Nachkaufreserve")
    nk, stress = m["nachkauf"], m["stress"]
    res = _asset(m, "reserve")
    if res is None or not res.get("enabled"):
        st.info("Die Nachkaufreserve ist deaktiviert (🧩 Portfolio → Bausteine).")
    c1, c2 = st.columns(2)
    if res is not None:
        neu = c1.number_input("Reserve (% des Portfolios)", 0.0, 60.0, float(res.get("targetWeight") or 0), step=1.0,
                              key=_k("res_w"))
        if abs(neu - float(res.get("targetWeight") or 0)) > 1e-9:
            res["targetWeight"], res["enabled"] = neu, neu > 0
    ziele = list(D.NACHKAUF_ZIELE)
    nk["ziel"] = c2.selectbox("Ziel der Tranchen", ziele, index=ziele.index(nk.get("ziel", "proportional")),
                              format_func=D.NACHKAUF_ZIELE.get, key=_k("nk_ziel"))
    if nk["ziel"] == "asset":
        auswahl = [a["id"] for a in m["assets"] if a.get("enabled") and a["category"] != "cash"]
        if auswahl:
            nk["ziel_asset"] = st.selectbox("Baustein", auswahl, format_func=lambda i: _asset(m, i)["name"],
                                            index=auswahl.index(nk["ziel_asset"]) if nk.get("ziel_asset") in auswahl else 0,
                                            key=_k("nk_asset"))
    c3, c4 = st.columns(2)
    nk["min_score_aktiv"] = c3.toggle("Einzelwerte/Korb nur mit Mindest-Score", value=bool(nk.get("min_score_aktiv")),
                                      key=_k("nk_ms"))
    nk["min_score"] = float(c4.number_input("Mindest-Score", 0.0, 100.0, float(nk.get("min_score", 70)), step=5.0,
                                            key=_k("nk_score"), disabled=not nk["min_score_aktiv"]))
    df = pd.DataFrame([{"Tranche": n + 1, "Drawdown %": t["drawdown"], "Anteil der Reserve %": round(t["anteil"] * 100, 1)}
                       for n, t in enumerate(nk["tranchen"])])
    ed = st.data_editor(df, key=_k("tranchen"), hide_index=True, height=_hoehe(len(df)), width="stretch", disabled=["Tranche"],
                        column_config={"Drawdown %": st.column_config.NumberColumn(min_value=-95.0, max_value=0.0, step=5.0),
                                       "Anteil der Reserve %": st.column_config.NumberColumn(min_value=0.0, max_value=100.0,
                                                                                             step=5.0)})
    for n, t in enumerate(nk["tranchen"]):
        d, a = ed.iloc[n]["Drawdown %"], ed.iloc[n]["Anteil der Reserve %"]
        if not pd.isna(d):
            t["drawdown"] = float(d)
        if not pd.isna(a) and abs(float(a) - round(t["anteil"] * 100, 1)) > 1e-9:
            t["anteil"] = float(a) / 100
    st.caption("Regelbasiert: Eine Tranche wird nur bei einem Markt-Drawdown ab der Schwelle eingesetzt. Ein "
               "Kursrückgang allein ist kein Grund – Einzelwerte bzw. der Korb kommen nur bei ausreichendem "
               "Fundamental Score in Frage.")

    with st.expander("Stress-Szenario", expanded=False):
        s1, s2, s3 = st.columns(3)
        stress["einbruch"] = float(s1.number_input("Einbruch (%)", 0.0, 90.0, float(stress["einbruch"]), step=5.0,
                                                   key=_k("st_e")))
        stress["start"] = int(s2.number_input("Beginn (Monat)", 1, 480, int(stress["start"]), key=_k("st_s")))
        stress["dauer"] = int(s3.number_input("Dauer (Monate)", 1, 60, int(stress["dauer"]), key=_k("st_d")))
        s4, s5 = st.columns(2)
        stress["erholung"] = int(s4.number_input("Erholung (Monate)", 1, 120, int(stress["erholung"]), key=_k("st_r")))
        stress["wikifolio_beta"] = float(s5.number_input("Wikifolio-Beta", 0.0, 3.0, float(stress["wikifolio_beta"]),
                                                         step=0.1, key=_k("st_b")))
        st.caption("Modellhafter Markteinbruch zusätzlich zum Trend der Annahmen. Hebelprodukte fallen mit ihrem "
                   "Hebel, Cash gar nicht.")

    ohne = E.projektion(m, R["r"], rebalancing=R["reb"], stress=stress)
    mit = E.projektion(m, R["r"], rebalancing=R["reb"], stress=stress, nachkauf=nk, scores=R["scores"],
                       confidences=R["conf"])
    x = [i / 12 for i in range(len(mit["monatswerte"]))]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=ohne["monatswerte"], name="Reserve bleibt Cash", line=dict(color="#8A9099", width=2)))
    fig.add_trace(go.Scatter(x=x, y=mit["monatswerte"], name="Mit Tranchen", line=dict(color="#16C784", width=3)))
    for n in mit["nachkaeufe"]:
        fig.add_trace(go.Scatter(x=[n["monat"] / 12], y=[mit["monatswerte"][n["monat"]]], mode="markers",
                                 marker=dict(color="#F5B942", size=11, symbol="triangle-up"), showlegend=False,
                                 hovertemplate=f"Tranche bei {_de(n['drawdown'], 0)} %: {_de(n['betrag'])} €<extra></extra>"))
    _layout(fig, 340)
    fig.update_xaxes(title="Jahre")
    _chart(fig, "pl_reserve")
    _kacheln([
        ("Endwert ohne Einsatz", _eur(ohne["endwert"]), "Stresspfad"),
        ("Endwert mit Tranchen", _eur(mit["endwert"]), "Stresspfad"),
        ("Tranchen ausgelöst", str(len(mit["nachkaeufe"])), f'von {len(nk["tranchen"])}'),
        ("Max. Verlust", _pct(mit["max_verlust_pfad"], 0, anteil=False), "im Stresspfad"),
    ], klein=True)
    if mit["nachkaeufe"]:
        namen = {a["id"]: a["name"] for a in m["assets"]}
        _tabelle(["Monat", "Markt-DD", "Betrag", "Verteilung"],
                 [[str(n["monat"]), _pct(n["drawdown"], 0, anteil=False), _de(n["betrag"]) + " €",
                   _verteilung(n["ziele"], namen)]
                  for n in mit["nachkaeufe"]], links=(3,))
    elif R["scores"].get("korb") is None and nk.get("min_score_aktiv") and nk.get("ziel") == "bester_score":
        st.caption("Kein Fundamental Score verfügbar – Tranchen gehen nicht in Einzelwerte.")
    _hinweis()


def _verteilung(ziele, namen, max_n=3):
    teile = sorted(((b, i) for i, b in ziele.items() if b >= 1), reverse=True)
    txt = ", ".join(f"{namen[i]} {_de(b)} €" for b, i in teile[:max_n])
    if len(teile) > max_n:
        txt += f" + {len(teile) - max_n} weitere"
    return _esc(txt)


# --- 9 Sensitivitaet --------------------------------------------------------
def _b_sensitiv(m, R):
    _abschnitt("Sensitivität (Tornado)")
    delta = st.select_slider("Abweichung je Annahme", options=[5, 10, 15, 20, 30], value=10,
                             format_func=lambda v: f"± {v} Pp.", key="pl_tornado_delta")
    basis, zeilen = E.tornado(m, R["r"], delta / 100.0, rebalancing=R["reb"])
    namen = {a["id"]: a["name"] for a in m["assets"]}
    zeilen = [z for z in zeilen if z["spanne"] > 1][:10]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=[namen[z["id"]] for z in zeilen], x=[z["tief"] - basis for z in zeilen], base=basis,
                         orientation="h", name=f"−{delta} Pp.", marker_color="#EA3943",
                         hovertemplate="%{y}: %{x:,.0f} €<extra></extra>"))
    fig.add_trace(go.Bar(y=[namen[z["id"]] for z in zeilen], x=[z["hoch"] - basis for z in zeilen], base=basis,
                         orientation="h", name=f"+{delta} Pp.", marker_color="#16C784",
                         hovertemplate="%{y}: %{x:,.0f} €<extra></extra>"))
    fig.add_vline(x=basis, line=dict(color="#FFFFFF", width=1))
    _layout(fig, 80 + 34 * len(zeilen))
    fig.update_layout(barmode="overlay", hovermode="closest")
    fig.update_yaxes(autorange="reversed", side="left", tickformat=None)
    fig.update_xaxes(tickformat=",.0f")
    _chart(fig, "pl_tornado")
    st.caption(f"Endwert, wenn EINE Annahme um ± {delta} Prozentpunkte abweicht (Basis {_eur(basis)}). "
               "Oben stehen die Annahmen, von denen das Ergebnis am stärksten abhängt.")

    wiki_ids = [a["id"] for a in m["assets"] if a["category"] == "wikifolio" and a.get("enabled")]
    if wiki_ids:
        _abschnitt("Wikifolios gemeinsam")
        stufen = [0.50, 0.40, 0.30, 0.20, 0.10, 0.0]
        erg = E.gruppen_sensitivitaet(m, R["r"], wiki_ids, stufen, rebalancing=R["reb"])
        fig2 = go.Figure(go.Bar(x=[_pct(s, 0) for s, _ in erg], y=[v for _, v in erg],
                                marker_color=["#16C784" if v >= m["rahmen"]["zielvermoegen"] else "#4C9AFF" for _, v in erg],
                                hovertemplate="Wikifolios %{x} p.a.: %{y:,.0f} €<extra></extra>"))
        fig2.add_hline(y=m["rahmen"]["zielvermoegen"], line=dict(color="#F5B942", dash="dash"))
        _layout(fig2, 300, legende=False)
        fig2.update_xaxes(title="Rendite aller Wikifolios p.a.")
        _chart(fig2, "pl_wiki_sens")
        _tabelle(["Wikifolios p.a.", "Endwert", "Ziel"],
                 [[_pct(s, 0), _eur(v), '<span class="pl-gut">ja</span>' if v >= m["rahmen"]["zielvermoegen"]
                   else '<span class="pl-schlecht">nein</span>'] for s, v in erg])
    _hinweis()


# --- 10 Annahmen & Datenqualitaet -------------------------------------------
def _b_annahmen(m, R, historie, hist_assets):
    _abschnitt("Annahmen (Assumption Layer)")
    quellen = ["manualScenario", "bear", "base", "bull", "custom"]
    titel = {"manualScenario": "Eigene %", "bear": "Bear %", "base": "Base %", "bull": "Bull %", "custom": "Custom %"}
    zeilen = []
    for a in m["assets"]:
        z = {"Baustein": a["name"]}
        for q in quellen:
            an = E.annahme(m, a["id"], q)
            z[titel[q]] = None if not an else round(an["value"] * 100, 2)
        eig = E.annahme(m, a["id"], "manualScenario")
        z["Notiz"] = (eig or {}).get("notes", "")
        zeilen.append(z)
    ed = _editor_formular(pd.DataFrame(zeilen), key=_k("annahmen"), hide_index=True, height=_hoehe(len(zeilen)), width="stretch",
                        disabled=["Baustein"],
                        column_config={t: st.column_config.NumberColumn(t, step=0.5, format="%.2f") for t in titel.values()})
    geaendert = False
    for i, a in enumerate(m["assets"]):
        for q in quellen:
            v = ed.iloc[i][titel[q]]
            alt = E.annahme(m, a["id"], q)
            if pd.isna(v):
                if alt is not None and q != "manualScenario":
                    m["annahmen"] = [x for x in m["annahmen"] if not (x["assetId"] == a["id"] and x["sourceType"] == q)]
                    geaendert = True
                continue
            if alt is None or abs(alt["value"] * 100 - float(v)) > 0.006:
                E.setze_annahme(m, a["id"], q, float(v) / 100)
                geaendert = True
        notiz = ed.iloc[i]["Notiz"]
        eig = E.annahme(m, a["id"], "manualScenario")
        if eig is not None and isinstance(notiz, str) and notiz != eig.get("notes", ""):
            eig["notes"] = notiz
            geaendert = True
    if geaendert:
        st.rerun()
    c1, c2 = st.columns(2)
    regel = m["szenario_regel"]
    regel["bear_faktor"] = float(c1.number_input("Bear = Basis ×", 0.0, 2.0, float(regel["bear_faktor"]), step=0.05,
                                                 key=_k("rb")))
    regel["bull_faktor"] = float(c2.number_input("Bull = Basis ×", 0.0, 3.0, float(regel["bull_faktor"]), step=0.05,
                                                 key=_k("rbu")))
    regel["text"] = (f"Fehlt eine eigene Bear-/Bull-Annahme: Bear = {_de(regel['bear_faktor'] * 100)} %, "
                     f"Bull = {_de(regel['bull_faktor'] * 100)} % der Basisannahme.")

    _abschnitt("Historical Layer & Datenqualität")
    zeilen = []
    for a in m["assets"]:
        h = historie.get(a["id"]) or {}
        ha = hist_assets.get(a["id"]) or {}
        info = R["info"].get(a["id"]) or {}
        conf = R["conf"].get(a["id"])
        badges = "".join(f'<span class="pl-badge pl-warn">{_esc(b)}</span>'
                         for b in E.bias_hinweise(a, info, conf)) if a.get("enabled") else ""
        if info.get("hinweis"):
            badges += f'<span class="pl-badge pl-info">{_esc(info["hinweis"])}</span>'
        quelle = (info.get("herkunft") or {}).get("sourceType") or "–"
        zeilen.append([
            f'<span class="pt-name">{_esc(a["name"])}</span><span class="pt-sub">'
            f'{_esc(ha.get("instrument") or ha.get("fehler") or "")}</span>{badges}',
            _pct(info.get("brutto")) if a.get("enabled") else "aus",
            _esc(QUELLEN.get(quelle, quelle)),
            _pct(h.get("historical5Y")), _pct(h.get("historical10Y")), _pct(h.get("fundamentalModel")),
            (_de(h.get("jahre"), 1) + " J.") if h.get("jahre") else "–",
            f"{_de(conf)}/100" if conf is not None else "–",
            _datum(h.get("stand")) if h.get("stand") else "–",
        ])
    _tabelle(["Baustein", "Rendite", "Quelle", "Hist. 5J", "Hist. 10J", "Fundam.", "Historie", "Confidence",
              "Datenstand"], zeilen)
    st.caption("Zwei getrennte Ebenen: Historical Layer = gemessene Vergangenheit (ls-tc.de-Kurshistorie, "
               "Qualitäts-Agent), Assumption Layer = frei gewählte Annahmen für die Rechnung. Confidence misst "
               "nur die Länge/Belastbarkeit der Datenbasis (1 J. ≈ 22, 5 J. ≈ 71, 10 J. ≈ 92), keine "
               "Wahrscheinlichkeit. Werte ohne Quelle werden nicht erfunden, sondern bleiben leer.")

    ids = [a["id"] for a in m["assets"] if a.get("enabled") and a["category"] != "cash"]
    if ids:
        w = E.gewichte(m)
        fig = go.Figure(go.Scatter(
            x=[R["conf"].get(i) for i in ids], y=[(R["info"][i]["brutto"] or 0) * 100 for i in ids],
            mode="markers+text", text=[_asset(m, i)["name"][:18] for i in ids], textposition="top center",
            textfont=dict(size=10), marker=dict(size=[8 + w[i] * 120 for i in ids], color="#4C9AFF", opacity=0.75),
            hovertemplate="%{text}: %{y:.1f} % · Conf. %{x}<extra></extra>"))
        _layout(fig, 360, legende=False, eur=False)
        fig.update_layout(hovermode="closest")
        fig.update_xaxes(title="Data Confidence (0–100)", range=[0, 105])
        fig.update_yaxes(title="Angenommene Rendite % p.a.", side="left")
        _chart(fig, "pl_conf")
        st.caption("Rechts oben = hohe Annahme mit guter Datenbasis. Links oben = hohe Annahme mit dünner Datenbasis.")

    _abschnitt("Stammdaten")
    kats = list(D.KATEGORIEN)
    df = pd.DataFrame([{
        "Baustein": a["name"], "WKN/Ticker": a.get("ticker") or "", "ISIN": a.get("isin") or "",
        "Kategorie": a["category"], "TER %": None if a.get("expenseRatio") is None else a["expenseRatio"] * 100,
        "Perf.-Fee %": None if a.get("performanceFee") is None else a["performanceFee"] * 100,
        "Hebel": a.get("leverage") or 1.0, "Tech %": None if a.get("techAnteil") is None else a["techAnteil"] * 100,
        "Halbl. %": None if a.get("semiAnteil") is None else a["semiAnteil"] * 100,
    } for a in m["assets"]])
    ed = _editor_formular(df, key=_k("stamm"), hide_index=True, height=_hoehe(len(df)), width="stretch", disabled=["Baustein"],
                        column_config={"Kategorie": st.column_config.SelectboxColumn(options=kats),
                                       "TER %": st.column_config.NumberColumn(format="%.2f", step=0.05),
                                       "Perf.-Fee %": st.column_config.NumberColumn(format="%.0f", step=1.0),
                                       "Hebel": st.column_config.NumberColumn(format="%.1f", step=0.5),
                                       "Tech %": st.column_config.NumberColumn(format="%.0f", min_value=0, max_value=100),
                                       "Halbl. %": st.column_config.NumberColumn(format="%.0f", min_value=0, max_value=100)})
    geaendert = False

    def zahl(v, faktor=1.0):
        return None if pd.isna(v) else float(v) / faktor

    for i, a in enumerate(m["assets"]):
        z = ed.iloc[i]
        neu = {"ticker": (str(z["WKN/Ticker"]).strip() or None) if not pd.isna(z["WKN/Ticker"]) else None,
               "isin": (str(z["ISIN"]).strip() or None) if not pd.isna(z["ISIN"]) else None,
               "category": z["Kategorie"] if z["Kategorie"] in kats else a["category"],
               "expenseRatio": zahl(z["TER %"], 100), "performanceFee": zahl(z["Perf.-Fee %"], 100),
               "leverage": zahl(z["Hebel"]) or 1.0, "techAnteil": zahl(z["Tech %"], 100),
               "semiAnteil": zahl(z["Halbl. %"], 100)}
        for k, v in neu.items():
            alt = a.get(k)
            if (alt is None) != (v is None) or (v is not None and alt != v and not
                                                 (isinstance(v, float) and isinstance(alt, (int, float))
                                                  and abs(alt - v) < 1e-12)):
                a[k] = v
                geaendert = True
    if geaendert:
        st.rerun()
    st.caption("WKN/ISIN steuern die Kurssuche für den Historical Layer. Wikifolios ohne WKN werden per Name "
               "gesucht – bitte den gefundenen Namen oben prüfen.")



# --- 11 Entnahmeplan --------------------------------------------------------
def _entnahme_rechnen(m, R, e=None):
    """Entnahme aus dem Modell-Endwert der Aufbauphase (eine durchgehende Rechnung)."""
    e = e or _entnahme_daten(m)
    proj = R["zus"]["projektion"]
    kapital = proj["endwert"]
    einstand = min(proj["eingezahlt"], kapital)
    if e.get("rendite_quelle", "eigen") == "eigen":
        rendite = e["rendite_pa"] / 100.0
    elif R["zus"]["modell_cagr"] is not None:
        rendite = R["zus"]["modell_cagr"]
    else:
        # keine Aufbauphase (0 Jahre): gewichtete Portfoliorendite statt 0 %
        rendite = sum(g * R["r"].get(i, 0.0) for i, g in E.gewichte(m).items())
    kw = dict(dynamik_pa=e["dynamik_pa"] / 100.0, einstand=einstand,
              steuersatz=(e["steuersatz"] / 100.0) if e["steuer"] else 0.0,
              freibetrag=e["freibetrag"] if e["steuer"] else 0.0)
    plan = E.entnahmeplan(kapital, rendite, e["monatlich"], jahre=int(e["dauer_jahre"]), **kw)
    return kapital, rendite, kw, plan


def _dauer_text(p, jahre_max=100):
    if p["reicht_dauerhaft"]:
        return f"über {jahre_max} J."
    mon = p["dauer_monate"]
    return f"{mon // 12} J. {mon % 12} M." if mon % 12 else f"{mon // 12} J."


def _b_entnahme(m, R):
    e = _entnahme_daten(m)
    rahmen = m["rahmen"]
    proj = R["zus"]["projektion"]
    _abschnitt("Entnahmeplan (monatlich)")
    _hinweis("Szenariorechnung · keine Prognose · Entnahme beginnt nach dem Aufbau mit dem Modell-Endwert")
    if not e.get("aktiv", True):
        st.info("Die Entnahme ist ausgeschaltet – oben unter „⚙️ Planung: Aufbau → Entnahme“ einschalten.")
        return
    kapital, rendite, kw, plan = _entnahme_rechnen(m, R, e)
    st.caption("Alle Eingaben (Aufbau und Entnahme) stehen oben unter „⚙️ Planung: Aufbau → Entnahme“.")
    if e.get("rendite_quelle") == "modell":
        st.caption(f"Rendite in der Entnahme wie Aufbauphase: {_pct(rendite)} p.a. – so hohe Renditen über "
                   "Jahrzehnte durchzuhalten ist nicht plausibel; eine eigene Annahme ist meist ehrlicher.")
    jahre = e["dauer_jahre"]
    plan = E.entnahmeplan(kapital, rendite, e["monatlich"], jahre=jahre, **kw)
    verzehr = E.entnahme_fuer(kapital, rendite, jahre=jahre, **kw)
    erhalt = E.entnahme_fuer(kapital, rendite, jahre=jahre, ziel_restwert=kapital, **kw)
    reicht = plan["reicht_dauerhaft"] or plan["dauer_monate"] >= jahre * 12

    _kacheln([
        ("Startkapital", _eur(kapital), D.ENTNAHME_STARTS[e["start"]] + f" · nach {rahmen['horizont_jahre']} J."),
        ("Entnahme", f"{_de(e['monatlich'])} €", "pro Monat netto"
         + (f", +{_de(e['dynamik_pa'], 1)} % p.a." if e["dynamik_pa"] else "")),
        ("Kapital reicht", f'<span class="{"pl-gut" if reicht else "pl-schlecht"}">{_dauer_text(plan)}</span>',
         f"Plan: {jahre} J. bei {_pct(rendite)} p.a."),
        (f"Rest nach {jahre} J.", _eur(plan["restwert"]) if plan["restwert"] else "0 €",
         f"Steuern gesamt {_eur(plan['summe_steuer'])}" if e["steuer"] else "vor Steuern"),
    ])
    _kacheln([
        ("Kapitalverzehr", f"{_de(verzehr)} €", f"max. pro Monat, aufgebraucht nach {jahre} J."),
        ("Kapitalerhalt", f"{_de(erhalt)} €", f"max. pro Monat, nach {jahre} J. noch {_eur(kapital)}"),
    ], klein=True)
    st.caption("Kapitalverzehr/-erhalt: erste Monatsentnahme (netto) – mit derselben jährlichen Erhöhung.")

    # Chart: Aufbau + Entnahme auf einer Zeitachse
    aufbau = proj["monatswerte"]
    n_auf = len(aufbau) - 1
    x_auf = [i / 12 for i in range(n_auf + 1)]
    ent = plan["verlauf"][: jahre * 12 + 1] if plan["reicht_dauerhaft"] or (plan["dauer_monate"] or 0) >= jahre * 12 \
        else plan["verlauf"]
    x_ent = [(n_auf + i) / 12 for i in range(len(ent))]
    fig = go.Figure()
    if e["start"] == "modell":
        fig.add_trace(go.Scatter(x=x_auf, y=aufbau, name="Aufbau (Modell)", line=dict(color="#4C9AFF", width=2)))
    fig.add_trace(go.Scatter(x=x_ent, y=ent, name="Entnahmephase", line=dict(color="#16C784", width=3)))
    netto_kum, summe = [0.0], 0.0
    for i in range(1, len(ent)):
        summe += e["monatlich"] * (1 + e["dynamik_pa"] / 100.0) ** ((i - 1) // 12)
        netto_kum.append(summe)
    fig.add_trace(go.Scatter(x=x_ent, y=netto_kum, name="Summe Entnahmen", line=dict(color="#F5B942", dash="dot")))
    _layout(fig, 340)
    fig.update_xaxes(title="Jahre ab heute")
    _chart(fig, "pl_entnahme")

    _abschnitt("Rendite-Sensitivität")
    zeilen = []
    for d in (-0.04, -0.02, 0.0, 0.02):
        r = rendite + d
        p = E.entnahmeplan(kapital, r, e["monatlich"], jahre=jahre, **kw)
        ok = p["reicht_dauerhaft"] or p["dauer_monate"] >= jahre * 12
        zeilen.append([("<b>" if d == 0 else "") + _pct(r) + ("</b>" if d == 0 else ""),
                       f'<span class="{"pl-gut" if ok else "pl-schlecht"}">{_dauer_text(p)}</span>',
                       _eur(p["restwert"]) if p["restwert"] else "0 €",
                       _de(E.entnahme_fuer(kapital, r, jahre=jahre, **kw)) + " €"])
    _tabelle(["Rendite p.a.", "Reicht", f"Rest nach {jahre} J.", "Verzehr/Monat"], zeilen)
    st.caption("Konstante Renditen – echte Märkte schwanken. Verluste gleich zu Beginn der Entnahme wiegen deutlich "
               "schwerer (Reihenfolge-Risiko); der Stresspfad unter „⚠️ Risiko → Stress & Reserve“ zeigt die Aufbauphase.")

    _abschnitt("Jahresübersicht")
    tab = plan["jahre_tabelle"][:max(jahre, 1)]
    kopf = ["Jahr", "Anfang", "Erträge", "Entnahme netto"] + (["Steuer"] if e["steuer"] else []) + ["Ende"]
    _tabelle(kopf, [[str(rahmen["horizont_jahre"] + z["jahr"]), _de(z["anfang"]) + " €", _de(z["ertrag"]) + " €",
                     _de(z["netto"]) + " €"] + ([_de(z["steuer"]) + " €"] if e["steuer"] else [])
                    + [_de(z.get("ende", 0)) + " €"] for z in tab])
    st.caption("„Jahr“ = Jahre ab heute (Aufbauphase + Entnahmejahr). Beträge ungerundet zur Nachvollziehbarkeit – "
               "alle Werte bleiben Szenariorechnung.")


# ===========================================================================
# Einstieg
# ===========================================================================
def render(h):
    st.markdown(CSS, unsafe_allow_html=True)
    m = _modell(h)
    name = st.session_state.get("planer_name")
    st.markdown(f'<div class="abschnitt">💼 Portfolio-Planer{" · " + _esc(name) if name else ""}</div>',
                unsafe_allow_html=True)
    _hinweis("Szenariorechnung / keine Prognose – alle Renditen sind Annahmen oder historische Ausgangswerte, "
             "keine Erwartung und keine Anlageempfehlung.")

    status_platz = st.empty()
    _rahmen(m)
    kpi_platz = st.empty()
    warn_platz = st.empty()
    haupt = st.pills("Bereich", HAUPT, default=HAUPT[0], key="pl_haupt") or HAUPT[0]
    unter = None
    if UNTER[haupt]:
        unter = st.pills("Unterseite", UNTER[haupt], default=UNTER[haupt][0], key=f"pl_unter_{HAUPT.index(haupt)}",
                         label_visibility="collapsed") or UNTER[haupt][0]

    with st.spinner("Lade historische Daten …"):
        try:
            hist_assets, hist_korb = _historie(m, h)
        except Exception:
            hist_assets, hist_korb = {}, {}
        fund, fund_stand = _fundamentaldaten(m, h)
    je_score, korb_score = _scores(m, fund)
    historie = _layer(m, hist_assets, hist_korb, fund)
    # Annahmen automatisch aus den bisherigen Renditen p.a. (nur automatisch
    # gefuehrte - selbst eingetragene Werte bleiben)
    E.annahmen_aus_historie(m, historie)
    st.session_state["planer_historie"] = historie

    # Eingaben des Bereichs zuerst (sie aendern das Modell), danach rechnen
    R = _rechne(m, historie, korb_score)
    if _auto_gewichtung(m, R):
        R = _rechne(m, historie, korb_score)
    seiten = {
        ("🧩 Portfolio", "Bausteine"): lambda: _b_bausteine(m, R, h),
        ("🧩 Portfolio", "Aufteilung"): lambda: _b_aufteilung(m, R),
        ("⚖️ Gewichtung", None): lambda: _b_gewichtung(m, R),
        ("📈 Ergebnis", "Wachstum"): lambda: _b_growth(m, R),
        ("📈 Ergebnis", "Ziel"): lambda: _b_ziel(m, R),
        ("📈 Ergebnis", "Szenarien"): lambda: _b_szenarien(m, R, historie, h),
        ("📈 Ergebnis", "Entnahme"): lambda: _b_entnahme(m, R),
        ("⚠️ Risiko", "Konzentration"): lambda: _b_risiko(m, R, historie),
        ("⚠️ Risiko", "Sensitivität"): lambda: _b_sensitiv(m, R),
        ("⚠️ Risiko", "Stress & Reserve"): lambda: _b_reserve(m, R),
        ("🔬 Analyse", "Aktienkorb"): lambda: _b_korb(m, R, fund, fund_stand, je_score, korb_score, hist_korb),
        ("🔬 Analyse", "Wikifolios"): lambda: _b_wiki(m, R, hist_assets),
        ("🗂️ Daten", "Annahmen & Quellen"): lambda: _b_annahmen(m, R, historie, hist_assets),
        ("🗂️ Daten", "Gespeicherte Modelle"): lambda: _b_modelle(m, R, historie, h),
    }
    seiten[(haupt, unter)]()

    # KPIs mit dem Stand NACH den Eingaben
    je_score, korb_score = _scores(m, fund)
    R = _rechne(m, historie, korb_score)
    if _auto_gewichtung(m, R):
        R = _rechne(m, historie, korb_score)
    _kpis(kpi_platz, m, R)
    _gewichtswarnung(warn_platz, m)

    status = _auto_speichern(m, h)
    if status:
        art, sz_name, zeit = status
        text = (f"✓ Automatisch gespeichert als „{sz_name}“ · {zeit} Uhr" if art == "ok" else
                "⚠ Automatische Speicherung nicht möglich (GitHub-Speicher nicht erreichbar) – "
                "Änderungen gelten nur bis zum Neuladen.")
        status_platz.markdown(f'<div class="pl-hinweis">{_esc(text)}</div>', unsafe_allow_html=True)
