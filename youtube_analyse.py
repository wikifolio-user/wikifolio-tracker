"""Faceless YouTube Phase 3a - Kommentar- und Transkript-Analyse. Reine Logik (ohne Streamlit).

Kommentare: oeffentliche Kommentare ueber die offizielle YouTube Data API (commentThreads, 1 Einheit je 100).
Gespeichert und angezeigt werden nur Text, Likes, Datum und Antwortzahl - nie Namen oder Kanaele der Verfasser.
Auswertung ohne KI: Spam-Filter, Gruppen (Lob, Kritik, Fragen, Wuensche) ueber Stichworte, haeufige Begriffe.
Mit KI (Gemini/Groq ueber ki_anbieter): Zusammenfassung je Gruppe, offene Fragen, Wuensche, Kritikpunkte.

Transkript: eingefuegter Text oder eine SRT/VTT-Datei (fremde Untertitel gibt die API nicht heraus). Ohne KI:
Umfang, Sprechtempo, Kapitelvorschlag nach Zeit, Kernsaetze nach Begriffsgewicht, moegliche Luecken gegenueber den
Fragen aus den Kommentaren. Mit KI: Kernaussagen, Luecken, Kapitel."""
import collections
import json
import re

MAX_KOMMENTARE = 1000
KI_KOMMENTARE = 150
GRUPPEN = {"wunsch": "Wünsche & Themenvorschläge", "frage": "Offene Fragen", "kritik": "Kritik",
           "lob": "Lob", "sonstiges": "Sonstiges"}
MUSTER = {
    "wunsch": r"(bitte (mach|mehr|ein video)|mach (mal|bitte)|video (über|zu|about)|nächstes video|"
              r"please (make|do)|next video|could you (make|do)|würde (gern|mich freuen)|wünsche mir|"
              r"would love (to see|a video)|part 2|teil 2|fortsetzung)",
    "frage": r"(\?|^(wie|was|warum|wieso|weshalb|wann|wo|welche[rsmn]?|kann man|gibt es|how|what|why|when|where|"
             r"which|can you|is it|does|do you)\b)",
    "kritik": r"(schlecht|falsch|enttäusch|clickbait|langweilig|nervig|zu lang|zu laut|zu leise|ton ist|"
              r"musik ist zu|fehler|stimmt nicht|unsinn|quatsch|boring|wrong|bad|misleading|too long|"
              r"annoying|hate|worst|dislike|terrible|disappoint|ki[- ]stimme|ai voice|robot)",
    "lob": r"(danke|super|toll|klasse|genial|hilfreich|sehr gut|gut erklärt|endlich|thank|great|love|"
           r"amazing|awesome|best|helpful|well explained|perfect|excellent|nice|👍|❤|🙏|🔥)",
}
SPAM = r"(https?://|www\.|t\.me/|whatsapp|telegram|check (out )?my (channel|video)|schau (mal )?auf meinem kanal|" \
       r"abonnier(t)? (meinen|mich)|sub(scribe)? (to|for) (me|sub)|\+\d{6,}|crypto signal|investment manager|" \
       r"bitcoin mining|forex)"
STOPP = set("""der die das und oder aber nicht ist sind war waren ein eine einer eines einem einen ich du er sie es wir
ihr mich dich sich mir dir uns euch auch noch nur schon sehr mehr wie was wer wo wann warum mit von zu zum zur im in
am an auf aus bei für fur über um so dass da dann denn doch ja nein mal man kann können würde wäre hat habe haben hast
wird werden wurde bitte danke video videos kanal mein meine dein deine sein seine ihr ihre the a an and or but not is
are was were be been to of in on at for with this that it its i you he she we they me my your our their so very
just also really can could would will do does did have has had if as from by about what how why when which who all
any some no yes like dont im ive its thats there here than then them these those one get got
""".split())
TRANSKRIPT_KAPITEL_S = 150


# ---------------------------------------------------------------------------------------------------- Video-ID
def video_id(eingabe):
    """Video-ID aus Link oder ID (11 Zeichen). -> str oder None"""
    s = str(eingabe or "").strip()
    for m in (r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})", r"^([A-Za-z0-9_-]{11})$"):
        t = re.search(m, s)
        if t:
            return t.group(1)
    return None


# ---------------------------------------------------------------------------------------------------- Kommentare
def kommentar_parsen(item):
    top = ((item.get("snippet") or {}).get("topLevelComment") or {}).get("snippet") or {}
    text = top.get("textOriginal") or top.get("textDisplay") or ""
    return {"text": re.sub(r"\s+", " ", str(text)).strip()[:1000], "likes": int(top.get("likeCount") or 0),
            "datum": str(top.get("publishedAt") or "")[:10],
            "antworten": int((item.get("snippet") or {}).get("totalReplyCount") or 0)}


