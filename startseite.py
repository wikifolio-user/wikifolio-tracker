"""Ueberblick-Kacheln der Startseite (Audit UX-02) - ohne Streamlit, ohne Netz testbar.

Quellen sind nur gespeicherte Daten: die Chronik (Kurs-Alarme der Workflows stehen dort als Kategorie "alarm")
und die EKS-Ideen des Benutzers. Es werden keine Kurse abgerufen.
"""
import logging

import chronik


def datum_kurz(eintrag):
    """Chronik-Eintrag -> "16.11. 09:25 Uhr" (ohne Uhrzeit, wenn keine gespeichert ist)."""
    d = str(eintrag.get("datum") or "")
    teile = d.split("-")
    txt = f"{teile[2]}.{teile[1]}." if len(teile) == 3 else d
    return txt + (f" {eintrag['zeit']} Uhr" if eintrag.get("zeit") else "")


def ueberblick_daten(chronik_liste, eks_roh):
    """-> Liste von (key, label, wert, unterzeile, ziel) mit ziel "chronik" oder "eks"; leere Bereiche entfallen."""
    kacheln = []
    eintraege = [x for x in (chronik_liste if isinstance(chronik_liste, list) else []) if isinstance(x, dict)]
    alarm = next((x for x in eintraege if chronik.kategorie_von(x) == "alarm"), None)
    if alarm:
        kacheln.append(("alarm", "Letzter Alarm", alarm.get("titel") or "–", datum_kurz(alarm), "chronik"))
    letzt = next((x for x in eintraege if chronik.kategorie_von(x) not in ("alarm", "zugang")), None)
    if letzt:
        kacheln.append(("chronik", "Chronik", letzt.get("titel") or "–", datum_kurz(letzt), "chronik"))
    if isinstance(eks_roh, dict) and eks_roh.get("ideen"):
        try:
            from eks_rechner import modell as M, rechnen as R
            rang = [r for r in R.rangliste(M.bereinigen(eks_roh)) if r["status"] != "verworfen"]
        except Exception as e:
            logging.warning(f"Ueberblick EKS: {type(e).__name__}")
            rang = []
        if rang:
            zahl = {k: sum(1 for r in rang if r["ampel"] == k) for k in ("gruen", "gelb", "rot")}
            wert = "  ".join(f"{R.AMPEL[k]} {n}" for k, n in zahl.items())
            stand = str(((eks_roh.get("letzter_lauf") or {}).get("stand") or ""))[:10]
            sub = (f"Monatslauf {stand[8:10]}.{stand[5:7]}." if len(stand) == 10 and stand[4] == "-"
                   else f"{len(rang)} aktive Idee" + ("n" if len(rang) != 1 else ""))
            kacheln.append(("eks", "EKS-Ideen", wert, sub, "eks"))
    return kacheln
