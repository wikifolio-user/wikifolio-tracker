"""Faceless YouTube Phase 2b - Nischen-Score und Einnahmepotenzial. Reine Rechenlogik (ohne Streamlit).

Grundlage ist eine Stichwortsuche (youtube_api.suche, sortiert nach Aufrufen): die erfolgreichsten Videos einer
Nische mit der Groesse ihrer Kanaele. Daraus entstehen vier Teilwerte (je 0-100, jeweils mit Begruendung):
  Nachfrage  - Median der Aufrufe (logarithmisch: 1.000 = 0, 1 Mio. = 100)
  Konkurrenz - Anteil der Treffer von grossen Kanaelen (ab 100.000 Abos); weniger = besser
  Chance     - Anteil kleiner Kanaele (unter 10.000 Abos) mit mehr Aufrufen als Abonnenten; 25 % = 100
  Frische    - Anteil junger Videos unter den Top-Treffern; 50 % = 100
Gesamt = gewichtetes Mittel (35/25/25/15) der vorhandenen Teile. Fehlt ein Teil, ist der Score "vorlaeufig".
Alle Einnahmen sind Schaetzungen (RPM-Spannen, editierbar) - nie gemessene Werte."""
import math
import re
import statistics

GEWICHTE = {"nachfrage": 35, "konkurrenz": 25, "chance": 25, "frische": 15}
TEIL_TEXT = {"nachfrage": "Nachfrage", "konkurrenz": "Konkurrenz", "chance": "Chance für kleine Kanäle",
             "frische": "Frische"}
MIN_VIDEOS = 10
GROSS_ABOS = 100000
KLEIN_ABOS = 10000
CHANCE_VOLL = 0.25
FRISCH_VOLL = 0.5

# RPM = Auszahlung an den Kanal je 1.000 Aufrufe (nach YouTube-Anteil), grobe Spannen fuer DACH/US - Schaetzung.
STANDARD_RPM = {
    "Finanzen & Investieren": (6.0, 18.0), "Business & Marketing": (5.0, 14.0), "Immobilien": (5.0, 15.0),
    "Technik & KI": (3.0, 10.0), "Software & Tutorials": (3.0, 9.0), "Gesundheit & Fitness": (3.0, 8.0),
    "Bildung & Wissen": (2.0, 7.0), "Reisen": (2.0, 6.0), "Dokumentation & Geschichte": (2.0, 6.0),
    "Unterhaltung & True Crime": (1.5, 5.0), "Gaming": (1.0, 3.5), "Musik & Entspannung": (0.5, 2.0),
    "Sonstiges": (1.0, 5.0)}
SHORTS_RPM = (0.03, 0.12)
SZENARIEN = {"konservativ": 0.05, "realistisch": 0.2, "optimistisch": 0.6}   # Anteil am Nischen-Median je Video
STICHWORTE = [
    (r"finanz|aktie|börse|boerse|etf|invest|geld|krypto|bitcoin|dividend|sparen|rente|steuer|stock|money|crypto",
     "Finanzen & Investieren"),
    (r"immobilie|wohnung|miete|real estate", "Immobilien"),
    (r"business|marketing|selbstständig|selbststaendig|gründ|gruend|startup|verkauf|amazon fba|dropshipping|"
     r"side hustle|nebenverdienst", "Business & Marketing"),
    (r"\bki\b|\bai\b|künstliche|kuenstliche|chatgpt|technik|tech|smartphone|gadget|robot", "Technik & KI"),
    (r"excel|software|tutorial|programmier|python|coding|app\b|anleitung", "Software & Tutorials"),
    (r"gesund|fitness|abnehm|ernährung|ernaehrung|workout|schlaf|diet|health", "Gesundheit & Fitness"),
    (r"reise|urlaub|travel", "Reisen"),
    (r"geschichte|history|doku|krieg|antike|mittelalter", "Dokumentation & Geschichte"),
    (r"true crime|mystery|kriminal|horror|creepy", "Unterhaltung & True Crime"),
    (r"gaming|minecraft|fortnite|zocken|game", "Gaming"),
    (r"musik|music|lofi|entspann|meditation|sleep|ambient", "Musik & Entspannung"),
    (r"lernen|wissen|erklärt|erklaert|psychologie|wissenschaft|science|fakten", "Bildung & Wissen")]
KATEGORIE_NISCHE = {"27": "Bildung & Wissen", "28": "Technik & KI", "20": "Gaming", "10": "Musik & Entspannung",
                    "24": "Unterhaltung & True Crime", "23": "Unterhaltung & True Crime", "19": "Reisen",
                    "26": "Sonstiges", "22": "Sonstiges", "25": "Dokumentation & Geschichte"}


def _klemmen(x):
    return max(0.0, min(100.0, x))


def rpm_tabelle(eigene=None):
    """Standard-RPM, ueberschrieben von eigenen Werten {nische: [von, bis]} (nur gueltige Paare)."""
    t = dict(STANDARD_RPM)
    for n, w in (eigene or {}).items():
        try:
            von, bis = float(w[0]), float(w[1])
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        if str(n).strip() and 0 <= von <= bis <= 200:
            t[str(n).strip()] = (von, bis)
    return t


