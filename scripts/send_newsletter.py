#!/usr/bin/env python3
"""Send newsletter/<date>.json to Buttondown.

Usage: send_newsletter.py <date> draft|send
Needs BUTTONDOWN_API_KEY (a revocable API key from Buttondown settings, stored as a
GitHub Actions secret). "draft" creates a draft to review in Buttondown; "send"
publishes it to subscribers. Refuses to send the same date twice.
"""
import json, os, sys, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.buttondown.com/v1/emails"


def call(method, url, payload=None, extra=None):
    h = {"Authorization": f"Token {os.environ['BUTTONDOWN_API_KEY']}", "Content-Type": "application/json"}
    h.update(extra or {})
    req = urllib.request.Request(url, method=method, headers=h,
                                 data=json.dumps(payload).encode() if payload is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:800]}


def main(date, mode):
    msg = json.loads((ROOT / "newsletter" / f"{date}.json").read_text())
    log = ROOT / "newsletter" / "sent.json"
    sent = json.loads(log.read_text()) if log.exists() else {}
    if mode == "send" and sent.get(date, {}).get("status") == "sent":
        print(f"Already sent for {date}; skipping."); return
    payload = {"subject": msg["subject"], "body": msg["body"], "status": "draft"}
    if mode == "send":
        payload["status"] = "about_to_send"
    code, res = call("POST", API, payload, {"X-Buttondown-Live-Dangerously": "true"} if mode == "send" else None)
    print(code, json.dumps({k: res.get(k) for k in ("id", "status", "subject", "error")}))
    if code >= 300:
        sys.exit(1)
    sent[date] = {"status": "sent" if mode == "send" else "draft", "id": res.get("id")}
    log.write_text(json.dumps(sent, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
