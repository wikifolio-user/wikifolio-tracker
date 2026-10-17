"""Tests fuer login.py (python3 -m unittest test_login) - ohne Streamlit, ohne Netz.
`st` wird durch eine kleine Attrappe ersetzt."""
import contextlib
import copy
import unittest
from unittest import mock

import chronik as C
import login as L


class Stop(Exception):
    pass


class Rerun(Exception):
    pass


class _Ctx:
    def __init__(self, headers=None):
        self.headers = headers or {}


class FakeSt:
    """Minimale Streamlit-Attrappe: eine frische Instanz = eine frische Sitzung."""
    def __init__(self, secrets=None, eingaben=None, gedrueckt=(), headers=None):
        self.secrets = secrets if secrets is not None else {}
        self.session_state = {}
        self.eingaben = dict(eingaben or {})    # label oder key -> Wert
        self.gedrueckt = set(gedrueckt)         # Labels von Submit-Knoepfen / Keys von Buttons
        self.context = _Ctx(headers)
        self.fehler, self.warnungen, self.erfolge, self.infos, self.toasts, self.codes = [], [], [], [], [], []

    # Ausgaben
    def error(self, t, **k): self.fehler.append(t)
    def warning(self, t, **k): self.warnungen.append(t)
    def success(self, t, **k): self.erfolge.append(t)
    def info(self, t, **k): self.infos.append(t)
    def toast(self, t, **k): self.toasts.append(t)
    def code(self, t, **k): self.codes.append(t)
    def markdown(self, *a, **k): pass
    def caption(self, *a, **k): pass
    def divider(self, *a, **k): pass

    # Steuerung
    def stop(self): raise Stop()
    def rerun(self, scope=None): raise Rerun()

    # Layout
    def container(self, **k): return contextlib.nullcontext()
    def form(self, *a, **k): return contextlib.nullcontext()
    def expander(self, *a, **k): return contextlib.nullcontext()
    def columns(self, n): return [self] * (n if isinstance(n, int) else len(n))

    # Eingaben
    def text_input(self, label, key=None, **k):
        return self.eingaben.get(key, self.eingaben.get(label, ""))

    def form_submit_button(self, label, **k):
        return label in self.gedrueckt

    def button(self, label, key=None, **k):
        return (key or label) in self.gedrueckt

    def toggle(self, label, value=False, key=None, **k):
        if key and key in self.session_state:
            return self.session_state[key]
        return value


SECRETS = {"login": {"admin_benutzer": "chef", "admin_passwort_hash": L.passwort_hash("Admin-Passwort-123")}}


class FakeStore:
    """benutzer.json im Speicher; gh_aktualisiere mit optionalem Fremd-Schreiber zwischen Lesen und Schreiben."""
    def __init__(self, daten=None):
        self.daten = copy.deepcopy(daten or {})
        self.schreib_ok = True
        self.vor_aendern = None      # wird einmal nach dem "Lesen" der Fassung des Aufrufers ausgefuehrt
        self.writes = 0
        self.reads = 0

    def gh_read(self, path, default):
        self.reads += 1
        return copy.deepcopy(self.daten)

    gh_read_cached = gh_read

    def gh_write(self, path, obj, message=""):
        if not self.schreib_ok:
            return False
        self.daten = copy.deepcopy(obj)
        self.writes += 1
        return True

    def gh_aktualisiere(self, path, aendern, default=None, message=""):
        if not self.schreib_ok:
            return False, None
        if self.vor_aendern:                      # Konflikt: jemand schreibt dazwischen -> Retry mit frischen Daten
            f, self.vor_aendern = self.vor_aendern, None
            f()
        neu = aendern(copy.deepcopy(self.daten))
        if neu is None:
            return True, self.daten
        self.daten = copy.deepcopy(neu)
        self.writes += 1
        return True, neu


def _store_mit_anna():
    return FakeStore({"benutzer": {"anna": {"hash": L.passwort_hash("Richtig-Passwort-1"), "aktiv": True,
                                            "ansichten": None, "zuletzt": "2020-01-01T10:15"}}})


