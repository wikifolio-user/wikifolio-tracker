"""Login mit Benutzername + Passwort und Benutzerverwaltung.

- Der Admin steht in den Streamlit-Secrets (kann sich nie selbst aussperren):
      [login]
      admin_benutzer = "marc"
      admin_passwort_hash = "pbkdf2_sha256$200000$..."   # empfohlen (Audit SEC-06)
      # admin_passwort = "..."                          # Klartext: geht noch, erzeugt eine Warnung
  Hash erzeugen:  python3 -c "import getpass, login; print(login.passwort_hash(getpass.getpass()))"
- Weitere Benutzer legt der Admin in der App an (Menue -> 👥 Benutzer). Sie liegen in
  state/benutzer.json im GitHub-Speicher - Passwoerter nur als PBKDF2-Hash, nie im Klartext.
- Je Benutzer: welche Ansichten er sehen darf, aktiv/gesperrt, Passwort zuruecksetzen, loeschen.
  Gesperrte oder geloeschte Benutzer fliegen beim naechsten Seitenaufbau raus.
- Fail-closed (Audit SEC-03): fehlt die Login-Konfiguration oder ist sie unvollstaendig,
  bleibt die App gesperrt (Fehlerseite). Ohne Login laeuft sie nur mit ausdruecklichem
      login_deaktiviert = true
  (ganz oben oder im Abschnitt [login] der Secrets).
- Fehlversuche werden serverweit pro Benutzername (und pro Client-IP) gezaehlt
  (Audit SEC-02): 5 Fehlversuche in 15 Minuten -> 60 s Sperre, bei Wiederholung
  verdoppelt bis hoechstens 15 Minuten. Die Zaehler liegen nur im Arbeitsspeicher
  des Server-Prozesses (nach einem Neustart leer) und werden nie gespeichert.

Datensparsamkeit / Aufbewahrung (Audit DATA-06):
- Gespeichert wird je Benutzer nur das Datum der letzten Anmeldung ("zuletzt",
  YYYY-MM-DD, keine Uhrzeit), hoechstens ein Schreibvorgang pro Benutzer und Tag.
- Die Chronik erhaelt hoechstens einen Eintrag "Anmeldung" je Benutzer und Tag,
  ohne Uhrzeit; sie wird mit chronik.MAX_EINTRAEGE automatisch gekuerzt.
- Beim Loeschen eines Benutzers verschwindet sein Datensatz aus benutzer.json;
  Altstaende bleiben aber in der Git-Historie des Speicher-Repos und in den monatlichen
  Sicherungs-Tags state-backup-JJJJ-MM (die letzten 3, siehe squash-state-history.yml) -
  spaetestens nach rund 3 Monaten sind sie damit entfernt. Sofort: Tags loeschen und den
  State-Branch neu aufsetzen (History-Rewrite).
- Neue Benutzernamen: nur a-z, 0-9, "-" und "_" (nutzerdaten.name_pruefen, Audit A-03) -
  jeder Name hat so garantiert einen eigenen Datenordner.
- Sitzungen enden bei Passwortwechsel und spaetestens nach MAX_SITZUNG_SEK (Audit A-13).
"""
import datetime
import hashlib
import hmac
import logging
import secrets as _secrets
import threading
import time

import nutzerdaten

PFAD_BENUTZER = "state/benutzer.json"
ITERATIONEN = 200_000
MAX_ITERATIONEN = 2_000_000          # Schutz vor manipulierten Hashes (Rechenzeit)

# serverweite Sperre (Audit SEC-02)
MAX_FEHLVERSUCHE = 5                 # je Benutzername im Fenster
MAX_FEHLVERSUCHE_IP = 20             # je Client-IP (NAT/Haushalte teilen sich IPs)
FENSTER_SEK = 15 * 60
SPERRE_SEK = 60
SPERRE_MAX_SEK = 15 * 60
_MAX_ZAEHLER = 5000                  # Obergrenze Speicher (zufaellige Namen)

# Passwortregeln (Audit SEC-06)
MIN_LAENGE = 10
ADMIN_MIN_LAENGE = 12
HAEUFIGE_PASSWOERTER = frozenset({
    "1234567890", "0123456789", "1111111111", "123456789a", "1q2w3e4r5t",
    "qwertzuiop", "qwertyuiop", "password12", "password123", "passwort12",
    "passwort123", "passwort1234", "hallo12345", "hallo123456", "iloveyou12",
    "abc1234567", "admin12345", "letmein123", "sommer2024", "fussball123",
})

HASH_HINWEIS = 'python3 -c "import getpass, login; print(login.passwort_hash(getpass.getpass()))"'
SPEICHERFEHLER = "Speichern nicht möglich (GitHub-Speicher) – es wurde nichts geändert. Bitte erneut versuchen."


# ---------------------------------------------------------------------------
# Passwoerter
# ---------------------------------------------------------------------------
def passwort_hash(passwort, salz=None, iterationen=ITERATIONEN):
    salz = salz or _secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", passwort.encode("utf-8"), bytes.fromhex(salz), iterationen).hex()
    return f"pbkdf2_sha256${iterationen}${salz}${h}"


