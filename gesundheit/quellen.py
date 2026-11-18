"""Externe Lebensmittel-Datenbanken (Provider-Schnittstelle).

Ein Provider hat suchen(begriff, get) -> [Lebensmittel im Format von lebensmittel.py]. get ist requests.get (in
Tests ersetzbar). Umgesetzt: Open Food Facts (frei, ohne Key, Herstellerangaben). Vorbereitet, aber NICHT
umgesetzt (keine vorgetaeuschten Funktionen): Barcode-Scan (Open Food Facts kann Barcodes - fehlt nur die
Kamera-Erkennung), Apple Health / Google Health Connect / Fitness-Tracker (brauchen eine native App bzw.
Exportdateien - kommt nur als Import einer exportierten Datei in Frage).
"""
import logging

from . import lebensmittel as L
from . import naehrstoffe as N

OFF_URL = "https://world.openfoodfacts.org/cgi/search.pl"
OFF_HEADERS = {"User-Agent": "FinanzDashboard-Gesundheit/1.0 (privat)"}   # OFF bittet um eine Kennung, ohne Personendaten
_OFF_FELDER = {"kcal": "energy-kcal_100g", "protein": "proteins_100g", "kh": "carbohydrates_100g",
               "zucker": "sugars_100g", "fett": "fat_100g", "fett_ges": "saturated-fat_100g",
               "ballast": "fiber_100g", "salz": "salt_100g"}


# Mikronaehrstoffe: Open Food Facts liefert sie in g je 100 g -> in die Basiseinheit des Naehrstoffs umrechnen
_OFF_MIKRO = {"vit_a": "vitamin-a", "vit_b1": "vitamin-b1", "vit_b2": "vitamin-b2", "vit_b3": "vitamin-pp",
              "vit_b5": "pantothenic-acid", "vit_b6": "vitamin-b6", "vit_b7": "biotin", "vit_b9": "vitamin-b9",
              "vit_b12": "vitamin-b12", "vit_c": "vitamin-c", "vit_d": "vitamin-d", "vit_e": "vitamin-e",
              "vit_k": "vitamin-k", "calcium": "calcium", "magnesium": "magnesium", "kalium": "potassium",
              "natrium": "sodium", "phosphor": "phosphorus", "chlorid": "chloride", "eisen": "iron", "zink": "zinc",
              "kupfer": "copper", "mangan": "manganese", "selen": "selenium", "jod": "iodine", "chrom": "chromium",
              "molybdaen": "molybdenum", "fluorid": "fluoride", "omega3": "omega-3-fat",
              "epa": "eicosapentaenoic-acid", "dha": "docosahexaenoic-acid", "ala": "alpha-linolenic-acid",
              "omega6": "omega-6-fat", "cholesterin": "cholesterol"}


def _zahl(x):
    try:
        z = float(x)
    except (TypeError, ValueError):
        return None
    return z if z == z and z >= 0 else None


def off_produkt(p):
    """Open-Food-Facts-Produkt -> Lebensmittel oder None (ohne Namen oder Kalorien unbrauchbar)."""
    name = str(p.get("product_name_de") or p.get("product_name") or "").strip()
    n = p.get("nutriments") or {}
    pro100 = {k: _zahl(n.get(f)) for k, f in _OFF_FELDER.items()}
    for k, f in _OFF_MIKRO.items():
        g = _zahl(n.get(f + "_100g"))
        if g is not None:
            pro100[k] = round(N.umrechnen(g, "g", N.NAEHRSTOFFE[k].einheit), 4)
    pro100 = L.natrium_aus_salz({k: v for k, v in pro100.items() if v is not None})   # fehlend = unbekannt
    if not name or "kcal" not in pro100 or not p.get("code"):
        return None
    einheiten = {}
    portion = _zahl(p.get("serving_quantity"))
    if portion:
        einheiten["Portion"] = portion
    basis = "ml" if str(p.get("quantity") or "").strip().lower().endswith(("ml", " l", "cl")) else "g"
    return {"id": f"off:{p['code']}", "name": name[:80], "kategorie": "Produkt", "basis": basis, "pro100": pro100,
            "einheiten": einheiten, "quelle": "Open Food Facts", "marke": str(p.get("brands") or "").split(",")[0][:40],
            "such": ""}


def off_suchen(begriff, get, limit=15):
    """Produkte bei Open Food Facts suchen. -> (treffer, fehler_text oder None)"""
    begriff = str(begriff or "").strip()
    if len(begriff) < 2:
        return [], None
    try:
        r = get(OFF_URL, params={"search_terms": begriff, "search_simple": 1, "action": "process", "json": 1,
                                 "page_size": limit * 2, "lc": "de", "cc": "de",
                                 "fields": "code,product_name,product_name_de,brands,nutriments,serving_quantity,quantity"},
                headers=OFF_HEADERS, timeout=12)
        if r.status_code != 200:
            return [], "Die Online-Datenbank antwortet gerade nicht. Bitte später erneut versuchen."
        produkte = (r.json() or {}).get("products") or []
    except Exception as e:
        logging.warning(f"Open Food Facts: {type(e).__name__}")
        return [], "Die Online-Datenbank ist gerade nicht erreichbar. Bitte später erneut versuchen."
    aus, gesehen = [], set()
    for p in produkte:
        lm = off_produkt(p if isinstance(p, dict) else {})
        if lm and lm["id"] not in gesehen:
            gesehen.add(lm["id"])
            aus.append(lm)
    return aus[:limit], None
