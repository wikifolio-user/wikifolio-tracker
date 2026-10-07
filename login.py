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


def konfig(st):
    """-> {"admin": name, "admin_pw": hash/klartext} oder None (Login aus)."""
    s, _ = _secrets_quelle(st)
    if not s:
        return None
    name = _norm(s.get("admin_benutzer"))
    pw = s.get("admin_passwort_hash") or s.get("admin_passwort")
    if not name or not pw:
        return None
    return {"admin": name, "admin_pw": str(pw)}


def diagnose(st):
    """Kurzer Text, warum der Login (nicht) aktiv ist - ohne Werte zu verraten."""
    try:
        abschnitte = list(st.secrets.keys())
    except Exception:
        return "Keine Secrets gefunden (Settings → Secrets ist leer)."
    s, wo = _secrets_quelle(st)
    if not s:
        return ("In den Secrets fehlt „admin_benutzer“. Vorhandene Einträge/Abschnitte: "
                + (", ".join(abschnitte) or "keine") + ".")
    if not (s.get("admin_passwort") or s.get("admin_passwort_hash")):
        return f"„admin_benutzer“ gefunden ({wo}), aber „admin_passwort“ fehlt."
    return f"Login aktiv (gefunden unter {wo})."


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
    background: #3987e5 !important; border: none !important; color: #fff !important;
    min-height: 52px; border-radius: 12px !important; margin-top: 6px; }
.st-key-login_box [data-testid="stFormSubmitButton"] button p { font-size: 1.05rem !important; font-weight: 700 !important; }
.st-key-login_box [data-testid="stFormSubmitButton"] button:active { background: #2f72c4 !important; }
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
            name = st.text_input("👤 Benutzername", autocomplete="username",
                                 placeholder="Benutzername eingeben")
            pw = st.text_input("🔑 Passwort", type="password", autocomplete="current-password",
                               placeholder="Passwort eingeben")
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
RECHTE_CSS = """<style>
.st-key-rechte_box [data-testid="stCheckbox"], [class*="st-key-rechte_"] [data-testid="stCheckbox"] {
    padding: 6px 10px; margin-bottom: 6px; border-radius: 10px;
    background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.14); }
[class*="st-key-rechte_"] [data-testid="stCheckbox"] label p { font-size: .9rem !important; color: #e8e6df !important; }
.rechte-info { font-size: .8rem; color: #a9a79c; margin: 2px 0 8px; }
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


def render_verwaltung(st, gh_read, gh_write, ansichten, namen):
    """ansichten: Liste der waehlbaren Ansichten (Schluessel), namen: {schluessel: Anzeigename}."""
    cfg = konfig(st)
    if cfg is None:
        st.warning("Login ist **nicht aktiv** – die App ist für jeden mit dem Link offen.\n\n" + diagnose(st))
        st.info("In Streamlit unter Settings → Secrets ganz unten eintragen und speichern:\n\n"
                "```toml\n[login]\nadmin_benutzer = \"dein-name\"\nadmin_passwort = \"dein-passwort\"\n```")
        return
    st.markdown(RECHTE_CSS, unsafe_allow_html=True)
    daten = lade(gh_read)
    benutzer = daten.setdefault("benutzer", {})
    st.caption(f"Admin: **{cfg['admin']}** (aus den Secrets – sieht immer alles). Schalter wirken sofort und "
               "werden automatisch gespeichert; gesperrte oder gelöschte Benutzer fliegen beim nächsten Klick raus.")

    def _rechte_setzen(nn, liste=None):
        """Callback: aktuelle Schalterstellung (oder feste Liste) speichern."""
        prefix = f"rechte_{nn}"
        if liste is not None:
            for a in ansichten:
                st.session_state[_schalter_key(prefix, a)] = a in liste
        auswahl = [a for a in ansichten if st.session_state.get(_schalter_key(prefix, a))]
        d = lade(gh_read)
        if nn in d.get("benutzer", {}):
            d["benutzer"][nn]["ansichten"] = auswahl
            if speichere(gh_write, d, f"rechte {nn}"):
                st.toast(f"✅ Rechte von „{nn}“ gespeichert ({len(auswahl)}/{len(ansichten)})")
            else:
                st.toast("⚠️ Speichern nicht möglich (GitHub-Speicher)")

    with st.expander("➕ Neuen Benutzer anlegen", expanded=not benutzer):
        with st.form("neu_benutzer", clear_on_submit=True):
            c1, c2 = st.columns(2)
            n = c1.text_input("Benutzername")
            pw = c2.text_input("Passwort (min. 8 Zeichen)", type="password")
            st.markdown('<div class="rechte-info">Darf sehen (später jederzeit änderbar):</div>',
                        unsafe_allow_html=True)
            with st.container(key="rechte_neu"):
                cols = st.columns(2)
                wahl = {a: cols[i % 2].toggle(namen.get(a, a), value=True, key=f"neu_sicht_{i}")
                        for i, a in enumerate(ansichten)}
            if st.form_submit_button("Anlegen", width="stretch"):
                sicht = [a for a, an in wahl.items() if an]
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
        erlaubt = [a for a in (u.get("ansichten") if u.get("ansichten") is not None else ansichten) if a in ansichten]
        titel = (f"{'🟢' if aktiv else '⛔'} {nn} · {len(erlaubt)}/{len(ansichten)} Ansichten"
                 + (f" · zuletzt {u['zuletzt'][:16].replace('T', ' ')}" if u.get("zuletzt") else ""))
        with st.expander(titel):
            st.markdown('<div class="rechte-info">👁️ <b>Darf sehen</b> – antippen zum Ein-/Ausschalten, '
                        'wird sofort gespeichert:</div>', unsafe_allow_html=True)
            q1, q2 = st.columns(2)
            q1.button("✅ Alles erlauben", key=f"bv_alle_{nn}", width="stretch",
                      on_click=_rechte_setzen, args=(nn, list(ansichten)))
            q2.button("⬜ Nichts erlauben", key=f"bv_keine_{nn}", width="stretch",
                      on_click=_rechte_setzen, args=(nn, []))
            with st.container(key=f"rechte_{nn}"):
                _rechte_schalter(st, f"rechte_{nn}", ansichten, namen, erlaubt,
                                 on_change=_rechte_setzen, args=(nn,))
            st.divider()
            c2, c4 = st.columns(2)
            if c2.button("⛔ Sperren" if aktiv else "✅ Freischalten", key=f"bv_akt_{nn}", width="stretch"):
                u["aktiv"] = not aktiv
                speichere(gh_write, daten, f"{'sperre' if aktiv else 'frei'} {nn}")
                st.rerun()
            if c4.button("🗑️ Löschen", key=f"bv_del_{nn}", width="stretch"):
                benutzer.pop(nn, None)
                speichere(gh_write, daten, f"loeschen {nn}")
                for a in ansichten:
                    st.session_state.pop(_schalter_key(f"rechte_{nn}", a), None)
                st.rerun()
            neu_pw = st.text_input("🔑 Neues Passwort", type="password", key=f"bv_pw_{nn}",
                                   placeholder="mind. 8 Zeichen")
            if st.button("Passwort setzen", key=f"bv_pwb_{nn}", width="stretch"):
                if len(neu_pw or "") < 8:
                    st.error("Mindestens 8 Zeichen.")
                else:
                    u["hash"] = passwort_hash(neu_pw)
                    speichere(gh_write, daten, f"passwort {nn}")
                    st.success("Passwort geändert.")