class Basis(unittest.TestCase):
    def setUp(self):
        L._zaehler_leeren()
        self.p = mock.patch.object(L, "_bremse", lambda: None)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def login_versuch(self, store, name, pw, chronik=None, headers=None, secrets=SECRETS, gh_aktualisiere=True):
        st = FakeSt(secrets, {"👤 Benutzername": name, "🔑 Passwort": pw}, {"Anmelden"}, headers)
        kw = {"gh_aktualisiere": store.gh_aktualisiere} if gh_aktualisiere else {}
        try:
            L.gate(st, store.gh_read, store.gh_read_cached, store.gh_write, chronik, **kw)
        except Rerun:
            return st, "rerun"
        except Stop:
            return st, "stop"
        return st, "return"


class Sperre(Basis):
    def test_sperre_ueber_frische_sitzungen(self):
        store = _store_mit_anna()
        for _ in range(L.MAX_FEHLVERSUCHE):          # jede Runde eine neue Sitzung (Neuladen)
            st, erg = self.login_versuch(store, "Anna", "falsch")
            self.assertEqual(erg, "stop")
        # neue Sitzung, RICHTIGES Passwort -> trotzdem gesperrt
        st, erg = self.login_versuch(store, "anna", "Richtig-Passwort-1")
        self.assertEqual(erg, "stop")
        self.assertNotIn("login_name", st.session_state)
        self.assertTrue(any("Fehlversuche" in f for f in st.fehler))

    def test_sperre_laeuft_ab_und_verdoppelt(self):
        k = L._schluessel("bob")
        t = 1000.0
        for i in range(L.MAX_FEHLVERSUCHE):
            rest = L.fehlversuch_merken(k, t + i)
        self.assertAlmostEqual(rest, L.SPERRE_SEK)
        t2 = t + L.MAX_FEHLVERSUCHE + L.SPERRE_SEK + 1
        self.assertEqual(L.sperre_rest(k, t2), 0)
        for i in range(L.MAX_FEHLVERSUCHE):
            rest = L.fehlversuch_merken(k, t2 + i)
        self.assertAlmostEqual(rest, 2 * L.SPERRE_SEK)

    def test_sperre_hoechstens_15_minuten(self):
        k = L._schluessel("carl")
        t = 0.0
        for runde in range(8):
            for i in range(L.MAX_FEHLVERSUCHE):
                rest = L.fehlversuch_merken(k, t)
            self.assertLessEqual(rest, L.SPERRE_MAX_SEK)
            t += rest + 1
        self.assertAlmostEqual(rest, L.SPERRE_MAX_SEK)

    def test_ip_sperre(self):
        store = _store_mit_anna()
        h = {"X-Forwarded-For": "203.0.113.7, 10.0.0.1"}
        for i in range(L.MAX_FEHLVERSUCHE_IP):        # verschiedene Namen, gleiche IP
            self.login_versuch(store, f"x{i}", "falsch", headers=h)
        st, erg = self.login_versuch(store, "anna", "Richtig-Passwort-1", headers=h)
        self.assertEqual(erg, "stop")
        self.assertNotIn("login_name", st.session_state)
        # andere IP ist nicht betroffen
        st, erg = self.login_versuch(store, "anna", "Richtig-Passwort-1", headers={"X-Forwarded-For": "198.51.100.2"})
        self.assertEqual(erg, "rerun")

    def test_erfolg_setzt_zaehler_zurueck(self):
        store = _store_mit_anna()
        for _ in range(L.MAX_FEHLVERSUCHE - 1):
            self.login_versuch(store, "anna", "falsch")
        st, erg = self.login_versuch(store, "anna", "Richtig-Passwort-1")
        self.assertEqual(erg, "rerun")
        self.assertEqual(st.session_state["login_name"], "anna")
        self.login_versuch(store, "anna", "falsch")
        self.assertEqual(L.sperre_rest(L._schluessel("anna")), 0)


