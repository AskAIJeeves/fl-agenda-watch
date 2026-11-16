"""Find Florida governments with a working Granicus agenda feed that the
project does not cover yet. Tries likely subdomains for each candidate and
view_id 1-6, and keeps feeds that return agenda items.
Writes data/granicus_probe.json.
"""
import concurrent.futures as cf
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (fl-agenda-watch; public agenda research)"}

CITIES = """Hialeah, Pompano Beach, West Palm Beach, Palm Bay, Lauderhill, Weston, Delray Beach, Homestead, Jupiter,
Sanford, Wellington, Margate, Coconut Creek, Ocala, Port Orange, Sarasota, Bradenton, Palm Beach Gardens, Bonita Springs,
Apopka, North Miami, Fort Myers, Ocoee, Winter Garden, Altamonte Springs, Oviedo, St Cloud, Coral Gables, Cutler Bay,
Miami Lakes, Plant City, Winter Haven, Titusville, Ormond Beach, DeLand, Panama City, Panama City Beach, Fort Pierce,
Vero Beach, Naples, Marco Island, Punta Gorda, Venice, Winter Park, Lake Worth Beach, Greenacres, Royal Palm Beach,
Riviera Beach, Hallandale Beach, Aventura, Sunny Isles Beach, North Miami Beach, Key West, Destin, Fort Walton Beach,
Crestview, Leesburg, Clermont, Eustis, Mount Dora, Haines City, Bartow, Lake Wales, Zephyrhills, New Port Richey,
Oldsmar, Safety Harbor, Gulfport, Temple Terrace, Sebring, St Augustine, Fernandina Beach, Jacksonville Beach,
Atlantic Beach, Lake Mary, Casselberry, Longwood, Winter Springs, Edgewater, New Smyrna Beach, Cocoa, Cocoa Beach,
Rockledge, Satellite Beach, Sebastian, Stuart, Lake Park, North Lauderdale, Lauderdale Lakes, Oakland Park,
Wilton Manors, Dania Beach, Cooper City, Parkland, Lighthouse Point, Miami Shores, Opa-locka, Sweetwater, Florida City,
Palmetto Bay, Pinecrest, Belle Glade, Lake City, Palatka, Niceville, Gulf Breeze, Lynn Haven, Callaway, Tavares,
Groveland, Minneola, Auburndale, Dade City, Brooksville, Inverness, Crystal River, Port St Joe, Arcadia, Wildwood""".replace("\n", " ")
COUNTIES = """Collier, Charlotte, Hernando, Citrus, Marion, Sumter, Brevard, Flagler, Clay, Nassau, Putnam, Leon, Bay,
Santa Rosa, Walton, Monroe, Indian River, St Lucie, Martin, Highlands, Hendry, Okeechobee, DeSoto, Columbia, Levy,
Wakulla, Jackson, Gadsden, Baker, Bradford, Union, Suwannee, Gulf, Franklin, Holmes, Washington, Hardee, Glades""".replace("\n", " ")


def slug(s):
    return re.sub(r"[^a-z]", "", s.lower())


def variants(name, county):
    b = slug(name)
    if county:
        return [f"{b}county", f"{b}countyfl", f"{b}co", f"{b}cofl", f"{b}countyflorida", f"{b}bocc", f"co{b}", b]
    return [b, f"{b}fl", f"cityof{b}", f"{b}florida", f"{b}city", f"{b}-fl"]


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=10) as r:
            return r.status, r.read(400000).decode("utf-8", "ignore")
    except Exception as e:
        return None, str(e)[:120]


def probe(name, county):
    responded = None
    for v in variants(name, county):
        st, body = get(f"https://{v}.granicus.com/ViewPublisher.php?view_id=1")
        if st is None and ("Name or service not known" in body or "nodename" in body or "getaddrinfo" in body):
            continue                                      # subdomain does not exist
        feeds = []
        for vid in range(1, 7):
            st, body = get(f"https://{v}.granicus.com/ViewPublisherRSS.php?view_id={vid}&mode=agendas")
            n = body.count("<item>") if st == 200 else 0
            if n:
                title = re.search(r"<title>([^<]{0,120})</title>", body)
                feeds.append({"view_id": vid, "items": n, "title": title.group(1) if title else None,
                              "url": f"https://{v}.granicus.com/ViewPublisherRSS.php?view_id={vid}&mode=agendas"})
        if feeds:
            return {"name": name + (" County" if county else ""), "subdomain": v, "feeds": feeds, "status": "feeds"}
        if st == 200 and "granicus" in body.lower() and "not found" not in body.lower():
            responded = responded or v
    return {"name": name + (" County" if county else ""), "subdomain": responded,
            "status": "site_no_agenda_feed" if responded else "not_found"}


def main():
    cands = [(c.strip(), False) for c in CITIES.split(",") if c.strip()] + \
            [(c.strip(), True) for c in COUNTIES.split(",") if c.strip()]
    with cf.ThreadPoolExecutor(16) as ex:
        res = list(ex.map(lambda a: probe(*a), cands))
    found = [r for r in res if r["status"] == "feeds"]
    (ROOT / "data/granicus_probe.json").write_text(json.dumps(
        {"checked": len(res), "with_feeds": len(found), "results": sorted(res, key=lambda r: r["status"])}, indent=1))
    print(f"checked {len(res)}, feeds found for {len(found)}")
    for r in found:
        print(r["name"], r["subdomain"], [(f["view_id"], f["items"]) for f in r["feeds"]])


if __name__ == "__main__":
    main()