def nische_raten(begriff, videos=()):
    """Passende RPM-Nische: erst Stichworte im Suchbegriff, sonst die haeufigste YouTube-Kategorie."""
    b = str(begriff or "").lower()
    for muster, nische in STICHWORTE:
        if re.search(muster, b):
            return nische
    kats = [v.get("kategorie") for v in videos if v.get("kategorie")]
    if kats:
        return KATEGORIE_NISCHE.get(max(set(kats), key=kats.count), "Sonstiges")
    return "Sonstiges"


def bewerten(videos, zeitraum_tage=365):
    """videos: angereicherte Treffer einer Suche (youtube_api.anreichern). -> Bewertung mit Teilwerten und Texten."""
    vs = [v for v in videos if v.get("views") is not None]
    teile, texte = {}, {}
    if len(vs) < MIN_VIDEOS:
        return {"gesamt": None, "teile": {}, "texte": {}, "vorlaeufig": True, "anzahl": len(vs), "chancen": [],
                "einstufung": "zu wenig Daten", "median_views": None,
                "hinweis": f"Nur {len(vs)} Videos gefunden – für eine Bewertung braucht es mindestens {MIN_VIDEOS}. "
                           "Zeitraum vergrößern oder einen allgemeineren Begriff wählen."}
    med = statistics.median(v["views"] for v in vs)
    teile["nachfrage"] = round(_klemmen((math.log10(max(med, 1)) - 3) / 3 * 100))
    texte["nachfrage"] = f"Median {med:,.0f} Aufrufe in den Top {len(vs)} Videos.".replace(",", ".")
    bekannt = [v for v in vs if v.get("abonnenten") is not None]
    if len(bekannt) >= MIN_VIDEOS:
        gross = sum(1 for v in bekannt if v["abonnenten"] >= GROSS_ABOS) / len(bekannt)
        teile["konkurrenz"] = round(_klemmen(100 * (1 - gross)))
        texte["konkurrenz"] = (f"{gross:.0%} der Treffer stammen von Kanälen ab {GROSS_ABOS:,} Abonnenten "
                               f"(Median der Kanäle: {statistics.median(v['abonnenten'] for v in bekannt):,.0f})."
                               ).replace(",", ".")
        klein = [v for v in bekannt if v["abonnenten"] < KLEIN_ABOS and (v.get("faktor_kanal") or 0) >= 1]
        anteil = len(klein) / len(bekannt)
        teile["chance"] = round(_klemmen(anteil / CHANCE_VOLL * 100))
        texte["chance"] = (f"{len(klein)} von {len(bekannt)} Treffern kommen von Kanälen unter {KLEIN_ABOS:,} "
                           "Abonnenten und haben trotzdem mehr Aufrufe als Abonnenten.").replace(",", ".")
    else:
        texte["konkurrenz"] = texte["chance"] = (f"Nur {len(bekannt)} Kanäle mit sichtbarer Abonnentenzahl – "
                                                 "zu wenig für eine Aussage.")
    grenze = min(90, zeitraum_tage / 3) if zeitraum_tage else 90
    mit_alter = [v for v in vs if v.get("alter_tage") is not None]
    if mit_alter:
        jung = sum(1 for v in mit_alter if v["alter_tage"] <= grenze) / len(mit_alter)
        teile["frische"] = round(_klemmen(jung / FRISCH_VOLL * 100))
        texte["frische"] = f"{jung:.0%} der Top-Videos sind höchstens {grenze:.0f} Tage alt."
    summe = sum(GEWICHTE[k] for k in teile)
    gesamt = round(sum(teile[k] * GEWICHTE[k] for k in teile) / summe) if summe else None
    chancen = sorted([v for v in bekannt if v["abonnenten"] < KLEIN_ABOS and (v.get("faktor_kanal") or 0) >= 1],
                     key=lambda v: -(v.get("faktor_kanal") or 0))
    return {"gesamt": gesamt, "teile": teile, "texte": texte, "vorlaeufig": len(teile) < len(GEWICHTE),
            "anzahl": len(vs), "median_views": med, "chancen": chancen, "hinweis": "",
            "einstufung": "–" if gesamt is None else "vielversprechend" if gesamt >= 70 else
            "prüfenswert" if gesamt >= 50 else "schwierig"}


def einnahmen(views_monat, rpm):
    """Spanne der Werbeeinnahmen pro Monat (Schaetzung)."""
    v = max(float(views_monat or 0), 0.0)
    return v / 1000 * rpm[0], v / 1000 * rpm[1]


def potenzial(median_views, videos_monat, rpm, shorts=False):
    """Szenarien fuer einen NEUEN Kanal in der Nische: Aufrufe je Video als Anteil am Nischen-Median.
    -> {szenario: {"views_monat", "von", "bis"}} - alles Schaetzung."""
    rpm = SHORTS_RPM if shorts else rpm
    aus = {}
    for name, anteil in SZENARIEN.items():
        views = max(float(median_views or 0), 0.0) * anteil * max(int(videos_monat or 0), 0)
        von, bis = einnahmen(views, rpm)
        aus[name] = {"views_monat": round(views), "von": von, "bis": bis}
    return aus


def kanal_views_monat(videos):
    """Grobe Schaetzung der monatlichen Aufrufe eines Kanals: Aufrufe der Videos der letzten 90 Tage / 3.
    Der Back-Katalog fehlt - der echte Wert liegt meist hoeher."""
    neu = [v for v in videos if v.get("alter_tage") is not None and v["alter_tage"] <= 90 and v.get("views")]
    return round(sum(v["views"] for v in neu) / 3) if neu else 0