class FailClosed(Basis):
    def test_ohne_konfig_stop(self):
        st = FakeSt({"github": {"token": "x"}})
        with self.assertRaises(Stop):
            L.gate(st, None, None, None)
        text = " ".join(st.fehler + st.infos)
        for verboten in ("admin_benutzer", "admin_passwort", "github", "token"):
            self.assertNotIn(verboten, text)

    def test_unvollstaendige_konfig_stop(self):
        st = FakeSt({"login": {"admin_benutzer": "chef"}})
        with self.assertRaises(Stop):
            L.gate(st, None, None, None)

    def test_ausdruecklich_deaktiviert(self):
        for s in ({"login_deaktiviert": True}, {"login": {"login_deaktiviert": "true"}}):
            self.assertIsNone(L.gate(FakeSt(s), None, None, None))
        with self.assertRaises(Stop):
            L.gate(FakeSt({"login_deaktiviert": False}), None, None, None)

    def test_pruefen_ohne_konfig_neustart(self):
        st = FakeSt({})
        st.session_state["login_name"] = "anna"
        with self.assertRaises(Rerun):
            L.pruefen(st, lambda p, d: {})
        self.assertNotIn("login_name", st.session_state)

    def test_diagnose_ohne_schluesselnamen(self):
        d = L.diagnose(FakeSt({"geheimer_abschnitt": {"x": 1}}))
        self.assertNotIn("geheimer_abschnitt", d)
        self.assertNotIn("admin_", d)


class Timing(Basis):
    def test_unbekannt_und_gesperrt_nutzen_dummy_hash(self):
        cfg = L.konfig(FakeSt(SECRETS))
        daten = {"benutzer": {"gesperrt": {"hash": L.passwort_hash("Irgendwas-123"), "aktiv": False}}}
        echt = L.passwort_ok
        with mock.patch.object(L, "passwort_ok", wraps=echt) as po:
            self.assertFalse(L.pruefe_anmeldung(cfg, daten, "niemand", "x"))
            self.assertEqual(po.call_count, 1)
            self.assertTrue(L.ist_hash(po.call_args[0][1]))      # gegen den Dummy-Hash geprueft
            po.reset_mock()
            self.assertFalse(L.pruefe_anmeldung(cfg, daten, "gesperrt", "Irgendwas-123"))
            self.assertEqual(po.call_count, 1)
            self.assertIs(po.call_args[0][1], L._DUMMY["hash"])

    def test_klartext_admin_rechnet_auch_hash(self):
        cfg = L.konfig(FakeSt({"login": {"admin_benutzer": "chef", "admin_passwort": "klartext-pw-123"}}))
        self.assertFalse(cfg["admin_pw_hash"])
        with mock.patch.object(L, "_dummy_pruefen", wraps=L._dummy_pruefen) as d:
            self.assertTrue(L.pruefe_anmeldung(cfg, {}, "Chef", "klartext-pw-123"))
            self.assertEqual(d.call_count, 1)

    def test_admin_hash_login(self):
        cfg = L.konfig(FakeSt(SECRETS))
        self.assertTrue(cfg["admin_pw_hash"])
        self.assertTrue(L.pruefe_anmeldung(cfg, {}, "chef", "Admin-Passwort-123"))
        self.assertFalse(L.pruefe_anmeldung(cfg, {}, "chef", "falsch"))