def kommentare_laden(abruf, vid, maximal=300, reihenfolge="relevance"):
    """Oeffentliche Top-Level-Kommentare. Kosten: 1 Einheit je Seite (100 Kommentare)."""
    aus, token = [], None
    maximal = max(1, min(int(maximal), MAX_KOMMENTARE))
    while len(aus) < maximal:
        p = {"part": "snippet", "videoId": vid, "maxResults": 100, "textFormat": "plainText",
             "order": reihenfolge if reihenfolge in ("relevance", "time") else "relevance"}
        if token:
            p["pageToken"] = token
        r = abruf("commentThreads", p)
        aus += [kommentar_parsen(i) for i in r.get("items") or []]
        token = r.get("nextPageToken")
        if not token:
            break
    return [k for k in aus if k["text"]][:maximal]


def ist_spam(text):
    t = text.lower()
    if re.search(SPAM, t):
        return True
    if re.search(r"(.)\1{9,}", t):                          # aaaaaaaaaa
        return True
    return False


def gruppen_von(text):
    t = text.lower()
    return [g for g, m in MUSTER.items() if re.search(m, t, re.M)] or ["sonstiges"]


def hauptgruppe(text):
    g = gruppen_von(text)
    return next(x for x in GRUPPEN if x in g)


def _woerter(text):
    return [w for w in re.findall(r"[a-zäöüß0-9][a-zäöüß0-9\-]{2,}", text.lower()) if w not in STOPP
            and not w.isdigit()]


def begriffe(texte, n=20, gewichte=None):
    """Haeufigste Woerter und Wortpaare (ohne Fuellwoerter). -> [(begriff, anzahl)]"""
    z = collections.Counter()
    for i, t in enumerate(texte):
        w = _woerter(t)
        g = (gewichte or [1] * len(texte))[i]
        for x in set(w):
            z[x] += g
        for a, b in set(zip(w, w[1:])):
            z[f"{a} {b}"] += g * 1.5
    paare = {k for k in z if " " in k and z[k] >= 3}
    for p in paare:                                       # Einzelwoerter, die fast nur im Paar vorkommen, weg
        for w in p.split():
            if z.get(w, 0) <= z[p] / 1.5 + 1:
                z.pop(w, None)
    return [(k, round(v)) for k, v in z.most_common(n * 2) if v >= 2][:n]


def kommentare_auswerten(kommentare):
    """-> {"anzahl", "spam", "gruppen": {g: {"anzahl", "anteil", "beispiele"}}, "begriffe", "fragen"}"""
    echt = [k for k in kommentare if not ist_spam(k["text"])]
    je = {g: [] for g in GRUPPEN}
    for k in echt:
        je[hauptgruppe(k["text"])].append(k)
    gruppen = {}
    for g, liste in je.items():
        liste = sorted(liste, key=lambda k: (-k["likes"], -k["antworten"]))
        gruppen[g] = {"name": GRUPPEN[g], "anzahl": len(liste),
                      "anteil": len(liste) / len(echt) * 100 if echt else 0.0,
                      "beispiele": [dict(k, text=k["text"][:300]) for k in liste[:5]]}
    return {"anzahl": len(kommentare), "echt": len(echt), "spam": len(kommentare) - len(echt), "gruppen": gruppen,
            "begriffe": begriffe([k["text"] for k in echt], 20, [1 + min(k["likes"], 50) / 10 for k in echt]),
            "fragen": [k["text"][:300] for k in sorted(je["frage"], key=lambda k: -k["likes"])[:15]],
            "wuensche": [k["text"][:300] for k in sorted(je["wunsch"], key=lambda k: -k["likes"])[:15]]}


