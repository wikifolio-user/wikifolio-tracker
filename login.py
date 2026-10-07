"""Login mit Benutzername + Passwort und Benutzerverwaltung.

- Der Admin steht in den Streamlit-Secrets (kann sich nie selbst aussperren):
      [login]
      admin_benutzer = "marc"
      admin_passwort = "dein-sicheres-passwort"
- Weitere Benutzer legt der Admin in der App an (Menue -> 👥 Benutzer). Sie liegen in
  state/benutzer.json im GitHub-Speicher - Passwoerter nur als PBKDF2-Hash, nie im Klartext.
- Je Benutzer: welche Ansichten er sehen darf, aktiv/gesperrt, Passwort zuruecksetzen, loeschen.
  Gesperrte oder geloeschte Benutzer fliegen beim naechsten Seitenaufbau raus.
- Ohne [login] in den Secrets ist der Login aus (App verhaelt sich wie bisher).
"""
import datetime
import hashlib
import hmac
import secrets as _secrets
import time

PFAD_BENUTZER = "state/benutzer.json"
ITERATIONEN = 200_000
MAX_FEHLVERSUCHE = 5
SPERRE_SEK = 60


# ---------------------------------------------------------------------------
# Passwoerter
# ---------------------------------------------------------------------------
def passwort_hash(passwort, salz=None, iterationen=ITERATIONEN):
    salz = salz or _secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", passwort.encode("utf-8"), bytes.fromhex(salz), iterationen).hex()
    return f"pbkdf2_sha256${iterationen}${salz}${h}"


def passwort_ok(passwort, gespeichert):
    """Prueft gegen einen Hash (pbkdf2_sha256$...) oder - nur fuer den Admin in den Secrets - Klartext."""
    if not gespeichert or passwort is None:
        return False
    if gespeichert.startswith("pbkdf2_sha256$"):
        try:
            _, it, salz, soll = gespeichert.split("$")
            ist = passwort_hash(passwort, salz, int(it)).split("$")[3]
            return hmac.compare_digest(ist, soll)
        except Exception:
            return False
    return hmac.compare_digest(passwort.encode("utf-8"), str(gespeichert).encode("utf-8"))


def _norm(name):
    return str(name or "").strip().lower()


# ---------------------------------------------------------------------------
# Konfiguration + Speicher
# ---------------------------------------------------------------------------
def konfig(st):
    """-> {"admin": name, "admin_pw": hash/klartext} oder None (Login aus)."""
    try:
        s = st.secrets.get("login")
    except Exception:
        s = None
    if not s:
        return None
    name = _norm(s.get("admin_benutzer"))
    pw = s.get("admin_passwort_hash") or s.get("admin_passwort")
    if not name or not pw:
        return None
    return {"admin": name, "admin_pw": str(pw)}


def lade(gh_read):
    daten = gh_read(PFAD_BENUTZER, {}) or {}
    return daten if isinstance(daten, dict) else {}


def speichere(gh_write, daten, nachricht):
    return gh_write(PFAD_BENUTZER, daten, message=f"benutzer: {nachricht} [skip ci]")


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


# ---------------------------------------------------------------------------
# Anmeldung
# ---------------------------------------------------------------------------
LOGIN_CSS = """<style>
.st-key-login_box { max-width: 420px; margin: 8vh auto 0; padding: 22px 20px; border-radius: 18px;
                    background: #12151c; border: 1px solid #2c313d; }
.login-titel { font-size: 1.4rem; font-weight: 800; color: #fff; margin-bottom: 2px; }
.login-text { font-size: .85rem; color: #a9a79c; margin-bottom: 14px; }
</style>"""


def gate(st, gh_read, gh_read_cached, gh_write, chronik=None):
    """Vor dem Dashboard aufrufen. -> Benutzer-dict, None (Login nicht eingerichtet) oder st.stop()."""
    cfg = konfig(st)
    if cfg is None:
        return None
    ss = st.session_state
    angemeldet = ss.get("login_name")
    if angemeldet:
        # bei jedem Seitenaufbau pruefen, ob der Benutzer noch existiert und aktiv ist
        u = _nutzer(cfg, lade(gh_read_cached), angemeldet)
        if u:
            return u
        for k in ("login_name",):
            ss.pop(k, None)
        st.warning("Dein Zugang wurde beendet oder geändert – bitte neu anmelden.")

    st.markdown(LOGIN_CSS, unsafe_allow_html=True)
    with st.container(key="login_box"):
        st.markdown('<div class="login-titel">🔐 Anmelden</div>'
                    '<div class="login-text">Finanz Dashboard · bitte Benutzername und Passwort eingeben</div>',
                    unsafe_allow_html=True)
        gesperrt_bis = ss.get("login_sperre_bis", 0)
        if time.time() < gesperrt_bis:
            st.error(f"Zu viele Fehlversuche – bitte {int(gesperrt_bis - time.time()) + 1} Sekunden warten.")
            st.stop()
        with st.form("login_form", border=False):
            name = st.text_input("Benutzername", autocomplete="username")
            pw = st.text_input("Passwort", type="password", autocomplete="current-password")
            los = st.form_submit_button("Anmelden", width="stretch")
        if los:
            daten = lade(gh_read)
            n = _norm(name)
            ok = False
            if n == cfg["admin"]:
                ok = passwort_ok(pw, cfg["admin_pw"])
            else:
                u = (daten.get("benutzer") or {}).get(n)
                ok = bool(u and u.get("aktiv", True) and passwort_ok(pw, u.get("hash")))
            if ok:
                ss["login_name"] = n
                ss["login_fehler"] = 0
                if n != cfg["admin"]:
                    try:
                        daten.setdefault("benutzer", {})[n]["zuletzt"] = datetime.datetime.now().isoformat(
                            timespec="minutes")
                        speichere(gh_write, daten, f"login {n}")
                    except Exception:
                        pass
                    if chronik:
                        try:
                            chronik("zugang", f"🔐 Anmeldung: {n}")
                        except Exception:
                            pass
                st.rerun()
            time.sleep(1.0)                                   # bremst Durchprobieren
            ss["login_fehler"] = ss.get("login_fehler", 0) + 1
            if ss["login_fehler"] >= MAX_FEHLVERSUCHE:
                ss["login_sperre_bis"] = time.time() + SPERRE_SEK
                ss["login_fehler"] = 0
            st.error("Benutzername oder Passwort falsch.")
    st.stop()