def ist_hash(gespeichert):
    return isinstance(gespeichert, str) and gespeichert.startswith("pbkdf2_sha256$")


def passwort_ok(passwort, gespeichert):
    """Prueft gegen einen Hash (pbkdf2_sha256$...) oder - nur fuer den Admin in den Secrets - Klartext."""
    if not gespeichert or passwort is None:
        return False
    if ist_hash(gespeichert):
        try:
            _, it, salz, soll = gespeichert.split("$")
            it = int(it)
            if not 0 < it <= MAX_ITERATIONEN:
                return False
            ist = passwort_hash(passwort, salz, it).split("$")[3]
            return hmac.compare_digest(ist, soll)
        except Exception:
            return False
    return hmac.compare_digest(passwort.encode("utf-8"), str(gespeichert).encode("utf-8"))


_DUMMY = {"hash": None}
_DUMMY_LOCK = threading.Lock()


def _dummy_pruefen(passwort):
    """Gleiche Rechenzeit wie eine echte Pruefung (Audit SEC-07): unbekannte, gesperrte
    oder Klartext-Konten verraten sich nicht ueber die Antwortzeit."""
    with _DUMMY_LOCK:
        if _DUMMY["hash"] is None:
            _DUMMY["hash"] = passwort_hash(_secrets.token_hex(16))
        h = _DUMMY["hash"]
    passwort_ok(passwort or "", h)
    return False


def passwort_pruefen(passwort, name=""):
    """Regeln fuer neue Passwoerter. -> Fehlertext oder None (= in Ordnung)."""
    pw = passwort or ""
    if len(pw) < MIN_LAENGE:
        return f"Passwort zu kurz (mindestens {MIN_LAENGE} Zeichen)."
    if pw.lower() in HAEUFIGE_PASSWOERTER:
        return "Dieses Passwort ist zu verbreitet – bitte ein anderes wählen."
    if name and pw.lower() == _norm(name):
        return "Passwort darf nicht dem Benutzernamen entsprechen."
    if len(set(pw)) <= 2:
        return "Passwort ist zu einfach."
    return None


def _norm(name):
    return str(name or "").strip().lower()


def _heute():
    """Datum (Europe/Berlin) als YYYY-MM-DD."""
    try:
        import chronik
        return chronik.jetzt().strftime("%Y-%m-%d")
    except Exception:
        return datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# Serverweite Fehlversuch-Zaehler (Audit SEC-02)
# Modul-Globals ueberleben in Streamlit alle Sitzungen eines Server-Prozesses.
# ---------------------------------------------------------------------------
_FEHL_LOCK = threading.Lock()
_FEHL = {}        # schluessel -> {"zeiten": [t, ...], "bis": t, "stufe": n}


def _uhr():
    return time.monotonic()


def _bremse():
    time.sleep(1.0)                  # bremst Durchprobieren zusaetzlich


def _schluessel(name, ip=None):
    k = [f"u:{_norm(name)}"]
    if ip:
        k.append(f"ip:{ip}")
    return k


def _grenze(schluessel):
    return MAX_FEHLVERSUCHE_IP if schluessel.startswith("ip:") else MAX_FEHLVERSUCHE


def sperre_rest(schluessel, jetzt=None):
    """-> verbleibende Sperrzeit in Sekunden (0 = frei) ueber alle Schluessel."""
    jetzt = _uhr() if jetzt is None else jetzt
    with _FEHL_LOCK:
        rest = 0.0
        for k in schluessel:
            e = _FEHL.get(k)
            if e and e.get("bis", 0) > jetzt:
                rest = max(rest, e["bis"] - jetzt)
        return rest


def _aufraeumen(jetzt):
    if len(_FEHL) <= _MAX_ZAEHLER:
        return
    for k in list(_FEHL):
        e = _FEHL[k]
        if e.get("bis", 0) <= jetzt and not [t for t in e["zeiten"] if jetzt - t < FENSTER_SEK]:
            del _FEHL[k]
    if len(_FEHL) > _MAX_ZAEHLER:          # Flut zufaelliger Namen: nur aktive Sperren behalten
        for k in list(_FEHL):
            if _FEHL[k].get("bis", 0) <= jetzt:
                del _FEHL[k]


def fehlversuch_merken(schluessel, jetzt=None):
    """Fehlversuch zaehlen (gleitendes 15-Minuten-Fenster). -> Sperrzeit in Sekunden (0 = keine)."""
    jetzt = _uhr() if jetzt is None else jetzt
    with _FEHL_LOCK:
        _aufraeumen(jetzt)
        for k in schluessel:
            e = _FEHL.setdefault(k, {"zeiten": [], "bis": 0.0, "stufe": 0})
            if e["stufe"] and jetzt - e["bis"] > FENSTER_SEK:
                e["stufe"] = 0                       # lange ruhig -> Backoff zuruecksetzen
            e["zeiten"] = [t for t in e["zeiten"] if jetzt - t < FENSTER_SEK] + [jetzt]
            if len(e["zeiten"]) >= _grenze(k):
                e["stufe"] += 1
                e["bis"] = jetzt + min(SPERRE_SEK * 2 ** (e["stufe"] - 1), SPERRE_MAX_SEK)
                e["zeiten"] = []
    return sperre_rest(schluessel, jetzt)


