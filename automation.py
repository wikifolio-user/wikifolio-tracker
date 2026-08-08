import datetime
import hashlib
import json
import os
import sys
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests
import yfinance as yf

SENDER_EMAIL = os.environ.get("EMAIL_USER")
SENDER_PASSWORD = os.environ.get("EMAIL_PASS")
RECEIVER_EMAIL = os.environ.get("EMAIL_USER")

WIKIFOLIO_URL = "https://www.wikifolio.com/de/de/w/de000ls9vfs2"
STATE_FILE = "last_state.json"


def send_mail(subject, html_body):
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)


def check_trades():
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(WIKIFOLIO_URL, headers=headers)
    curr_hash = hashlib.md5(res.text.encode("utf-8")).hexdigest()

    last_hash = None
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            last_hash = json.load(f).get("hash")

    if last_hash and curr_hash != last_hash:
        send_mail(
            "🚨 Wikifolio Trade Alert!",
            "<p>Ein neuer Trade oder eine Orderänderung wurde auf Wikifolio registriert.</p>",
        )

    with open(STATE_FILE, "w") as f:
        json.dump({"hash": curr_hash}, f)


def send_daily_report():
    data = yf.Ticker("LS9VFS.SG").history(period="1d")
    if not data.empty:
        price = float(data["Close"].iloc[-1])
        perf = ((price - 160.68) / 160.68) * 100
        send_mail(
            f"📊 Tagesupdate Wikifolio: {price:.2f} € ({perf:+.2f}%)",
            f"""
            <h3>Tagesauswertung Wikifolio</h3>
            <ul>
                <li><b>Einstieg (07.08.2025):</b> 160,68 €</li>
                <li><b>Aktueller Kurs:</b> {price:.2f} €</li>
                <li><b>Performance seit Kauf:</b> {perf:+.2f} %</li>
            </ul>
        """,
        )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "trade"
    if mode == "trade":
        check_trades()
    elif mode == "daily":
        send_daily_report()
