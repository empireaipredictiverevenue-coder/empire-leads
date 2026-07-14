# empire-leads

**Zero-Chrome, multi-source B2B lead discovery engine.**

Built for AI pipelines. No Selenium. No API keys. No Chrome.

```bash
pip install git+https://github.com/empire-ai-co-uk/empire-leads.git
```

## Quick start

```bash
# Find roofing contractors near Phoenix
empire-leads discover "roofing" --near "Phoenix, AZ" --radius 20 --output leads.jsonl

# Batch from config file
empire-leads batch --config niches.yaml --output all_leads.jsonl
```

## Why?

Every existing scraper relies on Chrome/Selenium or paid APIs. Chrome in containers is:
- **Heavy** — 500MB+ per instance
- **Flaky** — headless detection, timeouts, zombie processes
- **Slow** — 60-120s per query just to boot the browser

`empire-leads` uses free public data sources:
- **Overpass API** (OpenStreetMap) — name, phone, website, address for millions of businesses
- **County permit portals** (coming) — public construction permits as lead signals
- **Google Maps enrichment** (coming) — ratings, hours, category (no Chrome, direct HTTP)

## Sources

| Source | Free | API Key | Speed | Data |
|--------|------|---------|-------|------|
| Overpass (OSM) | ✓ unlimited | None | seconds | name, phone, website, address, category |
| County Permits | ✓ | None | seconds | permit records, contractor names |
| Maps Enrichment | ✓ | None | seconds | rating, hours, price level |

## Output

```jsonl
{"name":"Phoenix Roofing","phone":"(602) 497-0154","website":"https://...","address":"301 E Bethany Home Rd ...","source":"overpass:osm","niche":"roofing","rating":4.9}
```

## License

MIT — build anything with it.
