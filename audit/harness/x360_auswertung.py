import json, glob, sys, collections
S = sys.argv[1]
alle = []
for f in glob.glob(f"{S}/x360/*.json"):
    if f.endswith("probe.json"): continue
    alle += json.load(open(f))
print("Messungen:", len(alle), "Geräte:", sorted({(r['rolle'], r['geraet']) for r in alle}))
fehler = [r for r in alle if r.get("fehler")]
print("\n== App-/Harness-Fehler:", len(fehler))
for r in fehler[:40]: print(" ", r["rolle"], r["geraet"], r["ansicht"][:28], "|", r["teil"][:30], "|", r["fehler"][:2])
print("\n== Seitlicher Überlauf > 0:")
for r in alle:
    if (r.get("ueberlauf") or 0) > 0: print(" ", r["rolle"], r["geraet"], r["ansicht"][:28], r["teil"][:30], r["ueberlauf"])
print("\n== Elemente rechts außerhalb (ohne Scrollbereich):")
c = collections.Counter()
for r in alle:
    for x in r.get("raus") or []: c[(r["ansicht"][:25], r["teil"][:25], x[:30])] += 1
for k, n in c.most_common(30): print(" ", n, k)
print("\n== Abgeschnittene Texte:")
c = collections.Counter()
for r in alle:
    for x in r.get("geschnitten") or []: c[(r["ansicht"][:25], x[:40])] += 1
for k, n in c.most_common(30): print(" ", n, k)
print("\n== Konsole:")
c = collections.Counter()
for r in alle:
    for x in r.get("konsole") or []: c[(r["ansicht"][:25], x[:120])] += 1
for k, n in c.most_common(15): print(" ", n, k)
print("\n== axe:")
c = collections.Counter()
for r in alle:
    for v in r.get("axe") or []: c[(r["ansicht"][:25], v["id"], v["impact"])] += v["n"]
for k, n in c.most_common(30): print(" ", n, k)
d = sorted((r.get("dauer") or 0, r["ansicht"][:25], r["teil"][:25], r["geraet"]) for r in alle)
print("\n== langsamste:", d[-8:])