class Zuletzt(Basis):
    def test_zuletzt_nur_datum_und_chronik_einmal_pro_tag(self):
        store = _store_mit_anna()
        aufrufe = []
        chronik = lambda *a, **k: aufrufe.append((a, k))
        st, erg = self.login_versuch(store, "anna", "Richtig-Passwort-1", chronik=chronik)
        self.assertEqual(erg, "rerun")
        z = store.daten["benutzer"]["anna"]["zuletzt"]
        self.assertRegex(z, r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(len(aufrufe), 1)
        self.assertEqual(aufrufe[0][1]["schluessel"], f"login-anna-{z.replace('-', '')}")
        w = store.writes
        self.login_versuch(store, "anna", "Richtig-Passwort-1", chronik=chronik)   # zweiter Login am selben Tag
        self.assertEqual(store.writes, w)
        self.assertEqual(len(aufrufe), 1)

    def test_gleichzeitige_sperre_wird_nicht_ueberschrieben(self):
        store = _store_mit_anna()
        # Admin sperrt anna, nachdem ihr Login die (gecachte) Liste gelesen hat
        store.vor_aendern = lambda: store.daten["benutzer"]["anna"].__setitem__("aktiv", False)
        st, erg = self.login_versuch(store, "anna", "Richtig-Passwort-1")
        self.assertFalse(store.daten["benutzer"]["anna"]["aktiv"])
        self.assertEqual(erg, "stop")
        self.assertNotIn("login_name", st.session_state)

    def test_gleichzeitige_rechteaenderung_bleibt(self):
        store = _store_mit_anna()
        store.vor_aendern = lambda: store.daten["benutzer"]["anna"].__setitem__("ansichten", ["depot"])
        st, erg = self.login_versuch(store, "anna", "Richtig-Passwort-1")
        self.assertEqual(erg, "rerun")
        self.assertEqual(store.daten["benutzer"]["anna"]["ansichten"], ["depot"])
        self.assertRegex(store.daten["benutzer"]["anna"]["zuletzt"], r"^\d{4}-\d{2}-\d{2}$")

    def test_chronik_login_ohne_uhrzeit(self):
        e = C.neuer_eintrag("zugang", "🔐 Anmeldung: anna", schluessel="login-anna-20261012")
        self.assertEqual(e["zeit"], "")
        liste, ok1 = C.anhaengen([], e)
        liste, ok2 = C.anhaengen(liste, dict(e))
        self.assertEqual((ok1, ok2, len(liste)), (True, False, 1))


class Verwaltung(Basis):
    def _render(self, store, eingaben=None, gedrueckt=(), secrets=SECRETS, mit_aktualisiere=True):
        st = FakeSt(secrets, eingaben, gedrueckt)
        kw = {"gh_aktualisiere": store.gh_aktualisiere} if mit_aktualisiere else {}
        try:
            L.render_verwaltung(st, store.gh_read, store.gh_write, ["depot", "chronik"], {}, **kw)
            erg = "return"
        except Rerun:
            erg = "rerun"
        return st, erg

    def test_passwort_speicherfehler_zeigt_fehler(self):
        for mit in (True, False):
            store = _store_mit_anna()
            store.schreib_ok = False
            st, _ = self._render(store, {"bv_pw_anna": "Ganz-neues-Pw-77"}, {"bv_pwb_anna"}, mit_aktualisiere=mit)
            self.assertEqual(st.erfolge, [])
            self.assertTrue(any("Speichern nicht möglich" in f for f in st.fehler))

    def test_sperren_speicherfehler_kein_rerun(self):
        store = _store_mit_anna()
        store.schreib_ok = False
        st, erg = self._render(store, gedrueckt={"bv_akt_anna"})
        self.assertEqual(erg, "return")
        self.assertTrue(st.fehler)
        self.assertTrue(store.daten["benutzer"]["anna"]["aktiv"])

    def test_loeschen_fragt_erst_nach(self):
        store = _store_mit_anna()
        st, erg = self._render(store, gedrueckt={"bv_del_anna"})
        self.assertIn("anna", store.daten["benutzer"])           # noch nicht geloescht
        self.assertTrue(st.session_state.get("bv_del_frage_anna"))
        self.assertTrue(any("wirklich löschen" in w for w in st.warnungen))

    def test_loeschen_entfernt_zugang_und_daten(self):
        store = _store_mit_anna()
        aufrufe = []

        def daten_loeschen(name):
            aufrufe.append(name)
            return True, 3

        st = FakeSt(SECRETS, None, {"bv_del_ja_anna"})
        st.session_state["bv_del_frage_anna"] = True
        with self.assertRaises(Rerun):
            L.render_verwaltung(st, store.gh_read, store.gh_write, ["depot"], {},
                                gh_aktualisiere=store.gh_aktualisiere, daten_loeschen=daten_loeschen)
        self.assertNotIn("anna", store.daten["benutzer"])
        self.assertEqual(aufrufe, ["anna"])
        self.assertIn("3 Datei(en)", st.session_state["rechte_meldung"])

    def test_loeschen_abbrechen(self):
        store = _store_mit_anna()
        st = FakeSt(SECRETS, None, {"bv_del_nein_anna"})
        st.session_state["bv_del_frage_anna"] = True
        with self.assertRaises(Rerun):
            L.render_verwaltung(st, store.gh_read, store.gh_write, ["depot"], {},
                                gh_aktualisiere=store.gh_aktualisiere, daten_loeschen=lambda n: (True, 0))
        self.assertIn("anna", store.daten["benutzer"])

    def test_sperren_ok(self):
        store = _store_mit_anna()
        st, erg = self._render(store, gedrueckt={"bv_akt_anna"})
        self.assertEqual(erg, "rerun")
        self.assertFalse(store.daten["benutzer"]["anna"]["aktiv"])

    def test_passwort_regeln(self):
        store = _store_mit_anna()
        alt = store.daten["benutzer"]["anna"]["hash"]
        for pw in ("kurz", "1234567890", "Passwort123"):
            st, _ = self._render(store, {"bv_pw_anna": pw}, {"bv_pwb_anna"})
            self.assertTrue(st.fehler, pw)
            self.assertEqual(store.daten["benutzer"]["anna"]["hash"], alt)
        st, _ = self._render(store, {"bv_pw_anna": "Ganz-neues-Pw-77"}, {"bv_pwb_anna"})
        self.assertEqual(st.erfolge, ["Passwort geändert."])
        self.assertTrue(L.passwort_ok("Ganz-neues-Pw-77", store.daten["benutzer"]["anna"]["hash"]))

    def test_anlegen_nicht_ueberschreiben(self):
        store = _store_mit_anna()
        # zwischen Anzeige und Speichern legt ein anderer Admin-Tab "bert" an
        store.vor_aendern = lambda: store.daten["benutzer"].__setitem__("bert", {"hash": "x", "aktiv": True})
        st, erg = self._render(store, {"Benutzername": "bert", f"Passwort (min. {L.MIN_LAENGE} Zeichen)":
                                       "Bert-Passwort-99"}, {"Anlegen"})
        self.assertEqual(erg, "return")
        self.assertEqual(store.daten["benutzer"]["bert"]["hash"], "x")
        self.assertTrue(any("existiert" in f for f in st.fehler))
        self.assertIn("anna", store.daten["benutzer"])

    def test_klartext_admin_warnung(self):
        store = _store_mit_anna()
        st, _ = self._render(store, secrets={"login": {"admin_benutzer": "chef", "admin_passwort": "kurz"}})
        self.assertTrue(any("Klartext" in w for w in st.warnungen))
        self.assertTrue(any("passwort_hash" in c for c in st.codes))
        st, _ = self._render(store)
        self.assertFalse(any("Klartext" in w for w in st.warnungen))


class AdminHash(Verwaltung):
    def test_funktion(self):
        h, f = L.admin_hash_erzeugen("Neues-Admin-PW-2026", "Neues-Admin-PW-2026", "chef")
        self.assertIsNone(f)
        self.assertTrue(L.ist_hash(h))
        self.assertTrue(L.passwort_ok("Neues-Admin-PW-2026", h))
        self.assertFalse(L.passwort_ok("falsch", h))

    def test_ablehnungen(self):
        self.assertIn("überein", L.admin_hash_erzeugen("Neues-Admin-PW-2026", "anders-12345678", "chef")[1])
        self.assertIn("zu kurz", L.admin_hash_erzeugen("kurz-123", "kurz-123", "chef")[1])
        self.assertIsNone(L.admin_hash_erzeugen("1111111111111", "1111111111111", "chef")[0])

    def test_formular_gibt_secrets_zeile_aus(self):
        store = _store_mit_anna()
        vorher = store.writes
        st, _ = self._render(store, {"admin_hash_pw1": "Neues-Admin-PW-2026", "admin_hash_pw2": "Neues-Admin-PW-2026"},
                             {"Hash erzeugen"})
        zeilen = [c for c in st.codes if c.startswith("admin_passwort_hash = ")]
        self.assertEqual(len(zeilen), 1)
        h = zeilen[0].split('"')[1]
        self.assertTrue(L.passwort_ok("Neues-Admin-PW-2026", h))
        self.assertEqual(store.writes, vorher)                     # nichts gespeichert

    def test_formular_ohne_absenden_kein_hash(self):
        st, _ = self._render(_store_mit_anna())
        self.assertFalse(any(c.startswith("admin_passwort_hash") for c in st.codes))

if __name__ == "__main__":
    unittest.main()


class Sitzung(Basis):                                   # Audit A-13
    CFG = {"admin": "chef", "admin_pw": "pbkdf2_sha256$1$00$00", "admin_pw_hash": True}

    def _daten(self, h="pbkdf2_sha256$1$aa$bb"):
        return {"benutzer": {"anna": {"hash": h, "aktiv": True}}}

    def test_gueltig_nach_anmeldung(self):
        d = self._daten()
        ss = {"login_pw": L.pw_kennung(self.CFG, d, "anna"), "login_seit": 1000.0}
        self.assertTrue(L.sitzung_gueltig(ss, self.CFG, d, "anna", jetzt=1000.0 + 3600))

    def test_passwortwechsel_beendet_sitzung(self):
        ss = {"login_pw": L.pw_kennung(self.CFG, self._daten(), "anna"), "login_seit": 1000.0}
        self.assertFalse(L.sitzung_gueltig(ss, self.CFG, self._daten("pbkdf2_sha256$1$cc$dd"), "anna", jetzt=1001.0))

    def test_hoechstdauer(self):
        d = self._daten()
        ss = {"login_pw": L.pw_kennung(self.CFG, d, "anna"), "login_seit": 0.0}
        self.assertFalse(L.sitzung_gueltig(ss, self.CFG, d, "anna", jetzt=L.MAX_SITZUNG_SEK + 1))

    def test_alte_sitzung_ohne_kennung_ungueltig(self):
        self.assertFalse(L.sitzung_gueltig({}, self.CFG, self._daten(), "anna"))

    def test_admin_secret_wechsel(self):
        ss = {"login_pw": L.pw_kennung(self.CFG, {}, "chef"), "login_seit": 1.0}
        neu = dict(self.CFG, admin_pw="pbkdf2_sha256$1$11$22")
        self.assertFalse(L.sitzung_gueltig(ss, neu, {}, "chef", jetzt=2.0))

    def test_gate_meldet_abgelaufene_sitzung_ab(self):
        store = _store_mit_anna()
        st, erg = self.login_versuch(store, "anna", "Richtig-Passwort-1")
        self.assertEqual(erg, "rerun")
        st.session_state["login_seit"] -= L.MAX_SITZUNG_SEK + 10
        with self.assertRaises(Rerun):
            L.pruefen(st, store.gh_read_cached)
        self.assertNotIn("login_name", st.session_state)


class SpeicherAusfall(Basis):                           # Audit A-10
    def test_ehrliche_meldung_ohne_fehlversuch(self):
        store = FakeStore({})
        st = FakeSt(SECRETS, {"👤 Benutzername": "anna", "🔑 Passwort": "Richtig-Passwort-1"}, {"Anmelden"})
        with self.assertRaises(Stop):
            L.gate(st, store.gh_read, store.gh_read_cached, store.gh_write, speicher_fehler=lambda: True)
        self.assertTrue(any("Datenspeicher" in f for f in st.fehler))
        self.assertEqual(L.sperre_rest(L._schluessel("anna")), 0)
        self.assertFalse(any("falsch" in f for f in st.fehler))