def ki_prompt_kommentare(titel, kommentare):
    auswahl = sorted([k for k in kommentare if not ist_spam(k["text"])], key=lambda k: -k["likes"])[:KI_KOMMENTARE]
    zeilen = "\n".join(f"- ({k['likes']} Likes) {k['text'][:400]}" for k in auswahl)
    return (
        "Du analysierst öffentliche YouTube-Kommentare für einen Creator, der ein EIGENES, besseres Video zum Thema "
        "plant. Antworte auf Deutsch und NUR mit einem JSON-Objekt in diesem Schema:\n"
        '{"zusammenfassung": "2-3 Sätze", "gruppen": [{"name": "Lob|Kritik|Offene Fragen|Wünsche|Sonstiges", '
        '"anteil_prozent": Zahl, "kern": "1 Satz", "beispiele": ["kurzes Zitat", "..."]}], '
        '"offene_fragen": ["..."], "wuensche": ["..."], "kritikpunkte": ["..."], '
        '"chancen_fuer_eigenes_video": ["..."]}\n'
        "Regeln: Nenne keine Namen von Personen oder Kanälen. Zitate höchstens 15 Wörter. Erfinde nichts, was nicht in "
        f"den Kommentaren steht. Anteile sind Schätzungen.\nVideotitel: {titel or 'unbekannt'}\n"
        f"Kommentare ({len(auswahl)} von {len(kommentare)}, nach Likes):\n{zeilen}")


def json_aus_text(text):
    if not text:
        return None
    m = re.search(r"\{.*\}", str(text), re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _liste(x, n=12):
    return [str(v)[:300] for v in (x if isinstance(x, list) else []) if str(v).strip()][:n]


def ki_kommentare_pruefen(obj):
    """Schema absichern (nur erwartete Felder, gekuerzt). -> dict oder None"""
    if not obj:
        return None
    gruppen = []
    for g in obj.get("gruppen") if isinstance(obj.get("gruppen"), list) else []:
        if isinstance(g, dict) and g.get("name"):
            try:
                anteil = max(0.0, min(100.0, float(g.get("anteil_prozent") or 0)))
            except (TypeError, ValueError):
                anteil = None
            gruppen.append({"name": str(g["name"])[:40], "anteil": anteil, "kern": str(g.get("kern") or "")[:300],
                            "beispiele": _liste(g.get("beispiele"), 3)})
    aus = {"zusammenfassung": str(obj.get("zusammenfassung") or "")[:800], "gruppen": gruppen,
           "offene_fragen": _liste(obj.get("offene_fragen")), "wuensche": _liste(obj.get("wuensche")),
           "kritikpunkte": _liste(obj.get("kritikpunkte")),
           "chancen": _liste(obj.get("chancen_fuer_eigenes_video"))}
    return aus if (aus["zusammenfassung"] or gruppen) else None


def mit_ki(anbieter, prompt, pruefen):
    """KI-Antwort holen und pruefen; bei ungueltigem JSON genau ein zweiter Versuch. -> (dict, fehler)"""
    if anbieter is None:
        return None, "Kein KI-Zugang (GEMINI_API_KEY) eingerichtet."
    for _ in range(2):
        obj = pruefen(json_aus_text(anbieter.antwort(prompt)))
        if obj:
            return obj, None
        prompt += "\n\nDeine letzte Antwort war kein gültiges JSON im verlangten Schema. Nur das JSON-Objekt!"
    return None, "Die KI hat zweimal keine auswertbare Antwort geliefert."


# ---------------------------------------------------------------------------------------------------- Transkript
def _zeit(t):
    m = re.match(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})", t.strip())
    if not m:
        return None
    h, mi, s, ms = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s + ms / 1000


def transkript_parsen(text):
    """SRT/VTT oder Fliesstext -> {"art": "srt"/"vtt"/"text", "segmente": [{"start", "ende", "text"}]}.
    Bei Fliesstext ohne Zeiten: Absaetze als Segmente (start/ende None)."""
    s = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not s:
        return {"art": "text", "segmente": []}
    zeit = re.compile(r"^\s*((?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*((?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})")
    if zeit.search(s.split("\n\n")[0] if "-->" in s else "") or "-->" in s:
        art = "vtt" if s.upper().startswith("WEBVTT") else "srt"
        segmente, akt = [], None
        for zeile in s.split("\n"):
            m = zeit.match(zeile)
            if m:
                akt = {"start": _zeit(m.group(1)), "ende": _zeit(m.group(2)), "text": ""}
                segmente.append(akt)
            elif akt is not None and zeile.strip() and not re.fullmatch(r"\d+", zeile.strip()):
                t = re.sub(r"<[^>]+>", "", zeile).strip()
                if t and not akt["text"].endswith(t):         # VTT wiederholt Zeilen oft
                    akt["text"] = (akt["text"] + " " + t).strip()
            elif not zeile.strip():
                akt = None
        return {"art": art, "segmente": [x for x in segmente if x["text"]]}
    absaetze = [re.sub(r"\s+", " ", a).strip() for a in re.split(r"\n\s*\n", s)]
    if len(absaetze) == 1:                                   # langer Block: in Saetze-Gruppen teilen
        saetze = re.split(r"(?<=[.!?])\s+", absaetze[0])
        absaetze = [" ".join(saetze[i:i + 5]) for i in range(0, len(saetze), 5)]
    return {"art": "text", "segmente": [{"start": None, "ende": None, "text": a} for a in absaetze if a]}