def erfolg_merken(name):
    """Erfolgreiche Anmeldung: Zaehler des Benutzernamens zuruecksetzen (der IP-Zaehler bleibt)."""
    with _FEHL_LOCK:
        _FEHL.pop(_schluessel(name)[0], None)


def _zaehler_leeren():
    """Nur fuer Tests."""
    with _FEHL_LOCK:
        _FEHL.clear()


def _client_ip(st):
    """Erste Adresse aus X-Forwarded-For (vom Client faelschbar - daher nur als
    Zusatz zum Benutzernamen-Zaehler, nie als alleiniger Schutz)."""
    try:
        h = st.context.headers
        v = h.get("X-Forwarded-For") or h.get("x-forwarded-for") or ""
        ip = str(v).split(",")[0].strip()[:64]
        return ip or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Konfiguration + Speicher
# ---------------------------------------------------------------------------
def _secrets_quelle(st):
    """Sucht admin_benutzer in [login], ganz oben oder in irgendeinem Abschnitt der Secrets
    (haeufiger Fehler: Zeilen ohne [login] unter einen anderen Abschnitt angehaengt)."""
    try:
        alle = st.secrets
        if "login" in alle and alle["login"].get("admin_benutzer"):
            return alle["login"], "[login]"
        if alle.get("admin_benutzer"):
            return alle, "oberste Ebene"
        for k in list(alle.keys()):
            try:
                v = alle[k]
                if hasattr(v, "get") and v.get("admin_benutzer"):
                    return v, f"[{k}]"
            except Exception:
                continue
    except Exception:
        pass
    return None, None


def _wahr(v):
    return v is True or (isinstance(v, (str, int)) and not isinstance(v, bool)
                         and str(v).strip().lower() in ("true", "1", "ja", "yes"))


def login_deaktiviert(st):
    """Nur ein ausdrueckliches login_deaktiviert = true (oben oder in [login]) schaltet den Login ab."""
    try:
        s = st.secrets
        if _wahr(s.get("login_deaktiviert")):
            return True
        if "login" in s:
            ab = s["login"]
            if hasattr(ab, "get") and _wahr(ab.get("login_deaktiviert")):
                return True
    except Exception:
        pass
    return False


def konfig(st):
    """-> {"admin", "admin_pw", "admin_pw_hash": bool} oder None (keine/unvollstaendige Konfiguration)."""
    s, _ = _secrets_quelle(st)
    if not s:
        return None
    name = _norm(s.get("admin_benutzer"))
    pw = s.get("admin_passwort_hash") or s.get("admin_passwort")
    if not name or not pw:
        return None
    return {"admin": name, "admin_pw": str(pw), "admin_pw_hash": ist_hash(str(pw))}


def diagnose(st):
    """Kurzer Status ohne Werte und ohne Schluesselnamen (wird ggf. vor dem Login angezeigt)."""
    if konfig(st) is not None:
        return "Login aktiv."
    if login_deaktiviert(st):
        return "Login ausdrücklich deaktiviert."
    return "Login-Konfiguration fehlt oder ist unvollständig – App gesperrt (Details: Kopfkommentar von login.py)."


def lade(gh_read):
    daten = gh_read(PFAD_BENUTZER, {}) or {}
    return daten if isinstance(daten, dict) else {}


def speichere(gh_write, daten, nachricht):
    return gh_write(PFAD_BENUTZER, daten, message=f"benutzer: {nachricht} [skip ci]")


def benutzer_aendern(aendern, nachricht, gh_aktualisiere=None, gh_read=None, gh_write=None):
    """Lesen-Aendern-Schreiben von benutzer.json (Audit DATA-02/DATA-04).
    aendern(daten) -> geaenderte daten oder None (= nichts schreiben); wird mit frisch
    gelesenen Daten aufgerufen (bei Konflikt ggf. mehrfach). Mit gh_aktualisiere:
    Versionspruefung, nie Schreiben nach Lesefehler. Ohne: alter Weg (gh_read + gh_write;
    github_store blockiert dann Schreiben nach einem Lesefehler).
    -> True wenn gespeichert (oder nichts zu speichern war), False bei Fehler."""
    msg = f"benutzer: {nachricht} [skip ci]"

    def _a(d):
        d = d if isinstance(d, dict) else {}
        if not isinstance(d.get("benutzer"), dict):
            d["benutzer"] = {}
        return aendern(d)

    try:
        if gh_aktualisiere is not None:
            ok, _ = gh_aktualisiere(PFAD_BENUTZER, _a, default={}, message=msg)
            return bool(ok)
        neu = _a(lade(gh_read))
        if neu is None:
            return True
        return bool(gh_write(PFAD_BENUTZER, neu, message=msg))
    except Exception as e:
        logging.error(f"login.benutzer_aendern ({nachricht}): {type(e).__name__}")
        return False


def _nutzer(cfg, daten, name):
    """Benutzer-dict (inkl. Admin) oder None."""
    name = _norm(name)
    if name == cfg["admin"]:
        return {"name": name, "rolle": "admin", "ansichten": None, "aktiv": True}
    u = (daten.get("benutzer") or {}).get(name)
    if not u or not u.get("aktiv", True):
        return None
    return {"name": name, "rolle": "benutzer", "ansichten": u.get("ansichten"), "aktiv": True,
            "anzeige": u.get("anzeige") or name}


