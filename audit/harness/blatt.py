"""Langen Screenshot in Spalten nebeneinander legen (Kontaktbogen)."""
import sys
from PIL import Image
def blatt(quelle, ziel, spalte_h=1300, skala=0.75, max_spalten=6, start=0):
    im = Image.open(quelle).convert("RGB")
    w, h = im.size
    teile = []
    y = start
    while y < h and len(teile) < max_spalten:
        teile.append(im.crop((0, y, w, min(y + spalte_h, h))))
        y += spalte_h
    sw, sh = int(w * skala), int(spalte_h * skala)
    out = Image.new("RGB", (sw * len(teile) + 8 * (len(teile) - 1), sh), (60, 60, 60))
    for i, t in enumerate(teile):
        t = t.resize((sw, int(t.size[1] * skala)))
        out.paste(t, (i * (sw + 8), 0))
    out.save(ziel)
if __name__ == "__main__":
    a = sys.argv
    blatt(a[1], a[2], int(a[3]) if len(a) > 3 else 1300, float(a[4]) if len(a) > 4 else 0.75,
          int(a[5]) if len(a) > 5 else 6, int(a[6]) if len(a) > 6 else 0)