def pruefen(st, gh_read_cached):
    """Waehrend der Sitzung: Benutzer noch aktiv? Sonst abmelden und die ganze Seite neu aufbauen."""
    cfg = konfig(st)
    name = st.session_state.get("login_name")
    if cfg is None or not name:
        return
    if _nutzer(cfg, lade(gh_read_cached), name) is None:
        st.session_state.pop("login_name", None)
        st.session_state.pop("_nutzer", None)
        try:
            st.rerun(scope="app")
        except TypeError:
            st.rerun()


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
def render_verwaltung(st, gh_read, gh_write, ansichten, namen):
    """ansichten: Liste der waehlbaren Ansichten (Schluessel), namen: {schluessel: Anzeigename}."""
    cfg = konfig(st)
    if cfg is None:
        st.info("Login ist nicht eingerichtet. In Streamlit unter Settings → Secrets eintragen:\n\n"
                "```toml\n[login]\nadmin_benutzer = \"dein-name\"\nadmin_passwort = \"dein-passwort\"\n```")
        return
    daten = lade(gh_read)
    benutzer = daten.setdefault("benutzer", {})
    st.caption(f"Admin: **{cfg['admin']}** (aus den Secrets – kann hier nicht gelöscht werden). Änderungen gelten "
               "sofort: gesperrte oder gelöschte Benutzer werden beim nächsten Klick abgemeldet.")

    with st.expander("➕ Neuen Benutzer anlegen", expanded=not benutzer):
        with st.form("neu_benutzer", clear_on_submit=True):
            c1, c2 = st.columns(2)
            n = c1.text_input("Benutzername")
            pw = c2.text_input("Passwort (min. 8 Zeichen)", type="password")
            sicht = st.multiselect("Darf sehen", ansichten, default=ansichten, format_func=lambda a: namen.get(a, a))
            if st.form_submit_button("Anlegen", width="stretch"):
                nn = _norm(n)
                if not nn or nn == cfg["admin"] or nn in benutzer:
                    st.error("Name fehlt, ist der Admin oder existiert schon.")
                elif len(pw or "") < 8:
                    st.error("Passwort zu kurz (mindestens 8 Zeichen).")
                else:
                    benutzer[nn] = {"hash": passwort_hash(pw), "aktiv": True, "ansichten": sicht,
                                    "angelegt": datetime.date.today().isoformat()}
                    if speichere(gh_write, daten, f"neu {nn}"):
                        st.success(f"„{nn}“ angelegt.")
                        st.rerun()
                    else:
                        st.error("Speichern nicht möglich (GitHub-Speicher).")

    if not benutzer:
        st.caption("Noch keine weiteren Benutzer.")
        return
    for nn in sorted(benutzer):
        u = benutzer[nn]
        aktiv = u.get("aktiv", True)
        titel = f"{'🟢' if aktiv else '⛔'} {nn}" + (f" · zuletzt {u['zuletzt'].replace('T', ' ')}" if u.get("zuletzt") else "")
        with st.expander(titel):
            sicht = st.multiselect("Darf sehen", ansichten, default=[a for a in (u.get("ansichten") or ansichten)
                                                                     if a in ansichten],
                                   format_func=lambda a: namen.get(a, a), key=f"bv_sicht_{nn}")
            c1, c2 = st.columns(2)
            if c1.button("💾 Rechte speichern", key=f"bv_save_{nn}", width="stretch"):
                u["ansichten"] = sicht
                speichere(gh_write, daten, f"rechte {nn}")
                st.success("Gespeichert.")
            if c2.button("⛔ Sperren" if aktiv else "✅ Freischalten", key=f"bv_akt_{nn}", width="stretch"):
                u["aktiv"] = not aktiv
                speichere(gh_write, daten, f"{'sperre' if aktiv else 'frei'} {nn}")
                st.rerun()
            neu_pw = st.text_input("Neues Passwort", type="password", key=f"bv_pw_{nn}")
            c3, c4 = st.columns(2)
            if c3.button("🔑 Passwort setzen", key=f"bv_pwb_{nn}", width="stretch"):
                if len(neu_pw or "") < 8:
                    st.error("Mindestens 8 Zeichen.")
                else:
                    u["hash"] = passwort_hash(neu_pw)
                    speichere(gh_write, daten, f"passwort {nn}")
                    st.success("Passwort geändert.")
            if c4.button("🗑️ Löschen", key=f"bv_del_{nn}", width="stretch"):
                benutzer.pop(nn, None)
                speichere(gh_write, daten, f"loeschen {nn}")
                st.rerun()
