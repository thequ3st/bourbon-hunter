# PA Bourbon Hunter

A full-stack web app that scans Pennsylvania Fine Wine & Good Spirits (FWGS) stores for allocated and rare bourbon inventory. Combines a curated 105-bourbon knowledge base with real-time FWGS inventory scanning to alert you when desirable bottles appear in stock across 600+ PA stores.

## Features

- **105-Bourbon Knowledge Base** — Curated database across 4 rarity tiers with ratings, proof, age, MSRP, and tasting notes
- **Real-Time FWGS Scanning** — Queries the FWGS Oracle Commerce Cloud API to find products and check per-store stock levels
- **Location-Based Filtering** — Find inventory near you by zip code or GPS with configurable radius (10–100 mi)
- **Product Images** — Bottle photos pulled from the FWGS CDN displayed on cards and detail modals
- **Multi-Channel Notifications** — Email (SMTP), SMS (Twilio), Discord webhook, Slack webhook
- **Scan Progress Tracking** — Live progress bar with percentage, current item, and ETA
- **Scheduled Scans** — Configurable automatic scanning interval (default: every 2 hours)
- **Settings UI** — Configure all notification channels and scan parameters from the browser — no `.env` file required
- **Dark-Themed Dashboard** — Bourbon-aesthetic UI with tier badges, stock indicators, and store details

## Rarity Tiers

| Tier | Label | Count | Examples |
|------|-------|-------|----------|
| 1 | Unicorn | 15 | Pappy Van Winkle 23, George T. Stagg, William Larue Weller |
| 2 | Highly Allocated | 16 | Weller 12, E.H. Taylor Single Barrel, Rock Hill Farms |
| 3 | Allocated | 37 | Blanton's Original, Eagle Rare 10, Booker's, Elijah Craig Barrel Proof |
| 4 | Worth Tracking | 37 | Wild Turkey Rare Breed, Knob Creek 12, Smoke Wagon Uncut Unfiltered |

## Screenshots

Once running, the dashboard is available at `http://localhost:5000`:

- **Main Dashboard** — Grid of tracked bourbons with stock status, images, tier badges, and ratings
- **Product Detail** — Expanded view with store availability, quantities, and distance
- **Settings** — Accordion-style configuration for all notification channels
- **Scan Progress** — Banner with live progress bar during scans

## Quick Start

### Prerequisites

- Python 3.10+
- pip

### Installation

```bash
git clone https://github.com/thequ3st/bourbon-hunter.git
cd bourbon-hunter
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### Run

```bash
python app.py
```

Open **http://localhost:5000** in your browser.

### First Steps

1. Open the dashboard and click **Full Scan** to populate inventory data
2. Go to **Settings** to configure notification channels (optional)
3. The scheduler will automatically scan every 2 hours (configurable in Settings)

## Configuration

All settings can be configured from the **Settings** page in the browser UI. They persist in the SQLite database and apply immediately without restart.

Alternatively, you can use environment variables via a `.env` file:

```env
# Flask
FLASK_SECRET_KEY=your-secret-key
FLASK_DEBUG=false

# Scan Settings
SCAN_INTERVAL_MINUTES=120
REQUEST_DELAY_SECONDS=2.5

# Email (SMTP)
EMAIL_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=app-password
EMAIL_TO=you@gmail.com

# SMS (Twilio)
SMS_ENABLED=true
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+1234567890
SMS_TO_NUMBER=+1234567890

# Discord
DISCORD_ENABLED=true
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Slack
SLACK_ENABLED=true
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

### Tier Alert Routing

By default, notification channels are assigned by rarity tier:

| Tier | Dashboard | Email | SMS | Discord | Slack |
|------|-----------|-------|-----|---------|-------|
| 1 — Unicorn | Yes | Yes | Yes | Yes | Yes |
| 2 — Highly Allocated | Yes | Yes | Yes | Yes | Yes |
| 3 — Allocated | Yes | Yes | No | Yes | No |
| 4 — Worth Tracking | Yes | No | No | No | No |

