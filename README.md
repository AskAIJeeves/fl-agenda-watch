# FL agenda watch

Daily GitHub Action that pulls upcoming and recent agenda items from Florida governments that use Legistar, and flags large-dollar or notable spending items.

- `config/governments.json` lists the governments and candidate Legistar client names, plus the dollar threshold.
- `data/agenda_items.json` holds flagged items (government, meeting date, title, largest dollar amount found, links).
- `data/agenda_status.json` shows which governments worked and which failed. Governments that don't use Legistar (Tampa uses OnBase, for example) will show as failed.

Run manually from the Actions tab with "Run workflow".
