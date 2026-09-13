"""Temporary loopback-only first-owner setup, separate from the deployed API.

Run locally with `python -m app.owner_setup`. The owner enters their password
in their own browser; it is never printed, sent to chat, or written to a file.
This helper only creates the initial login. Reset requires manage_auth --reset.
"""
import asyncio
import json
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.config import get_settings
from app.db import dispose_engine
from app.manage_auth import provision_owner

ORIGIN = "http://127.0.0.1:8766"

PAGE = """<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>MoneySaver — יצירת התחברות פרטית</title>
<style>body{margin:0;min-height:100dvh;display:grid;place-items:center;background:#0b0e13;color:#f5f7fa;font:17px system-ui}
main{max-width:420px;padding:28px}h1{font-size:28px}p{line-height:1.7;color:#aeb7c4}form{display:grid;gap:12px}
input,button{box-sizing:border-box;font:inherit;border-radius:12px;padding:14px;width:100%}input{background:#151a22;border:1px solid #28303d;color:white;direction:ltr}button{background:#5b8def;border:0;cursor:pointer;font-weight:bold}#status{min-height:52px}</style>
<main><h1>החשבון הפרטי שלך</h1><p>בחר שם משתמש וסיסמה ל־MoneySaver. ההרשמה הזו פתוחה רק במחשב שלך. העסקאות הקיימות יישארו בחשבון.</p>
<form id="setup"><label for="username">שם משתמש</label><input id="username" name="username" autocomplete="username" minlength="3" maxlength="80" pattern="[A-Za-z0-9._@+\\-]{3,80}" required>
<label for="password">סיסמה או משפט סודי — לפחות 15 תווים</label><input id="password" name="password" type="password" autocomplete="new-password" minlength="15" maxlength="128" required>
<label for="confirm">אישור סיסמה</label><input id="confirm" name="confirm" type="password" autocomplete="new-password" minlength="15" maxlength="128" required>
<button id="submit">שמירת ההתחברות הפרטית</button></form><p id="status" role="status"></p></main>
<script nonce="NONCE">document.getElementById('setup').addEventListener('submit',async e=>{e.preventDefault();const status=document.getElementById('status'),button=document.getElementById('submit'),password=document.getElementById('password'),confirm=document.getElementById('confirm');if(password.value!==confirm.value){status.textContent='הסיסמאות אינן זהות.';return;}button.disabled=true;status.textContent='שומר…';try{const result=await fetch('/setup',{method:'POST',headers:{'Content-Type':'application/json','X-Setup-Nonce':'NONCE'},body:JSON.stringify({username:document.getElementById('username').value,password:password.value})});if(!result.ok)throw new Error();password.value='';confirm.value='';document.getElementById('setup').hidden=true;status.textContent='ההתחברות נשמרה. אפשר לסגור את הדף ולחזור ל־Codex.';}catch{status.textContent='ההגדרה לא הושלמה. בדוק ששם המשתמש תקין ושלא הוגדר כבר חשבון, ונסה שוב.';button.disabled=false;}});</script></html>"""


def main():
    if get_settings().production:
        raise SystemExit("First-owner setup runs only locally.")
    nonce = secrets.token_urlsafe(32)
    completed = False

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, data, content_type="text/plain; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data.encode("utf-8"))

        def do_GET(self):
            if self.headers.get("Host") != "127.0.0.1:8766" or self.path != "/":
                self.reply(404, "Not found")
                return
            self.reply(200, PAGE.replace("NONCE", nonce), "text/html; charset=utf-8")

        def do_POST(self):
            nonlocal completed
            if (self.path != "/setup" or self.headers.get("Host") != "127.0.0.1:8766" or
                    self.headers.get("Origin") != ORIGIN or
                    not secrets.compare_digest(self.headers.get("X-Setup-Nonce", ""), nonce)):
                self.reply(403, "Not allowed")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if completed or not 1 <= length <= 4096:
                    self.reply(400, "Invalid request")
                    return
                body = json.loads(self.rfile.read(length))
                if set(body) != {"username", "password"} or not all(isinstance(v, str) for v in body.values()):
                    raise ValueError()

                async def save():
                    try:
                        await provision_owner(body["username"], body["password"])
                    finally:
                        await dispose_engine()
                asyncio.run(save())
            except Exception:
                self.reply(400, "Setup was not completed")
                return
            completed = True
            self.reply(200, "Saved")
            print("Owner login created successfully. No password was printed.", flush=True)

    print(f"Private setup is ready at {ORIGIN}. Enter your credentials directly in the browser.", flush=True)
    HTTPServer(("127.0.0.1", 8766), Handler).serve_forever()


if __name__ == "__main__":
    main()
