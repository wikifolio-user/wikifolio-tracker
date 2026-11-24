"""Tests Kanal-Radar (youtube_radar.py, youtube_radar_agent.py) - mit Feed im echten YouTube-RSS-Format, ohne Netz."""
import datetime
import unittest

import youtube_radar as YR
import youtube_radar_agent as AG

UTC = datetime.timezone.utc
JETZT = datetime.datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


def eintrag(vid, views, likes, tage_alt, shorts=False):
    pub = (JETZT - datetime.timedelta(days=tage_alt)).isoformat()
    link = f"https://www.youtube.com/shorts/{vid}" if shorts else f"https://www.youtube.com/watch?v={vid}"
    return f"""
 <entry>
  <id>yt:video:{vid}</id>
  <yt:videoId>{vid}</yt:videoId>
  <yt:channelId>UCabcdefghijklmnopqrstuv</yt:channelId>
  <title>Video {vid} &amp; mehr</title>
  <link rel="alternate" href="{link}"/>
  <published>{pub}</published>
  <media:group>
   <media:title>Video {vid}</media:title>
   <media:thumbnail url="https://i1.ytimg.com/vi/{vid}/hqdefault.jpg" width="480" height="360"/>
   <media:community>
    <media:starRating count="{likes}" average="5.00" min="1" max="5"/>
    <media:statistics views="{views}"/>
   </media:community>
  </media:group>
 </entry>"""


def feed(eintraege, cid="abcdefghijklmnopqrstuv"):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">
 <id>yt:channel:{cid}</id>
 <yt:channelId>{cid}</yt:channelId>
 <title>Testkanal</title>{''.join(eintraege)}
</feed>"""


STANDARD = [eintrag("a1", 10000, 500, 10), eintrag("a2", 12000, 400, 12), eintrag("a3", 9000, 300, 14),
            eintrag("a4", 11000, 350, 16), eintrag("hit", 200000, 9000, 10), eintrag("s1", 50000, 3000, 5, True)]


class Antwort:
    def __init__(self, code, text=""):
        self.status_code, self.text = code, text


class Feed(unittest.TestCase):
    def test_parsen(self):
        f = YR.rss_parsen(feed(STANDARD))
        self.assertEqual(f["kanal_id"], "UCabcdefghijklmnopqrstuv")          # "UC" ergaenzt
        self.assertEqual(f["name"], "Testkanal")
        self.assertEqual(len(f["videos"]), 6)
        v = f["videos"][0]
        self.assertEqual((v["id"], v["views"], v["likes"], v["shorts"]), ("a1", 10000, 500, False))
        self.assertEqual(v["titel"], "Video a1 & mehr")
        self.assertTrue(f["videos"][-1]["shorts"])

    def test_ungueltig(self):
        with self.assertRaises(YR.RadarFehler):
            YR.rss_parsen("<html>kein feed")
        with self.assertRaises(YR.RadarFehler):
            YR.rss_parsen("<rss></rss>")

    def test_abrufen_fehler(self):
        with self.assertRaises(YR.RadarFehler):
            YR.abrufen("UCx", lambda *a, **k: Antwort(404))
        with self.assertRaises(YR.RadarFehler):
            YR.abrufen("UCx", lambda *a, **k: (_ for _ in ()).throw(OSError()))
        self.assertEqual(len(YR.abrufen("UCx", lambda *a, **k: Antwort(200, feed(STANDARD)))["videos"]), 6)

    def test_kanal_id(self):
        self.assertEqual(YR.kanal_id("UCBJycsmduvYEL83R_U4JriQ"), "UCBJycsmduvYEL83R_U4JriQ")
        self.assertEqual(YR.kanal_id("https://www.youtube.com/channel/UCBJycsmduvYEL83R_U4JriQ/videos"),
                         "UCBJycsmduvYEL83R_U4JriQ")
        for x in ("@mkbhd", "https://www.youtube.com/@mkbhd", "abc"):
            with self.assertRaises(YR.RadarFehler):
                YR.kanal_id(x)


class Kennzahlen(unittest.TestCase):
    def test_momentaufnahmen_und_wachstum(self):
        f = YR.rss_parsen(feed(STANDARD))
        r = YR.einfuegen({}, f, JETZT)
        self.assertIsNone(YR.wachstum(r["videos"]["a1"]["verlauf"]))      # eine Momentaufnahme ist kein Wachstum
        r = YR.einfuegen(r, f, JETZT + datetime.timedelta(minutes=30))
        self.assertEqual(len(r["videos"]["a1"]["verlauf"]), 1)             # innerhalb einer Stunde ersetzt
        f2 = YR.rss_parsen(feed([eintrag("a1", 12000, 520, 10)] + STANDARD[1:]))
        r = YR.einfuegen(r, f2, JETZT + datetime.timedelta(hours=24))
        self.assertEqual(len(r["videos"]["a1"]["verlauf"]), 2)
        self.assertAlmostEqual(YR.wachstum(r["videos"]["a1"]["verlauf"]), 2000 / (23.5 / 24), places=0)
        r = YR.einfuegen(r, f2, JETZT + datetime.timedelta(hours=30))
        self.assertIsNotNone(YR.wachstum(r["videos"]["a1"]["verlauf"]))

    def test_outlier_und_score(self):
        r = YR.einfuegen({}, YR.rss_parsen(feed(STANDARD)), JETZT)
        z = {x["id"]: x for x in YR.kennzahlen(r, JETZT)}
        self.assertGreater(z["hit"]["outlier"], 15)
        self.assertEqual(z["hit"]["outlier_stufe"], 10 if z["hit"]["outlier"] < 20 else 20)
        self.assertIsNone(z["s1"]["outlier"])                              # Shorts nur mit Shorts verglichen
        self.assertTrue(z["hit"]["vorlaeufig"])
        self.assertIn("Verhältnis zur Kanalgröße", z["hit"]["score_fehlt"])
        self.assertEqual(max(z.values(), key=lambda x: x["score"] or 0)["id"], "hit")
        self.assertAlmostEqual(z["a1"]["engagement_pct"], 5.0)

    def test_fehler_und_schaetzung(self):
        r = YR.fehler_merken({}, "UCx", "Feed 404", JETZT)
        self.assertEqual(r["kanaele"]["UCx"]["fehler"], "Feed 404")
        self.assertEqual(YR.werbung_schaetzung(10000), (10.0, 50.0))
        self.assertEqual(YR.werbung_schaetzung(0), (None, None))


class Agent(unittest.TestCase):
    def test_lauf_mit_fehlerhaftem_kanal(self):
        def get(url, **kw):
            return Antwort(404) if "UCkaputt" in url else Antwort(200, feed(STANDARD))
        r, ok, fehler = AG.lauf([{"id": "UCabcdefghijklmnopqrstuv", "name": "A"}, {"id": "UCkaputt", "name": "B"}],
                                {}, JETZT, get)
        self.assertEqual(ok, 1)
        self.assertEqual(len(fehler), 1)
        self.assertIn("UCabcdefghijklmnopqrstuv", r["kanaele"])
        self.assertTrue(r["kanaele"]["UCkaputt"]["fehler"])
        self.assertEqual(len(r["videos"]), 6)


if __name__ == "__main__":
    unittest.main()