# Sitzungen (Audit A-13): eine Anmeldung gilt nur, solange das Passwort unveraendert ist,
# und hoechstens MAX_SITZUNG_SEK lang.
MAX_SITZUNG_SEK = 12 * 3600


def pw_kennung(cfg, daten, name):
    """Kurzer Fingerabdruck des gespeicherten Passworts (Hash bzw. Admin-Secret) - aendert
    sich bei jedem Passwortwechsel. None, wenn der Benutzer nicht (mehr) existiert."""
    n = _norm(name)
    if n == cfg["admin"]:
        roh = cfg["admin_pw"]
    else:
        alle = daten.get("benutzer") if isinstance(daten.get("benutzer"), dict) else {}
        u = alle.get(n)
        roh = u.get("hash") if isinstance(u, dict) else None
    return hashlib.sha256(str(roh).encode("utf-8")).hexdigest()[:16] if roh else None


def sitzung_gueltig(ss, cfg, daten, name, jetzt=None):
    """Passwort seit der Anmeldung unveraendert und Sitzung nicht aelter als MAX_SITZUNG_SEK?"""
    jetzt = time.time() if jetzt is None else jetzt
    kennung = pw_kennung(cfg, daten, name)
    seit = ss.get("login_seit")
    return (kennung is not None and ss.get("login_pw") == kennung
            and isinstance(seit, (int, float)) and 0 <= jetzt - seit <= MAX_SITZUNG_SEK)


def _sitzung_beenden(ss):
    for k in ("login_name", "login_pw", "login_seit", "_nutzer"):
        ss.pop(k, None)


def pruefe_anmeldung(cfg, daten, name, passwort):
    """Passwortpruefung mit immer genau einer PBKDF2-Berechnung (Audit SEC-07). -> bool"""
    n = _norm(name)
    pw = passwort or ""
    if n == cfg["admin"]:
        gesp = cfg["admin_pw"]
        if ist_hash(gesp):
            return passwort_ok(pw, gesp)
        _dummy_pruefen(pw)                               # Klartext-Admin: gleiche Laufzeit
        return passwort_ok(pw, gesp)
    u = (daten.get("benutzer") or {}).get(n) if isinstance(daten.get("benutzer"), dict) else None
    if isinstance(u, dict) and u.get("aktiv", True) and ist_hash(u.get("hash")):
        return passwort_ok(pw, u["hash"])
    return _dummy_pruefen(pw)                            # unbekannt/gesperrt: gleiche Laufzeit


# ---------------------------------------------------------------------------
# Anmeldung
# ---------------------------------------------------------------------------
LOGIN_CSS = """<style>
.st-key-login_box { max-width: 420px; margin: 8vh auto 0; padding: 22px 20px; border-radius: 18px;
                    background: #12151c; border: 1px solid #2c313d; }
.login-titel { font-size: 1.4rem; font-weight: 800; color: #fff; margin-bottom: 2px; }
.login-text { font-size: .85rem; color: #a9a79c; margin-bottom: 14px; }
/* Beschriftung ueber den Feldern */
.st-key-login_box [data-testid="stTextInput"] label p {
    font-size: .95rem !important; font-weight: 700 !important; color: #e8e6df !important; }
/* Eingabefelder: heller Kasten mit deutlichem Rahmen */
.st-key-login_box [data-testid="stTextInput"] [data-baseweb="input"] {
    background: #222836 !important; border: 2px solid #4a5468 !important;
    border-radius: 12px !important; min-height: 52px; transition: border-color .15s, box-shadow .15s; }
.st-key-login_box [data-testid="stTextInput"] [data-baseweb="input"] > div,
.st-key-login_box [data-testid="stTextInput"] [data-baseweb="base-input"] {
    background: transparent !important; }
.st-key-login_box [data-testid="stTextInput"] input {
    background: transparent !important; color: #ffffff !important;
    font-size: 16px !important; padding: 12px 14px !important; caret-color: #3987e5; }
.st-key-login_box [data-testid="stTextInput"] input::placeholder { color: #8a90a0 !important; opacity: 1; }
/* aktives Feld: blauer Rahmen + Leuchten */
.st-key-login_box [data-testid="stTextInput"] [data-baseweb="input"]:focus-within {
    border-color: #3987e5 !important; box-shadow: 0 0 0 3px rgba(57,135,229,.35) !important; }
.st-key-login_box [data-testid="stTextInput"] button { background: transparent !important; color: #c9ccd4 !important; }
.st-key-login_box [data-testid="InputInstructions"] { display: none; }
/* Anmelden-Knopf: farbig und gross */
.st-key-login_box [data-testid="stFormSubmitButton"] button {
    background: #2563EB !important; border: none !important; color: #fff !important;
    min-height: 52px; border-radius: 12px !important; margin-top: 6px; }
.st-key-login_box [data-testid="stFormSubmitButton"] button p { font-size: 1.05rem !important; font-weight: 700 !important; }
.st-key-login_box [data-testid="stFormSubmitButton"] button:active { background: #1D4ED8 !important; }
</style>"""


