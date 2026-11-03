"""Merkmale eines ETFs aus seinem Namen (Anbieter, Region, Thema, Ertragsverwendung, Hebel/Short) - reine Logik.

Die Kursdaten (ls-tc) enthalten keine Stammdaten wie TER, Fondsvolumen oder Index. Die ETF-Namen folgen aber einem
festen Schema ("iShares Core MSCI World UCITS ETF USD (Acc)", "Xtrackers MSCI Emerging Markets 1C" ...), daraus
lassen sich Anbieter, Region, Thema und Ertragsverwendung zuverlaessig ablesen. Was nicht erkennbar ist, bleibt
"Sonstige" bzw. "unbekannt" - nichts wird geraten.
"""
import re

import klassen_score as KS

# (Anzeige, Muster) - erster Treffer zaehlt; laengere Namen vor kuerzeren (iShares Core vor iShares)
ANBIETER = (
    ("iShares", r"\bishares\b|\bblackrock\b"),
    ("Xtrackers", r"\bxtrackers\b|\bdb x-trackers\b|\bdws\b"),
    ("Vanguard", r"\bvanguard\b"),
    ("Amundi", r"\bamundi\b|\blyxor\b"),
    ("SPDR", r"\bspdr\b|\bstate street\b"),
    ("Invesco", r"\binvesco\b"),
    ("WisdomTree", r"\bwisdomtree\b"),
    ("VanEck", r"\bvaneck\b|\bvan eck\b"),
    ("UBS", r"\bubs\b"),
    ("HSBC", r"\bhsbc\b"),
    ("Franklin", r"\bfranklin\b"),
    ("JPMorgan", r"\bjpmorgan\b|\bjp morgan\b|\bj\.p\. morgan\b"),
    ("Global X", r"\bglobal x\b"),
    ("L&G", r"\bl&g\b|\blegal & general\b"),
    ("Fidelity", r"\bfidelity\b"),
    ("First Trust", r"\bfirst trust\b"),
    ("Deka", r"\bdeka\b"),
    ("BNP Paribas", r"\bbnp\b"),
    ("Ossiam", r"\bossiam\b"),
    ("HANetf", r"\bhanetf\b"),
    ("Leverage Shares", r"\bleverage shares\b"),
    ("GraniteShares", r"\bgraniteshares\b"),
    ("21Shares", r"\b21shares\b"),
    ("Rize", r"\brize\b"),
    ("KraneShares", r"\bkraneshares\b"),
    ("Market Access", r"\bmarket access\b"),
    ("Dimensional", r"\bdimensional\b"),
    ("Avantis", r"\bavantis\b"),
    ("Goldman Sachs", r"\bgoldman\b"),
    ("AXA", r"\baxa\b"),
    ("Allianz", r"\ballianz\b"),
    ("Nomura", r"\bnomura\b"),
    ("Tabula", r"\btabula\b"),
)

# Region: erster Treffer zaehlt (Laender vor Kontinenten vor "Welt")
REGIONEN = (
    ("Deutschland", r"\bdax\b|\bmdax\b|\bsdax\b|\btecdax\b|\bgermany\b|\bdeutschland\b"),
    ("USA", r"\bs&p\s?500\b|\bs&p\b|s\+p|\bsp\s?500\b|\bnasdaq\b|\bnas\s?100\b|\busa\b|\bu\.s\.\b|\bus\b|\bamerica\b|\brussell\b|\bdow jones\b|"
            r"\bmsci usa\b|\btreasury\b|\bus treasur"),
    ("Schwellenländer", r"\bemerging\b|\bem\b|\bmsci em\b|\bchina\b|\bindia\b|\bindien\b|\bbrazil\b|\bkorea\b|"
                        r"\btaiwan\b|\blatin america\b|\bafrica\b|\bfrontier\b|\bbric\b"),
    ("Japan", r"\bjapan\b|\bjap\b|\bjp\b|\bnikkei\b|\btopix\b"),
    ("Großbritannien", r"\buk\b|\bftse 100\b|\bftse 250\b|\bunited kingdom\b|\bgilt"),
    ("Schweiz", r"\bswitzerland\b|\bswiss\b|\bsmi\b"),
    ("Europa", r"\beurope\b|\beuropa\b|\beuro\b|\beurozone\b|\bemu\b|\bstoxx\b|\bnordic\b|\bfrance\b|\bcac\b|"
               r"\bitaly\b|\bspain\b|\bnetherlands\b"),
    ("Asien/Pazifik", r"\basia\b|\bpacific\b|\basien\b|\baustralia\b|\bhong kong\b|\bsingapore\b"),
    ("Welt", r"\bworld\b|\bwelt\b|\bacwi\b|\bglobal\b|\ball[- ]country\b|\bftse all-world\b|\bmsci ac\b"),
)

