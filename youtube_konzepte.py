"""Faceless YouTube Phase 3b - Better-Video-Konzepte und Affiliate-Finder. Reine Logik (ohne Streamlit).

Better Video: drei EIGENSTAENDIGE Konzepte aus Thema, gemerkten Kommentar-/Transkript-Analysen und eigener Recherche.
Ausdruecklich keine Uebersetzung oder Umschreibung fremder Videos - eine Aehnlichkeitspruefung gegen die Titel der
Quellvideos markiert Konzepte, die zu nah am Original sind. Mit KI (Gemini) oder ohne KI als Geruest aus den
Fragen, Wuenschen und Kritikpunkten.

Affiliate-Finder: eine gepflegte Liste bekannter Partnerprogramme mit offizieller Quelle. Ein Programm gilt erst als
geprueft, wenn du es auf der offiziellen Seite geprueft und ein Pruefdatum gesetzt hast. KI-Vorschlaege sind immer
"ungeprueft (KI)", bis du sie bestaetigst. Konditionen werden nie erfunden - sie stehen nur da, wenn du sie
eingetragen hast."""
import re

from youtube_analyse import _liste, json_aus_text

FORMATE = {"erklaer": "Erklärvideo", "liste": "Liste / Ranking", "vergleich": "Vergleich", "anleitung": "Anleitung",
           "faq": "Fragen & Antworten", "fallstudie": "Fallstudie"}
AEHNLICH_AB = 0.6

# Kategorien wie die RPM-Nischen (youtube_nische) - so passt der Finder zur Nischen-Analyse
PROGRAMME = [
    {"id": "amazon", "name": "Amazon PartnerNet", "url": "https://partnernet.amazon.de", "art": "Shop",
     "kategorien": ["Technik & KI", "Software & Tutorials", "Gesundheit & Fitness", "Bildung & Wissen", "Gaming",
                    "Sonstiges", "Reisen"], "maerkte": ["DE", "AT"],
     "hinweis": "Breites Sortiment; Provision je Produktkategorie, Cookie kurz."},
    {"id": "awin", "name": "Awin", "url": "https://www.awin.com/de", "art": "Netzwerk",
     "kategorien": ["Technik & KI", "Reisen", "Finanzen & Investieren", "Gesundheit & Fitness", "Sonstiges"],
     "maerkte": ["DE", "AT", "CH", "US", "UK"], "hinweis": "Netzwerk mit vielen Shops; Freigabe je Partnerprogramm."},
    {"id": "financeads", "name": "financeAds", "url": "https://www.financeads.net", "art": "Netzwerk",
     "kategorien": ["Finanzen & Investieren", "Immobilien"], "maerkte": ["DE", "AT", "CH"],
     "hinweis": "Finanzprodukte (Broker, Konten, Kredite) – Werbung für Finanzprodukte rechtlich sorgfältig "
                "kennzeichnen."},
    {"id": "digistore", "name": "Digistore24", "url": "https://www.digistore24.com", "art": "Digitale Produkte",
     "kategorien": ["Business & Marketing", "Bildung & Wissen", "Gesundheit & Fitness", "Software & Tutorials"],
     "maerkte": ["DE", "AT", "CH"], "hinweis": "Kurse und E-Books; Qualität der Produkte vorher selbst prüfen."},
    {"id": "copecart", "name": "CopeCart", "url": "https://www.copecart.com", "art": "Digitale Produkte",
     "kategorien": ["Business & Marketing", "Bildung & Wissen"], "maerkte": ["DE", "AT", "CH"],
     "hinweis": "Digitale Produkte und Kurse; Anbieter einzeln prüfen."},
    {"id": "tradedoubler", "name": "Tradedoubler", "url": "https://www.tradedoubler.com", "art": "Netzwerk",
     "kategorien": ["Reisen", "Technik & KI", "Sonstiges"], "maerkte": ["DE", "UK", "Global"],
     "hinweis": "Netzwerk mit Shops und Reiseanbietern."},
    {"id": "impact", "name": "Impact.com", "url": "https://impact.com", "art": "Netzwerk",
     "kategorien": ["Software & Tutorials", "Technik & KI", "Business & Marketing", "Bildung & Wissen"],
     "maerkte": ["US", "Global"], "hinweis": "Viele Software- und Online-Kurs-Anbieter (meist englischsprachig)."},
    {"id": "partnerstack", "name": "PartnerStack", "url": "https://partnerstack.com", "art": "Netzwerk",
     "kategorien": ["Software & Tutorials", "Technik & KI", "Business & Marketing"], "maerkte": ["US", "Global"],
     "hinweis": "SaaS-Programme, oft wiederkehrende Provisionen."},
    {"id": "ebay", "name": "eBay Partner Network", "url": "https://partnernetwork.ebay.de", "art": "Shop",
     "kategorien": ["Technik & KI", "Gaming", "Sonstiges"], "maerkte": ["DE"],
     "hinweis": "Marktplatz; Provision vom Erlös je Kategorie."},
    {"id": "getyourguide", "name": "GetYourGuide Partner", "url": "https://partner.getyourguide.com", "art": "Reisen",
     "kategorien": ["Reisen"], "maerkte": ["DE", "Global"], "hinweis": "Touren und Aktivitäten."},
]
KENNZEICHNUNG = ("Affiliate-Links in der Beschreibung als Werbung kennzeichnen (z. B. „*Affiliate-Link: Wenn du über "
                 "diesen Link kaufst, erhalte ich eine Provision – für dich ändert sich der Preis nicht.“) und in "
                 "YouTube Studio „Enthält bezahlte Werbung“ setzen, wenn eine Gegenleistung besteht.")