def _fehlerseite(st):
    """Fail-closed (Audit SEC-03): keine Schluesselnamen, keine Werte."""
    st.error("🔒 Die Anmeldung ist nicht eingerichtet – die App bleibt aus Sicherheitsgründen gesperrt.")
    st.info("Hinweis für den Betreiber: Login-Konfiguration in den Streamlit-Secrets prüfen "
            "(Anleitung im Kopfkommentar von login.py).")
    st.stop()


def _neu_starten(st):
    try:
        st.rerun(scope="app")
    except TypeError:
        st.rerun()


def _zuletzt_merken(n, gh_read, gh_write, gh_aktualisiere):
    """Datum der letzten Anmeldung speichern (hoechstens 1x pro Tag), ohne fremde
    Aenderungen (z. B. eine gerade gesetzte Sperre) zu ueberschreiben.
    -> (noch_aktiv, erster_login_heute)"""
    heute = _heute()
    status = {"aktiv": True, "neu": False}

    def aendern(d):
        u = d["benutzer"].get(n)
        if not isinstance(u, dict) or not u.get("aktiv", True):
            status["aktiv"] = False                      # inzwischen gesperrt/geloescht
            return None
        status["aktiv"] = True
        if u.get("zuletzt") == heute:
            status["neu"] = False
            return None
        status["neu"] = True
        u["zuletzt"] = heute
        return d

    if not benutzer_aendern(aendern, f"login {n}", gh_aktualisiere, gh_read, gh_write):
        logging.warning(f"login: Anmeldedatum fuer {n} nicht gespeichert")
    return status["aktiv"], status["neu"]


def _chronik_login(chronik, n):
    schluessel = f"login-{n}-{_heute().replace('-', '')}"
    try:
        chronik("zugang", f"🔐 Anmeldung: {n}", schluessel=schluessel)
    except TypeError:
        try:
            chronik("zugang", f"🔐 Anmeldung: {n}")
        except Exception:
            pass
    except Exception:
        pass


def gate(st, gh_read, gh_read_cached, gh_write, chronik=None, gh_aktualisiere=None, speicher_fehler=None):
    """Vor dem Dashboard aufrufen. -> Benutzer-dict, None (Login ausdruecklich deaktiviert)
    oder st.stop(). gh_aktualisiere (optional): app.gh_aktualisiere fuer sicheres Schreiben.
    speicher_fehler (optional): Funktion -> True, wenn die Benutzerliste gerade nicht lesbar
    war (Audit A-10: dann ehrliche Meldung statt "Passwort falsch")."""
    cfg = konfig(st)
    if cfg is None:
        if login_deaktiviert(st):
            return None
        _fehlerseite(st)
        return None                                       # nur falls st.stop() nicht wirft
    ss = st.session_state
    angemeldet = ss.get("login_name")
    if angemeldet:
        # bei jedem Seitenaufbau pruefen: Benutzer noch aktiv, Passwort unveraendert, Sitzung
        # nicht zu alt (Audit A-13)
        daten = lade(gh_read_cached)
        u = _nutzer(cfg, daten, angemeldet)
        if u and sitzung_gueltig(ss, cfg, daten, angemeldet):
            return u
        _sitzung_beenden(ss)
        st.warning("Deine Sitzung ist abgelaufen oder dein Zugang wurde geändert – bitte neu anmelden.")

    ip = _client_ip(st)
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)
    with st.container(key="login_box"):
        st.markdown('<div class="login-titel">🔐 Anmelden</div>'
                    '<div class="login-text">Finanz Dashboard · bitte Benutzername und Passwort eingeben</div>',
                    unsafe_allow_html=True)
        if ip:
            rest = sperre_rest([f"ip:{ip}"])
            if rest > 0:
                st.error(f"Zu viele Fehlversuche – bitte {int(rest) + 1} Sekunden warten.")
                st.stop()
        with st.form("login_form", border=False):
            name = st.text_input("👤 Benutzername", autocomplete="username",
                                 placeholder="Benutzername eingeben")
            pw = st.text_input("🔑 Passwort", type="password", autocomplete="current-password",
                               placeholder="Passwort eingeben")
            los = st.form_submit_button("Anmelden", width="stretch")
        if los:
            n = _norm(name)
            schluessel = _schluessel(n, ip)
            rest = sperre_rest(schluessel)
            if rest > 0:
                _dummy_pruefen(pw)                        # gleiche Laufzeit, kein Passworttest
                st.error(f"Zu viele Fehlversuche – bitte {int(rest) + 1} Sekunden warten.")
                st.stop()
            daten = lade(gh_read_cached)                  # gecacht (Audit SEC-02, Rate-Limit)
            if pruefe_anmeldung(cfg, daten, n, pw):
                erst_heute = False
                if n != cfg["admin"]:
                    aktiv, erst_heute = _zuletzt_merken(n, gh_read, gh_write, gh_aktualisiere)
                    if not aktiv:                         # zwischenzeitlich gesperrt
                        st.error("Benutzername oder Passwort falsch.")
                        st.stop()
                ss["login_name"] = n
                ss["login_pw"] = pw_kennung(cfg, daten, n)
                ss["login_seit"] = time.time()
                erfolg_merken(n)
                if chronik and erst_heute:
                    _chronik_login(chronik, n)
                st.rerun()
                return None
            if speicher_fehler is not None and speicher_fehler() and n != cfg["admin"]:
                # Benutzerliste nicht lesbar: kein Fehlversuch, ehrliche Meldung
                st.error("Anmeldung gerade nicht möglich – der Datenspeicher ist nicht erreichbar. "
                         "Bitte in ein paar Minuten erneut versuchen.")
                st.stop()
            _bremse()
            rest = fehlversuch_merken(schluessel)
            if rest > 0:
                st.error(f"Zu viele Fehlversuche – bitte {int(rest) + 1} Sekunden warten.")
            else:
                st.error("Benutzername oder Passwort falsch.")
    st.stop()


