# ESSFTA Breeder Showcase

A web app that collects **Kennel** and **Dog** entries from ESSFTA breeders and
assembles them into a print-ready **PDF booklet** — replacing the old
JotForm-into-InDesign-by-hand workflow.

Built for the ESSFTA 100th Anniversary (1926–2026) National Specialty.

## Why this instead of JotForm

The old attempt jumbled data because a flat spreadsheet has no way to say
"these 3 dogs belong to *this* kennel." Here every dog row carries a
`kennel_id` foreign key, so the relationship is structural and survives
concurrent entry by many owners at once. See [`app/db.py`](app/db.py).

## How it works

1. A kennel owner enters their email → gets a **magic sign-in link** (Mailgun,
   no passwords).
2. They fill the **kennel form**, then add **up to 3 dogs**, each with **2 photos**
   (auto-shrunk in the browser before upload).
3. Admins (Albert / Patty) can view & edit **every** entry, create entries **on
   behalf of** non-technical owners, and hit **Assemble Book**.
4. Assembly renders each entry to HTML matching the paper forms, sorted
   **alphabetically by kennel** with each kennel's dog pages right after it,
   then Playwright/Chromium prints one Letter-size PDF.

## Field definitions

All fields (venues, health tests, pedigree slots, limits) live in one place:
[`app/config.py`](app/config.py). Change them there and both the forms and the
booklet update together.

## Local development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
export SHOWCASE_SECRET_KEY=devkey SHOWCASE_ADMIN_EMAILS=collverab3@gmail.com
uvicorn app.main:app --reload --port 8790
```

Without `MAILGUN_API_KEY`, magic links are printed to the console (dev mode).

## Deploy to the NAS (essfta-showcase.collver.biz)

1. Copy `.env.example` → `.env`, set `SHOWCASE_SECRET_KEY` (long random) and
   `MAILGUN_API_KEY`.
2. `docker compose build && docker compose up -d`
   (or import the stack in Portainer; it joins `npm_npm_network`).
3. In Nginx Proxy Manager add a proxy host:
   `essfta-showcase.collver.biz` → `essfta-showcase:8790`, request a
   Let's Encrypt cert.
4. Point DNS for `essfta-showcase.collver.biz` at the homeserver (No-IP/UDR7).

Data (SQLite + photos) persists in the `showcase_data` / `showcase_uploads`
volumes.

## Admin

- `/admin` — list all entries, create-on-behalf, preview & assemble the book.
- Admin emails are set via `SHOWCASE_ADMIN_EMAILS` (comma-separated).