# ---------------------------------------------------------------------------------------------------- Better Video
def _tokens(t):
    return {w for w in re.findall(r"[a-zäöüß0-9]{3,}", str(t or "").lower())}


def aehnlichkeit(a, b):
    """Jaccard-Aehnlichkeit der Woerter (0..1)."""
    x, y = _tokens(a), _tokens(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def material(analysen):
    """Gemerkte Analysen -> Stichpunkte fuer die Konzepte."""
    m = {"quellen": [], "fragen": [], "wuensche": [], "kritik": [], "luecken": [], "kernaussagen": []}
    for a in analysen or []:
        e, ki = a.get("ergebnis") or {}, a.get("ki") or {}
        if a.get("titel"):
            m["quellen"].append(a["titel"])
        m["fragen"] += list(e.get("fragen") or []) + list(ki.get("offene_fragen") or [])
        m["wuensche"] += list(e.get("wuensche") or []) + list(ki.get("wuensche") or [])
        m["kritik"] += list(ki.get("kritikpunkte") or []) + list(ki.get("schwaechen") or [])
        m["luecken"] += list(e.get("luecken") or []) + list(ki.get("luecken") or [])
        m["kernaussagen"] += list(ki.get("kernaussagen") or e.get("kernsaetze") or [])
    return {k: list(dict.fromkeys(str(x)[:300] for x in v if str(x).strip()))[:15] for k, v in m.items()}


def prompt(thema, zielgruppe, laenge_min, m, notizen="", sprache="de"):
    def block(t, liste):
        return f"\n{t}:\n" + "\n".join(f"- {x}" for x in liste[:12]) if liste else ""
    return (
        "Du bist Redakteur für einen Faceless-YouTube-Kanal. Entwickle DREI eigenständige Videokonzepte. Sie dürfen "
        "fremde Videos weder übersetzen noch umschreiben noch deren Titel, Aufbau oder Formulierungen übernehmen. "
        "Nutze die Zuschauerstimmen nur als Hinweis darauf, was fehlt, und eigene, überprüfbare Fakten. "
        f"Sprache: {'Deutsch' if sprache == 'de' else 'Englisch'}. Antworte NUR mit JSON:\n"
        '{"konzepte": [{"titel": "...", "format": "erklaer|liste|vergleich|anleitung|faq|fallstudie", '
        '"hook": "erste 10 Sekunden", "zielgruppe": "...", "versprechen": "was der Zuschauer danach kann", '
        '"aufbau": [{"kapitel": "...", "inhalt": "1-2 Sätze"}], "alleinstellung": "was es besser macht als '
        'vorhandene Videos", "zu_pruefen": ["Fakten/Zahlen, die vor dem Skript belegt werden müssen"], '
        '"thumbnail_idee": "...", "laenge_min": Zahl}]}\n'
        f"Thema: {thema}\nZielgruppe: {zielgruppe or 'allgemein'}\nZiel-Länge: etwa {laenge_min} Minuten"
        + block("Offene Fragen der Zuschauer", m.get("fragen", []))
        + block("Wünsche der Zuschauer", m.get("wuensche", []))
        + block("Kritik an vorhandenen Videos", m.get("kritik", []))
        + block("Lücken vorhandener Videos", m.get("luecken", []))
        + (f"\nEigene Recherche/Notizen:\n{notizen[:3000]}" if notizen else "")
        + block("Titel der analysierten Videos (NICHT übernehmen)", m.get("quellen", [])))


def pruefen(obj, quellen=()):
    """KI-Antwort absichern; Aehnlichkeit zu Quelltiteln markieren. -> {"konzepte": [...]} oder None"""
    if not obj or not isinstance(obj.get("konzepte"), list):
        return None
    aus = []
    for k in obj["konzepte"][:3]:
        if not isinstance(k, dict) or not str(k.get("titel") or "").strip():
            continue
        aufbau = [{"kapitel": str(x.get("kapitel") or "")[:80], "inhalt": str(x.get("inhalt") or "")[:300]}
                  for x in (k.get("aufbau") if isinstance(k.get("aufbau"), list) else []) if isinstance(x, dict)]
        try:
            laenge = max(1, min(60, int(float(k.get("laenge_min") or 8))))
        except (TypeError, ValueError):
            laenge = 8
        titel = str(k["titel"]).strip()[:100]
        naechste = max(((aehnlichkeit(titel, q), q) for q in quellen), default=(0.0, None))
        aus.append({"titel": titel, "format": k.get("format") if k.get("format") in FORMATE else "erklaer",
                    "hook": str(k.get("hook") or "")[:300], "zielgruppe": str(k.get("zielgruppe") or "")[:120],
                    "versprechen": str(k.get("versprechen") or "")[:200], "aufbau": aufbau[:10],
                    "alleinstellung": str(k.get("alleinstellung") or "")[:300],
                    "zu_pruefen": _liste(k.get("zu_pruefen"), 8),
                    "thumbnail_idee": str(k.get("thumbnail_idee") or "")[:200], "laenge_min": laenge,
                    "aehnlich": naechste[1] if naechste[0] >= AEHNLICH_AB else None, "quelle": "KI"})
    return {"konzepte": aus} if aus else None


def geruest(thema, m, laenge_min=8):
    """Drei Konzept-Gerueste ohne KI - aus Fragen, Wuenschen und Kritik. Formulierungen bleiben bewusst allgemein."""
    t = str(thema or "").strip() or "das Thema"
    fragen, wuensche, kritik = m.get("fragen", []), m.get("wuensche", []), m.get("kritik", [])
    luecken = m.get("luecken", [])
    k1 = {"titel": f"{t}: die {min(len(fragen), 7) or 5} wichtigsten Fragen – klar beantwortet", "format": "faq",
          "aufbau": [{"kapitel": "Einstieg", "inhalt": "Warum diese Fragen immer wieder gestellt werden."}]
          + [{"kapitel": f"Frage {i + 1}", "inhalt": f[:200]} for i, f in enumerate(fragen[:7])]
          + [{"kapitel": "Zusammenfassung", "inhalt": "Die Antworten in drei Sätzen."}]}
    k2 = {"titel": f"{t} Schritt für Schritt – ohne Vorwissen", "format": "anleitung",
          "aufbau": [{"kapitel": "Was du am Ende kannst", "inhalt": "Ziel in einem Satz."}]
          + [{"kapitel": f"Schritt {i + 1}", "inhalt": w[:200]} for i, w in enumerate((wuensche + luecken)[:6])]
          + [{"kapitel": "Häufige Fehler", "inhalt": "Was Anfänger falsch machen."}]}
    k3 = {"titel": f"{t}: was die meisten Videos weglassen", "format": "erklaer",
          "aufbau": [{"kapitel": "Das Problem", "inhalt": "Was an vorhandenen Erklärungen fehlt."}]
          + [{"kapitel": f"Punkt {i + 1}", "inhalt": x[:200]} for i, x in enumerate((kritik + luecken)[:6])]
          + [{"kapitel": "Fazit", "inhalt": "Was du jetzt anders machst."}]}
    aus = []
    for k in (k1, k2, k3):
        aus.append(dict(k, hook="", zielgruppe="", versprechen="", alleinstellung="Beantwortet, was Zuschauer "
                        "vermissen (aus den gemerkten Analysen).", zu_pruefen=["Alle Fakten und Zahlen vor dem Skript "
                                                                                 "mit eigenen Quellen belegen."],
                        thumbnail_idee="", laenge_min=laenge_min, aehnlich=None, quelle="Gerüst (ohne KI)"))
    return {"konzepte": aus}


def auftrag(k, thema=""):
    """Konzept -> Auftrag fuer die Video Factory."""
    teile = [f"Erstelle ein eigenständiges deutsches YouTube-Video: „{k['titel']}“."]
    if k.get("versprechen"):
        teile.append(f"Versprechen an die Zuschauer: {k['versprechen']}")
    if k.get("hook"):
        teile.append(f"Einstieg: {k['hook']}")
    if k.get("aufbau"):
        teile.append("Aufbau: " + "; ".join(f"{x['kapitel']} – {x['inhalt']}" for x in k["aufbau"]))
    if k.get("zu_pruefen"):
        teile.append("Nur belegbare Fakten verwenden; prüfen: " + "; ".join(k["zu_pruefen"]))
    teile.append("Keine Inhalte anderer Videos übernehmen. Verständlich, ohne Gesicht.")
    return " ".join(teile)[:2000]


# ---------------------------------------------------------------------------------------------------- Affiliate
def passende(kategorie, markt="", eigene=None, pruefungen=None):
    """Programme fuer eine RPM-Nische/Kategorie, geprueft zuerst. pruefungen: {id: {"datum", "konditionen", ...}}"""
    pruefungen = pruefungen or {}
    liste = [dict(p, eigene=False) for p in PROGRAMME] + [dict(p, eigene=True) for p in (eigene or [])]
    aus = []
    for p in liste:
        if kategorie and kategorie not in (p.get("kategorien") or []) and kategorie != "alle":
            continue
        if markt and markt not in ("Global", "") and p.get("maerkte") and markt not in p["maerkte"] \
                and "Global" not in p["maerkte"]:
            continue
        pr = pruefungen.get(p["id"]) or {}
        aus.append(dict(p, geprueft=pr.get("datum"), konditionen=pr.get("konditionen") or "",
                        status="geprüft" if pr.get("datum") else ("ungeprüft (KI)" if p.get("ki") else "ungeprüft")))
    return sorted(aus, key=lambda p: (not p["geprueft"], p.get("ki", False), p["name"].lower()))


def ki_prompt_affiliate(thema, kategorie):
    return (
        "Nenne bis zu 6 Partnerprogramme (Affiliate) für YouTube-Videos zum Thema unten, die es tatsächlich gibt. "
        "Antworte NUR mit JSON: {\"programme\": [{\"name\": \"...\", \"url\": \"offizielle https-Adresse des "
        "Partnerprogramms\", \"warum\": \"1 Satz\"}]}. Keine erfundenen Programme, keine Provisionen angeben "
        f"(die prüft der Nutzer selbst).\nThema: {thema}\nNische: {kategorie}")


def ki_affiliate_pruefen(obj):
    if not obj or not isinstance(obj.get("programme"), list):
        return None
    aus = []
    for p in obj["programme"][:6]:
        if not isinstance(p, dict):
            continue
        url = str(p.get("url") or "").strip()
        name = str(p.get("name") or "").strip()[:60]
        if name and re.match(r"^https://[a-z0-9.-]+\.[a-z]{2,}(/\S*)?$", url, re.I):
            aus.append({"name": name, "url": url[:200], "warum": str(p.get("warum") or "")[:200]})
    return {"programme": aus} if aus else None


def eigenes_programm(name, url, kategorien, ki=False, hinweis=""):
    name, url = str(name or "").strip()[:60], str(url or "").strip()[:200]
    if not name:
        raise ValueError("Bitte einen Namen angeben.")
    if not re.match(r"^https://[a-z0-9.-]+\.[a-z]{2,}(/\S*)?$", url, re.I):
        raise ValueError("Bitte die offizielle Adresse mit https:// angeben.")
    pid = "e-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30]
    return {"id": pid, "name": name, "url": url, "art": "eigene", "kategorien": list(kategorien or []),
            "maerkte": [], "hinweis": str(hinweis or "")[:200], "ki": bool(ki)}