# Themen: alle Treffer zaehlen (ein ETF kann z. B. "Dividende" und "Europa" sein)
THEMEN = (
    ("Anleihen", r"\bbond|\btreasur|\bgovt\b|\bgovernment\b|\bcorporate\b|\baggregate\b|\bhigh yield\b|\bgilt|"
                 r"\banleihe|\bbund\b|\bt-bill|\bmoney market\b|\bgeldmarkt|\bovernight\b|\b€str\b|\bestr\b|"
                 r"\binflation linked\b|\btips\b|\b[0-9]+-[0-9]+\s?y(ea)?r?\b"),
    ("Dividende", r"\bdividend|\bdividende|\bhigh yield equity\b|\bincome\b|\baristocrat"),
    ("Technologie", r"\btech|\bnasdaq\b|\bsemiconductor|\bsoftware\b|\bcyber|\bcloud\b|\bdigital|\binternet\b|"
                    r"\bartificial intelligence\b|\bai\b|\brobotic|\bautomation\b|\bmetaverse\b|\bfintech\b"),
    ("Gesundheit", r"\bhealth|\bbiotech|\bpharma|\bmedical\b|\bgenomic"),
    ("Nachhaltig/ESG", r"\besg\b|\bsri\b|\bclimate\b|\bparis\b|\bpab\b|\bsustainab|\bscreened\b|\bctb\b|"
                       r"\bclean\b|\brenewable\b|\bwater\b|\bgreen\b"),
    ("Energie & Rohstoffe", r"\benergy\b|\boil\b|\bcommodit|\bmining\b|\bmetal|\buranium\b|\blithium\b|"
                            r"\bgold\b|\bsilver\b|\bsilber\b|\bplatin|\bagricult"),
    ("Edelmetalle", r"\bgold\b|\bsilver\b|\bsilber\b|\bplatin|\bpalladium\b|\bprecious\b"),
    ("Finanzen", r"\bbank|\bfinancial|\binsurance\b"),
    ("Immobilien", r"\breal estate\b|\breit|\bproperty\b|\bimmobilie"),
    ("Infrastruktur", r"\binfrastructure\b|\butilities\b"),
    ("Small/Mid Cap", r"\bsmall\b|\bmid\b|\bmdax\b|\bsdax\b|\brussell 2000\b|\bsmallcap|\bmidcap"),
    ("Faktor", r"\bvalue\b|\bmomentum\b|\bquality\b|\bmin(imum)? vol|\blow vol|\bequal weight\b|\bmulti[- ]factor\b|"
               r"\bfactor\b"),
    ("Krypto", r"\bbitcoin\b|\bethereum\b|\bcrypto|\bblockchain\b|\bsolana\b"),
    ("Verteidigung", r"\bdefen[cs]e\b|\baerospace\b|\bsecurity\b"),
    ("Konsum", r"\bconsumer\b|\bluxury\b|\bretail\b"),
    ("Industrie", r"\bindustrial"),
    ("Multi-Asset", r"\bmulti asset\b|\bmulti-asset\b|\bportfolio\b|\bstrategy\b|\b[0-9]{2}/[0-9]{2}\b"),
    ("Covered Call", r"\bcovered call\b|\boption income\b|\bbuywrite\b"),
)
THEMA_BREIT = "Breiter Markt"

ERTRAG = ("Ausschüttend", "Thesaurierend")
_AUSSCHUETTEND = re.compile(r"\(dist\)|\bdist\b|\bdis\b|\bdistributing\b|\bausschütt|\bausschuett|\b[0-9]D\b|"
                            r"\binc\b|\bincome\b", re.I)
_THESAURIEREND = re.compile(r"\(acc\)|\bacc\b|\baccumulating\b|\bthesaur|\b[0-9]C\b", re.I)


def _erster(text, tabelle, standard):
    for titel, muster in tabelle:
        if re.search(muster, text, re.I):
            return titel
    return standard


def ertrag(name):
    """Ausschüttend / Thesaurierend / None (nicht im Namen)."""
    n = str(name or "")
    # "Income"-ETFs schuetten aus - es sei denn, Acc steht ausdruecklich dabei
    if _THESAURIEREND.search(n) and not re.search(r"\(dist\)|\bdist\b|\bdistributing\b", n, re.I):
        return "Thesaurierend"
    if _AUSSCHUETTEND.search(n):
        return "Ausschüttend"
    return None


def merkmale(name):
    """-> {"anbieter", "region", "themen": [..], "ertrag": str|None, "hebel": bool}"""
    n = " ".join(str(name or "").replace("_", " ").split())
    themen = [t for t, m in THEMEN if re.search(m, n, re.I)]
    # Gold-ETCs sind Edelmetall, nicht "Energie & Rohstoffe" allgemein - nur ein Etikett
    if "Edelmetalle" in themen and "Energie & Rohstoffe" in themen and not re.search(
            r"\benergy\b|\boil\b|\bcommodit|\bmining\b|\buranium\b|\blithium\b|\bagricult", n, re.I):
        themen.remove("Energie & Rohstoffe")
    return {"anbieter": _erster(n, ANBIETER, "Sonstige"),
            "region": _erster(n, REGIONEN, "Sonstige"),
            "themen": themen or [THEMA_BREIT],
            "ertrag": ertrag(n),
            "hebel": bool(KS.HEBEL.search(n))}


def auswahl(werte, feld):
    """Alle vorkommenden Auspraegungen eines Merkmals, haeufigste zuerst -> [(wert, anzahl)]"""
    zaehler = {}
    for w in werte.values():
        mm = w.get("mm") or {}
        for v in (mm.get(feld) if feld == "themen" else [mm.get(feld)]) or []:
            if v:
                zaehler[v] = zaehler.get(v, 0) + 1
    return sorted(zaehler.items(), key=lambda x: (-x[1], x[0]))


def passt(mm, wahl):
    """wahl: {"anbieter": set, "region": set, "themen": set, "ertrag": set, "ohne_hebel": bool}; leere Mengen
    filtern nicht. Themen: mindestens eines der gewaehlten."""
    mm = mm or {}
    for feld in ("anbieter", "region", "ertrag"):
        if wahl.get(feld) and mm.get(feld) not in wahl[feld]:
            return False
    if wahl.get("themen") and not set(mm.get("themen") or []) & set(wahl["themen"]):
        return False
    if wahl.get("ohne_hebel") and mm.get("hebel"):
        return False
    return True
