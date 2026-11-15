# FL agenda watch

Daily GitHub Action that pulls upcoming and recent agenda items from Florida governments that use Legistar, and flags large-dollar or notable spending items.

- `config/governments.json` lists the governments and candidate Legistar client names, plus the dollar threshold.
- `data/agenda_items.json` holds flagged items (government, meeting date, title, largest dollar amount found, links).
- `data/agenda_status.json` shows which governments worked and which failed. Governments that don't use Legistar (Tampa uses OnBase, for example) will show as failed.

Run manually from the Actions tab with "Run workflow".

## PDF reader (governments without a usable feed)

`scripts/fetch_pdf_agendas.py` covers governments that post agendas as PDFs. Config is in `config/pdf_sources.json`.

- **Listing-page sources** (St. Petersburg): opens the listing page, follows meeting pages one level, downloads new agenda PDFs from the last 45 days, and keeps passages that contain an action word (approve, contract, agreement, bond, etc.) and a dollar amount of $1M or more.
- **Numbered sources** (Miami-Dade): agenda PDFs are numbered by meeting key; each run checks the keys after the last one found.
- Output: `data/pdf_items.json` (last 60 days), `data/pdf_seen.json` (PDFs already scanned), `data/pdf_debug.json` (what each source found, for tuning).
- Not yet covered: Tampa (OnBase Agenda Online) and Orlando. Both load their meeting lists with JavaScript and need dedicated readers.

## Coverage (Nov 14, 2026)

| Platform | Reader | Governments |
|---|---|---|
| Legistar API | fetch_agendas.py | Fort Lauderdale, Broward, Pinellas, Hillsborough, Clearwater, Jacksonville, Seminole County, Hollywood, Port St. Lucie (Pinellas Park, Palm Beach County, Gainesville connect but return no meetings) |
| CivicClerk API | fetch_pdf_agendas.py | Tarpon Springs, St. Pete Beach, Seminole (city), Gainesville |
| Granicus RSS | fetch_pdf_agendas.py | Dunedin, Seminole (city), Polk (Tampa and Miami Beach feeds empty) |
| Agenda PDFs on city site | fetch_pdf_agendas.py | St. Petersburg |
| Numbered PDFs | fetch_pdf_agendas.py | Miami-Dade County |
| Date-patterned PDFs | fetch_pdf_agendas.py | Palm Beach County, Manatee County |
| OnBase Agenda Online | fetch_pdf_agendas.py | Tampa, Osceola County, Sarasota County (older version, HTML fallback) (uses the DownloadFileBytes endpoint; DownloadFile returns a spinner page) |

| CivicWeb | fetch_pdf_agendas.py | Daytona Beach, Largo, Miami Gardens (meeting list via MeetingsService.svc JSON) |
| eScribe | fetch_pdf_agendas.py | Orlando, St. Johns County, Cape Coral, Alachua County. Agenda PDFs sit behind a Cloudflare browser check, so only HTML item titles are read (no dollar amounts) |
| PrimeGov | fetch_pdf_agendas.py | Miami Beach, Palm Coast (CompiledDocument PDF) |
| iQM2 | fetch_pdf_agendas.py | Miami, Okaloosa County. Portal often times out for GitHub's servers |

Not yet covered: Pasco County FL (pasco.civicweb.net is Pasco, Washington), Volusia (search form), Leon and West Palm Beach (block GitHub), St. Lucie and Fort Myers (Laserfiche), Brevard, Miami (iQM2), Miami Beach (PrimeGov), Oldsmar (CivicWeb).

`scripts/probe_platforms.py` (Actions tab, "Platform probe") tests governments listed in `config/probe_list.json` against common platforms. Its Novus check gives false positives.
