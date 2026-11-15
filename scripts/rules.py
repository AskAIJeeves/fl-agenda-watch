"""Shared layer-1 rules: tag and score agenda text so every reader filters the same way."""
import json, math, re
from pathlib import Path
CFG = json.loads((Path(__file__).resolve().parent.parent / "config/rules.json").read_text())
I = re.I
ACTION = re.compile(CFG["action"], I)
ROUTINE = re.compile(CFG["routine"], I)
OUTGOING = re.compile(CFG["outgoing_grant"])          # case-sensitive tail: "to [A-Z]..." recipient name
OUTGOING_I = re.compile(CFG["outgoing_grant"], I)
BYPASS = re.compile(CFG["bypass"], I)
SIGNALS = {k: re.compile(v, I) for k, v in CFG["signals"].items()}
W = CFG["score_weights"]
MONEY = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(million|billion|m\b|mm\b)?", I)
RECIP = re.compile(r"\bto\s+(?:the\s+)?((?:[A-Z][\w&'.\-]*|of|and|for|the|de|la|in)(?:\s+(?:[A-Z][\w&'.\-]*|of|and|for|the|de|la|in)){0,9})")

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
        if len(name) >= 6 and not re.match(r"(?i)^(the\s+)?(city|county|board|state|exceed|be|date|fiscal|september|october)\b", name):
            return name[:100]
    return None

def norm(name):
    n = re.sub(r"(?i)\b(inc|incorporated|corp|corporation|llc|co|the|of|and|&)\b\.?", " ", name or "")
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", n.lower()).split())

def classify(text):
    """Return None to drop, else a dict of tags. Wide net: $25K+ spending actions, any outgoing grant, any bypass of competition."""
    if not text or len(text) < 30: return None
    amts = amounts(text); top = max(amts) if amts else None
    outgoing = bool(OUTGOING.search(text) or (OUTGOING_I.search(text) and re.search(r"(?i)\bto\b", text)))
    bypass = bool(BYPASS.search(text))
    sig = sorted(k for k, rx in SIGNALS.items() if rx.search(text))
    routine = bool(ROUTINE.search(text)) and not (outgoing or bypass or sig)
    action = bool(ACTION.search(text))
    keep = outgoing or bypass or (action and top is not None and top >= CFG["capture_min"] and not routine)
    if not keep: return None
    score = sum(W.get(k, 0) for k in sig) + (W["outgoing_grant"] if outgoing else 0) + (W["bypass"] if bypass else 0)
    score += round(math.log10(top) - 4, 1) if top and top > 10000 else 0      # $100K +1, $1M +2, $10M +3
    return {"max_amount": top, "signals": sig, "outgoing_grant": outgoing, "bypass_competition": bypass,
            "recipient": recipient(text) if outgoing else None, "signal_score": round(score, 1)}