def _saetze(text):
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+", text) if len(x.strip()) > 25]


def zeit_text(s):
    if s is None:
        return "–"
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def transkript_auswerten(t, fragen=()):
    """t: transkript_parsen(). fragen: offene Fragen aus den Kommentaren (fuer moegliche Luecken)."""
    seg = t["segmente"]
    voll = " ".join(x["text"] for x in seg)
    woerter = len(re.findall(r"\w+", voll))
    dauer = max((x["ende"] or 0) for x in seg) if seg and seg[0]["start"] is not None else None
    wpm = woerter / (dauer / 60) if dauer else None
    top = begriffe([voll], 25)
    gewicht = {k: v for k, v in top}
    saetze = _saetze(voll)
    bewertet = sorted(((sum(gewicht.get(w, 0) for w in _woerter(s)) / (len(_woerter(s)) or 1) ** 0.5, i, s)
                       for i, s in enumerate(saetze)), reverse=True)
    kern = [s for _, _, s in sorted(bewertet[:7], key=lambda x: x[1])]
    kapitel = []
    if dauer:
        grenze, block = 0.0, []
        for x in seg:
            if x["start"] >= grenze + TRANSKRIPT_KAPITEL_S and block:
                kapitel.append(_kapitel(block))
                block, grenze = [], x["start"]
            block.append(x)
        if block:
            kapitel.append(_kapitel(block))
    luecken = []
    for f in fragen:
        w = [x for x in _woerter(f) if len(x) > 4]
        if w and not any(x in voll.lower() for x in w):
            luecken.append(f)
    return {"art": t["art"], "segmente": len(seg), "woerter": woerter, "dauer_s": dauer, "wpm": wpm,
            "begriffe": top[:15], "kernsaetze": kern, "kapitel": kapitel, "luecken": luecken[:10]}


def _kapitel(block):
    text = " ".join(x["text"] for x in block)
    b = begriffe([text], 3)
    titel = ", ".join(k for k, _ in b[:2]) or (text[:40] + "…")
    return {"start": block[0]["start"], "titel": titel[:60], "text": text[:200]}


def ki_prompt_transkript(titel, t, fragen=()):
    seg = t["segmente"]
    zeilen = "\n".join((f"[{zeit_text(x['start'])}] " if x["start"] is not None else "") + x["text"] for x in seg)
    if len(zeilen) > 24000:
        zeilen = zeilen[:24000] + "\n[… gekürzt]"
    fr = "\n".join(f"- {f}" for f in list(fragen)[:15])
    return (
        "Du analysierst das Transkript eines YouTube-Videos für einen Creator, der ein EIGENES, besseres Video zum "
        "Thema plant (keine Übersetzung oder Umschreibung). Antworte auf Deutsch und NUR mit einem JSON-Objekt:\n"
        '{"zusammenfassung": "3-4 Sätze", "kernaussagen": ["..."], "luecken": ["Was fehlt oder bleibt unklar"], '
        '"schwaechen": ["Aufbau, Tempo, Belege"], "kapitel": [{"zeit": "m:ss oder leer", "titel": "..."}]}\n'
        "Regeln: Nur was im Transkript steht oder offensichtlich fehlt; keine wörtlichen Passagen über 15 Wörter."
        + (f"\nOffene Fragen der Zuschauer (Kommentare):\n{fr}" if fr else "")
        + f"\nVideotitel: {titel or 'unbekannt'}\nTranskript:\n{zeilen}")


def ki_transkript_pruefen(obj):
    if not obj:
        return None
    kap = []
    for k in obj.get("kapitel") if isinstance(obj.get("kapitel"), list) else []:
        if isinstance(k, dict) and k.get("titel"):
            kap.append({"zeit": str(k.get("zeit") or "")[:10], "titel": str(k["titel"])[:80]})
    aus = {"zusammenfassung": str(obj.get("zusammenfassung") or "")[:1200],
           "kernaussagen": _liste(obj.get("kernaussagen")), "luecken": _liste(obj.get("luecken")),
           "schwaechen": _liste(obj.get("schwaechen")), "kapitel": kap[:20]}
    return aus if (aus["zusammenfassung"] or aus["kernaussagen"]) else None