def pruefen(st, gh_read_cached):
    """Waehrend der Sitzung - auch aus inneren Fragmenten aufrufbar (Audit SEC-10):
    Benutzer noch aktiv? -> aktueller Benutzer (mit frischen Rechten).
    Sonst abmelden und die ganze Seite neu aufbauen (Anmeldemaske / Fehlerseite)."""
    cfg = konfig(st)
    name = st.session_state.get("login_name")
    if cfg is None:
        if login_deaktiviert(st):
            return None
        # Konfiguration waehrend der Sitzung verschwunden -> fail-closed
        st.session_state.pop("login_name", None)
        st.session_state.pop("_nutzer", None)
        _neu_starten(st)
        return None
    # nicht (mehr) angemeldet, aber ein Teil der App zeichnet sich neu (Fragment) ->
    # ganze App neu starten, damit die Anmeldemaske erscheint
    daten = lade(gh_read_cached) if name else {}
    u = _nutzer(cfg, daten, name) if name else None
    if u is not None and not sitzung_gueltig(st.session_state, cfg, daten, name):
        u = None
    if u is not None:
        # frische Rechte uebernehmen - sonst gelten geaenderte Ansichten erst nach einem
        # kompletten Neuaufbau (das Menue zeichnet sich als Fragment meist nur teilweise neu)
        st.session_state["_nutzer"] = u
        return u
    _sitzung_beenden(st.session_state)
    _neu_starten(st)
    return None


def abmelden(st):
    for k in list(st.session_state.keys()):
        if k != "login_sperre_bis":
            st.session_state.pop(k, None)


def darf(nutzer, ansicht):
    """Darf der Benutzer die Ansicht sehen? (None = Login aus -> alles erlaubt)"""
    if nutzer is None or nutzer["rolle"] == "admin":
        return True
    erlaubt = nutzer.get("ansichten")
    return erlaubt is None or ansicht in erlaubt


# ---------------------------------------------------------------------------
# Benutzerverwaltung (nur Admin)
# ---------------------------------------------------------------------------
RECHTE_CSS = """<style>
.st-key-rechte_box [data-testid="stCheckbox"], [class*="st-key-rechte_"] [data-testid="stCheckbox"] {
    padding: 6px 10px; margin-bottom: 6px; border-radius: 10px;
    background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.14); }
[class*="st-key-rechte_"] [data-testid="stCheckbox"] label p { font-size: .9rem !important; color: #e8e6df !important; }
.rechte-info { font-size: .8rem; color: #a9a79c; margin: 2px 0 8px; }
[class*="st-key-rspeichern_"] button {
    background: #16C784 !important; border: none !important; min-height: 46px; border-radius: 12px !important;
    box-shadow: 0 0 10px rgba(22,199,132,.35) !important; }
[class*="st-key-rspeichern_"] button p { color: #0a0b0d !important; font-weight: 700 !important; font-size: 1rem !important; }
</style>"""


def _schalter_key(prefix, a):
    return f"{prefix}__{a}"


def _rechte_schalter(st, prefix, ansichten, namen, erlaubt, on_change=None, args=()):
    """Je Ansicht ein Schalter (2 Spalten). -> Liste der eingeschalteten Ansichten."""
    cols = st.columns(2)
    for i, a in enumerate(ansichten):
        k = _schalter_key(prefix, a)
        if k not in st.session_state:
            st.session_state[k] = a in erlaubt
        kw = {"on_change": on_change, "args": args} if on_change else {}
        cols[i % 2].toggle(namen.get(a, a), key=k, **kw)
    return [a for a in ansichten if st.session_state.get(_schalter_key(prefix, a))]


def _admin_pw_hinweis(st, cfg):
    """Audit SEC-06: Klartext-Admin-Passwort -> Warnung mit Anleitung."""
    if cfg.get("admin_pw_hash"):
        return
    kurz = len(cfg.get("admin_pw") or "") < ADMIN_MIN_LAENGE
    st.warning("⚠️ Das Admin-Passwort steht im **Klartext** in den Secrets"
               + (f" und ist kürzer als {ADMIN_MIN_LAENGE} Zeichen" if kurz else "")
               + ". Empfohlen: nur den Hash als `admin_passwort_hash` hinterlegen und "
                 "`admin_passwort` entfernen. Hash lokal erzeugen (im Projektordner):")
    st.code(HASH_HINWEIS, language="bash")