This is fully customizable from the Settings page.

## Architecture

```
bourbon-hunter/
├── app.py                      # Flask app, API routes, scan orchestration
├── config.py                   # Config with .env + DB settings bridge
├── requirements.txt
│
├── database/
│   ├── db.py                   # SQLite schema, migrations, connection pool
│   └── models.py               # Query functions (upsert, inventory, stats)
│
├── knowledge/
│   ├── bourbon_db.py           # Knowledge base loader, search terms, matching
│   └── data/
│       └── allocated_bourbons.json   # 105-bourbon curated database
│
├── scanner/
│   ├── fwgs_scraper.py         # 2-phase scan engine (search + stock check)
│   ├── product_parser.py       # OCC JSON parser with HTML fallback
│   └── store_locator.py        # Store locations API, geocoding, distance
│
├── notifications/
│   ├── notifier.py             # Dispatch engine with cooldown/dedup
│   ├── email_alert.py          # SMTP
│   ├── sms_alert.py            # Twilio
│   ├── discord_alert.py        # Discord webhook
│   └── slack_alert.py          # Slack webhook
│
├── static/
│   ├── css/style.css           # Dark theme styles
│   └── js/app.js               # Dashboard interactivity
│
└── templates/
    ├── index.html              # Main dashboard
    └── settings.html           # Settings UI
```

## How Scanning Works

The scanner operates in two phases:

### Phase 1 — Product Search
For each bourbon in the knowledge base, the scanner queries the FWGS search API (`/search?Ntt=<term>`) and parses results from the Oracle Commerce Cloud `window.state` JSON blob. Products are matched to the knowledge base using a 3-tier fuzzy matching strategy (substring, word-set, word-ratio) with distinctive word filtering to prevent false positives.

### Phase 2 — Per-Store Inventory
Matched products that show as in-stock are checked against the OCC `/ccstore/v1/stockStatus` API, which returns actual quantities at each of the 600+ PA store locations. New finds (product + store combinations not seen before) trigger notifications.

### Polite Scraping
- Configurable delay between requests (default 2.5 seconds)
- Custom User-Agent identifying the tool
- Respects rate limits

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/bourbons` | Knowledge base with images and tier labels |
| GET | `/api/inventory` | Latest inventory snapshots |
| GET | `/api/inventory/nearby?zip=19103&radius=25` | Inventory filtered by location |
| GET | `/api/stores/nearby?zip=19103&radius=25` | Store locations near a point |
| GET | `/api/stats` | Dashboard statistics |
| GET | `/api/scan/history` | Scan execution log |
| GET | `/api/scan/status` | Current scan state with progress |
| POST | `/api/scan/start` | Start a scan (`{"type": "full"}` or `{"type": "quick", "tier": 2}`) |
| POST | `/api/search` | Manual product search (`{"term": "pappy"}`) |
| GET | `/api/settings` | Current configuration |
| POST | `/api/settings` | Update configuration |
| POST | `/api/notifications/test` | Send test notifications |

## Database

SQLite database (`bourbon_hunter.db`) with 6 tables:

- **bourbons** — Knowledge base entries (name, distillery, proof, tier, ratings)
- **fwgs_products** — Scraped FWGS product listings (SKU, price, image URL)
- **inventory_snapshots** — Per-store stock levels over time
- **scan_log** — Scan history with timestamps and results
- **alerts_sent** — Notification history for deduplication
- **user_settings** — UI-configured settings (notification credentials, scan params)

## Dependencies

| Package | Purpose |
|---------|---------|
| Flask | Web framework and API server |
| requests | HTTP client for FWGS API |
| beautifulsoup4 + lxml | HTML parsing fallback |
| schedule | Background scan scheduler |
| python-dotenv | Environment variable loading |
| twilio | SMS notifications (optional) |

## License

MIT
