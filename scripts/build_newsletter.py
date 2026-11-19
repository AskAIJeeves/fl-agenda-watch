#!/usr/bin/env python3
"""Build the weekly FloridaSpending.com digest for Buttondown.

One email goes to every subscriber. Each county section is wrapped in a Buttondown
template condition, so a reader sees only the counties they ticked on the site form
(the form saves each county as a subscriber tag, plus "All Florida"). A reader with
no tags sees every county, so nothing is lost if tags are missing.

Content (from site/data/items.json, i.e. only items already published on the site):
  * Up for a vote: meetings from today through the next 14 days
  * Recently on an agenda: meetings in the past 7 days
Spending items only; statements and news stay on the site.

Writes newsletter/<date>.md (body) and newsletter/<date>.json ({subject, body}).
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://floridaspending.com"
PER_SECTION = 12          # most items per county per section; the rest link to the site
ALL_TAG = "All Florida"


def money(a):
    if a is None:
        return ""
    a = abs(a)
    if a >= 1e9:
        return f"${a/1e9:.1f}B"
    if a >= 1e6:
        return f"${a/1e6:.1f}M".replace(".0M", "M")
    return f"${a:,.0f}"


def fmt_date(d):
    x = dt.date.fromisoformat(d)
    return x.strftime("%a %b ") + str(x.day)


def line(i):
    amt = money(i.get("amount"))
    amt = f"**{amt}** " if amt else ""
    desc = (i.get("description") or "").strip()
    return (f"- {fmt_date(i['meeting_date'])}, **{i['government']}**: {amt}{desc} "
            f"[Source]({i['link']})")


def esc_tag(t):
    return t.replace('"', '\\"')


def main(today=None):
    today = dt.date.fromisoformat(today) if today else dt.date.today()
    items = json.loads((ROOT / "site/data/items.json").read_text())
    items = items["items"] if isinstance(items, dict) else items
    cov = json.loads((ROOT / "site/data/coverage.json").read_text())
    counties = sorted(c for c in cov["counties"] if c != "Other")

    t0, t14, t7 = today.isoformat(), (today + dt.timedelta(days=14)).isoformat(), (today - dt.timedelta(days=7)).isoformat()
    spend = [i for i in items if i.get("kind") == "spending" and i.get("meeting_date") and i.get("link")]
    ahead = [i for i in spend if t0 <= i["meeting_date"] <= t14]
    past = [i for i in spend if t7 <= i["meeting_date"] < t0]

    def pick(rows, county):
        rows = [i for i in rows if county in (i.get("counties") or [])]
        rows.sort(key=lambda i: (not i.get("featured"), -(i.get("amount") or 0)))
        return rows

    out = []
    out.append(f"Local spending items found on Florida agendas, for the week of {today.strftime('%B')} {today.day}, {today.year}. "
               "Each item links to the public record it came from. Amounts are as stated in the agenda or packet.")
    out.append("")
    out.append("**How to be heard.** Showing up in person is one of the most effective things you can do, and bringing someone "
               "with you (a spouse, a neighbor, a friend) multiplies it. Officials notice a full room. Florida law gives the public "
               "a reasonable opportunity to be heard before a board acts, under rules each board sets (s. 286.0114, Fla. Stat.). "
               "Many boards take general public comment near the start of the meeting, and you can leave once you have spoken. "
               "Some hear comment on a specific item only when that item comes up, which can be later, so check the agenda or "
               "call the clerk's office first, and turn in a speaker card early if the board uses them. If you can't attend, an "
               "email to each member before the meeting is a public record and still counts. "
               f"[More on speaking up]({SITE}/#petition).")
    out.append("")
    shown = 0
    for c in counties:
        a, p = pick(ahead, c), pick(past, c)
        if not a and not p:
            continue
        shown += 1
        out.append(f'{{% if "{esc_tag(ALL_TAG)}" in subscriber.tags or "{esc_tag(c)}" in subscriber.tags or not subscriber.tags %}}')
        out.append(f"## {c} County")
        out.append("")
        if a:
            out.append("**Up for a vote**")
            out.append("")
            out += [line(i) for i in a[:PER_SECTION]]
            if len(a) > PER_SECTION:
                out.append(f"- Plus {len(a) - PER_SECTION} more on [the site]({SITE}/#all).")
            out.append("")
        if p:
            out.append("**On an agenda last week**")
            out.append("")
            out += [line(i) for i in p[:PER_SECTION]]
            if len(p) > PER_SECTION:
                out.append(f"- Plus {len(p) - PER_SECTION} more on [the site]({SITE}/#all).")
            out.append("")
        out.append("{% endif %}")
        out.append("")

    out.append("---")
    out.append("")
    out.append(f"Counties with nothing new this week are left out. Full list, filters and big projects: [floridaspending.com]({SITE}). "
               f"To speak up before a vote, see [how to push back]({SITE}/#petition).")
    out.append("")
    out.append("We are adding local governments every week and working to make this digest as useful as possible before each vote. "
               "Suggestions and tips are welcome: reply to this email.")
    out.append("")
    out.append("Independent. Not affiliated with any government. To change your counties, unsubscribe below and sign up again on the site.")
    body = "\n".join(out)

    subject = f"Florida local spending: week of {today.strftime('%b')} {today.day}"
    d = ROOT / "newsletter"
    d.mkdir(exist_ok=True)
    (d / f"{t0}.md").write_text(body)
    (d / f"{t0}.json").write_text(json.dumps({"subject": subject, "body": body}, indent=1))
    print(json.dumps({"date": t0, "counties_with_items": shown, "up_for_vote": len(ahead), "last_week": len(past),
                      "chars": len(body)}))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