def render_verwaltung(st, gh_read, gh_write, ansichten, namen, gh_aktualisiere=None, daten_loeschen=None):
    """ansichten: Liste der waehlbaren Ansichten (Schluessel), namen: {schluessel: Anzeigename}.
    gh_aktualisiere (optional): app.gh_aktualisiere - alle Aenderungen dann als sicheres
    Lesen-Aendern-Schreiben mit Versionspruefung (Audit DATA-02).
    daten_loeschen (optional): Funktion(name) -> (ok, anzahl) - loescht beim Loeschen eines
    Benutzers auch alle seine gespeicherten Daten (Depot, Planer, Rechner, Chronik)."""
    cfg = konfig(st)
    if cfg is None:
        st.warning("Login ist **nicht aktiv** – " + diagnose(st))
        return
    st.markdown(RECHTE_CSS, unsafe_allow_html=True)
    _admin_pw_hinweis(st, cfg)
    meldung = st.session_state.pop("rechte_meldung", None)
    if meldung:
        st.toast(meldung)
    daten = lade(gh_read)
    benutzer = daten.get("benutzer") if isinstance(daten.get("benutzer"), dict) else {}
    st.caption(f"Admin: **{cfg['admin']}** (aus den Secrets – sieht immer alles). Gesperrte oder gelöschte "
               "Benutzer fliegen beim nächsten Klick raus.")

    def _aendern(fn, nachricht):
        return benutzer_aendern(fn, nachricht, gh_aktualisiere, gh_read, gh_write)

    def _alle_setzen(nn, liste):
        """Callback der Schnellknoepfe: nur die Schalter umstellen - gespeichert wird erst per Knopf."""
        for a in ansichten:
            st.session_state[_schalter_key(f"rechte_{nn}", a)] = a in liste

    def _rechte_speichern(nn):
        auswahl = [a for a in ansichten if st.session_state.get(_schalter_key(f"rechte_{nn}", a))]
        status = {"da": True}

        def fn(d):
            u = d["benutzer"].get(nn)
            if not isinstance(u, dict):
                status["da"] = False
                return None
            u["ansichten"] = auswahl
            return d

        if not _aendern(fn, f"rechte {nn}"):
            st.error(SPEICHERFEHLER)
            return False
        if not status["da"]:
            st.error(f"„{nn}“ existiert nicht mehr.")
            return False
        st.session_state["rechte_meldung"] = f"✅ Rechte von „{nn}“ gespeichert ({len(auswahl)}/{len(ansichten)})"
        return True

    with st.expander("➕ Neuen Benutzer anlegen", expanded=not benutzer):
        with st.form("neu_benutzer", clear_on_submit=True):
            c1, c2 = st.columns(2)
            n = c1.text_input("Benutzername")
            pw = c2.text_input(f"Passwort (min. {MIN_LAENGE} Zeichen)", type="password")
            st.markdown('<div class="rechte-info">Darf sehen (später jederzeit änderbar):</div>',
                        unsafe_allow_html=True)
            with st.container(key="rechte_neu"):
                cols = st.columns(2)
                wahl = {a: cols[i % 2].toggle(namen.get(a, a), value=True, key=f"neu_sicht_{i}")
                        for i, a in enumerate(ansichten)}
            if st.form_submit_button("Anlegen", width="stretch"):
                sicht = [a for a, an in wahl.items() if an]
                nn = _norm(n)
                fehler = passwort_pruefen(pw, nn)
                name_fehler = nutzerdaten.name_pruefen(nn, benutzer, (cfg["admin"],))
                if name_fehler:
                    st.error(name_fehler)
                elif fehler:
                    st.error(fehler)
                else:
                    eintrag = {"hash": passwort_hash(pw), "aktiv": True, "ansichten": sicht,
                               "angelegt": _heute()}
                    status = {"existiert": False}

                    def fn(d):
                        # frisch gelesen erneut pruefen (paralleles Anlegen, Audit A-03)
                        if nutzerdaten.name_pruefen(nn, d["benutzer"], (cfg["admin"],)):
                            status["existiert"] = True
                            return None
                        status["existiert"] = False
                        d["benutzer"][nn] = dict(eintrag)
                        return d

                    if not _aendern(fn, f"neu {nn}"):
                        st.error(SPEICHERFEHLER)
                    elif status["existiert"]:
                        st.error(f"„{nn}“ existiert schon.")
                    else:
                        st.session_state["rechte_meldung"] = f"✅ „{nn}“ angelegt."
                        st.rerun()

    if not benutzer:
        st.caption("Noch keine weiteren Benutzer.")
        return
    for ordner_, namen_ in nutzerdaten.slug_kollisionen(benutzer).items():
        st.error(f"⚠️ Diese Benutzer teilen sich einen Datenordner ({ordner_}) und sehen gegenseitig ihre "
                 f"Daten: {', '.join(namen_)}. Bitte alle bis auf einen löschen und neu anlegen.")
    for nn in sorted(benutzer):
        u = benutzer[nn] if isinstance(benutzer[nn], dict) else {}
        aktiv = u.get("aktiv", True)
        erlaubt = [a for a in (u.get("ansichten") if u.get("ansichten") is not None else ansichten) if a in ansichten]
        titel = (f"{'🟢' if aktiv else '⛔'} {nn} · {len(erlaubt)}/{len(ansichten)} Ansichten"
                 + (f" · zuletzt {str(u['zuletzt'])[:10]}" if u.get("zuletzt") else ""))
        with st.expander(titel):
            st.markdown('<div class="rechte-info">👁️ <b>Darf sehen</b> – Schalter einstellen und dann '
                        '<b>💾 Rechte speichern</b> tippen:</div>', unsafe_allow_html=True)
            q1, q2 = st.columns(2)
            q1.button("✅ Alle an", key=f"bv_alle_{nn}", width="stretch",
                      on_click=_alle_setzen, args=(nn, list(ansichten)))
            q2.button("⬜ Alle aus", key=f"bv_keine_{nn}", width="stretch",
                      on_click=_alle_setzen, args=(nn, []))
            # im Formular loesen die Schalter keinen Neuaufbau aus - erst der Speichern-Knopf
            with st.form(f"rechte_form_{nn}", border=False):
                with st.container(key=f"rechte_{nn}"):
                    _rechte_schalter(st, f"rechte_{nn}", ansichten, namen, erlaubt)
                with st.container(key=f"rspeichern_{nn}"):
                    gedrueckt = st.form_submit_button("💾 Rechte speichern", width="stretch")
                if gedrueckt and _rechte_speichern(nn):
                    st.rerun()
            st.divider()
            c2, c4 = st.columns(2)
            if c2.button("⛔ Sperren" if aktiv else "✅ Freischalten", key=f"bv_akt_{nn}", width="stretch"):
                ziel = not aktiv

                def fn(d, nn=nn, ziel=ziel):
                    x = d["benutzer"].get(nn)
                    if not isinstance(x, dict) or x.get("aktiv", True) == ziel:
                        return None
                    x["aktiv"] = ziel
                    return d

                if _aendern(fn, f"{'frei' if ziel else 'sperre'} {nn}"):
                    st.session_state["rechte_meldung"] = f"✅ „{nn}“ {'freigeschaltet' if ziel else 'gesperrt'}."
                    st.rerun()
                else:
                    st.error(SPEICHERFEHLER)
            if c4.button("🗑️ Löschen", key=f"bv_del_{nn}", width="stretch"):
                st.session_state[f"bv_del_frage_{nn}"] = True
            if st.session_state.get(f"bv_del_frage_{nn}"):
                st.warning(f"**„{nn}“ wirklich löschen?** Der Zugang und **alle seine Daten** (Depot, "
                           "Beobachtungsliste, Planer, Rechner-Eingaben, Chronik) werden unwiderruflich gelöscht.")
                j1, j2 = st.columns(2)
                if j2.button("Abbrechen", key=f"bv_del_nein_{nn}", width="stretch"):
                    st.session_state.pop(f"bv_del_frage_{nn}", None)
                    st.rerun()
                if j1.button("🗑️ Endgültig löschen", key=f"bv_del_ja_{nn}", width="stretch", type="primary"):
                    def fn(d, nn=nn):
                        if nn not in d["benutzer"]:
                            return None
                        d["benutzer"].pop(nn, None)
                        return d

                    if _aendern(fn, f"loeschen {nn}"):
                        for a in ansichten:
                            st.session_state.pop(_schalter_key(f"rechte_{nn}", a), None)
                        st.session_state.pop(f"bv_del_frage_{nn}", None)
                        meldung = f"✅ „{nn}“ gelöscht."
                        if daten_loeschen is not None:
                            try:
                                ok, anzahl = daten_loeschen(nn)
                            except Exception:
                                ok, anzahl = False, 0
                            meldung += (f" {anzahl} Datei(en) mit seinen Daten entfernt." if ok else
                                        " ⚠️ Seine Daten konnten nicht vollständig gelöscht werden – "
                                        "bitte später erneut einen Benutzer gleichen Namens anlegen und löschen.")
                        st.session_state["rechte_meldung"] = meldung
                        st.rerun()
                    else:
                        st.error(SPEICHERFEHLER)
            neu_pw = st.text_input("🔑 Neues Passwort", type="password", key=f"bv_pw_{nn}",
                                   placeholder=f"mind. {MIN_LAENGE} Zeichen")
            if st.button("Passwort setzen", key=f"bv_pwb_{nn}", width="stretch"):
                fehler = passwort_pruefen(neu_pw, nn)
                if fehler:
                    st.error(fehler)
                else:
                    h = passwort_hash(neu_pw)
                    status = {"da": True}

                    def fn(d, nn=nn, h=h, status=status):
                        x = d["benutzer"].get(nn)
                        if not isinstance(x, dict):
                            status["da"] = False
                            return None
                        x["hash"] = h
                        return d

                    if not _aendern(fn, f"passwort {nn}"):
                        st.error(SPEICHERFEHLER)
                    elif not status["da"]:
                        st.error(f"„{nn}“ existiert nicht mehr.")
                    else:
                        st.success("Passwort geändert.")
