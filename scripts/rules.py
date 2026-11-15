"""Shared layer-1 rules: tag and score agenda text so every reader filters the same way."""
import json, math, re
from pathlib import Path
CFG = json.loads((Path(__file__).resolve().parent.parent / "config/rules.json").read_text())
I = re.I
ACTION = re.compile(CFG["action"], I)
DECISION = re.compile(CFG["decision"], I)
ROUTINE = re.compile(CFG["routine"], I)
OUTGOING = re.compile(CFG["outgoing_grant"])          # case-sensitive tail: "to [A-Z]..." recipient name
OUTGOING_I = re.compile(CFG["outgoing_grant"], I)
BYPASS = re.compile(CFG["bypass"], I)
SIGNALS = {k: re.compile(v, I) for k, v in CFG["signals"].items()}
W = CFG["score_weights"]
MONEY = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(million|billion|m\b|mm\b)?", I)
RECIP = re.compile(r"\b(?:to|for)\s+(?:the\s+)?((?:[A-Z][\w&'.\-]*|of|and|for|the|de|la|in)(?:\s+(?:[A-Z][\w&'.\-]*|of|and|for|the|de|la|in)){0,9})")

def amounts(text):
    out = []
    for num, unit in MONEY.findall(text or ""):
        v = float(num.replace(",", ""))
        u = (unit or "").lower()
        if u in ("million", "m", "mm"): v *= 1e6
        elif u == "billion": v *= 1e9
        out.append(v)
    return out

def recipient(text):
    for m in RECIP.finditer(text or ""):
        name = m.group(1).strip(" .,")
        name = re.sub(r"\s+(of|and|for|the|de|la|in)$", "", name)
        if len(name) >= 6 and not re.match(r"(?i)^(the\s+)?(city|county|board|state|exceed|be|date|fiscal|year|period|purpose|project|program|january|february|march|april|may|june|july|august|september|october|november|december)\b", name):
            return name[:100]
    return None

def norm(name):
    n = re.sub(r"(?i)\b(inc|incorporated|corp|corporation|llc|co|the|of|and|&)\b\.?", " ", name or "")
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", n.lower()).split())

def classify(text, titles_only=False):
    """Return None to drop, else a dict of tags. Wide net: $25K+ spending actions, any outgoing grant, any bypass of competition."""
    if not text or len(text) < 30: return None
    amts = [a for a in amounts(text) if a <= CFG["max_plausible_amount"]]
    top = max(amts) if amts else None
    is_table = len(amts) >= CFG["table_amount_count"]          # budget tables, cost schedules, market stats
    decision = bool(DECISION.search(text))
    incoming = re.search(r"(?i)\baccept\w*\b[^.;]{0,80}\bgrant|\bgrant\w*\s+from\s+the\s+(state|federal|u\.?s\.?|florida|department|national)", text)
    outgoing = bool(OUTGOING.search(text)) and not is_table and not incoming
    bypass = bool(BYPASS.search(text)) and decision and not is_table
    sig = sorted(k for k, rx in SIGNALS.items() if rx.search(text))
    routine = bool(ROUTINE.search(text)) and not (outgoing or bypass or sig)
    action = bool(ACTION.search(text))
    keep = outgoing or bypass or (decision and not is_table and top is not None and top >= CFG["capture_min"] and not routine)
    if titles_only and not keep:   # agenda pages that list item titles without dollar amounts (eScribe)
        keep = bool(sig) and not routine
    if not keep: return None
    score = sum(W.get(k, 0) for k in sig) + (W["outgoing_grant"] if outgoing else 0) + (W["bypass"] if bypass else 0)
    score += round(math.log10(top) - 4, 1) if top and top > 10000 else 0      # $100K +1, $1M +2, $10M +3
    return {"max_amount": top, "signals": sig, "outgoing_grant": outgoing, "bypass_competition": bypass,
            "recipient": recipient(text) if outgoing else None, "signal_score": round(score, 1)}
