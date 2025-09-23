# Aventurootest

Aventurootest is an Eleventy-powered news and magazine site. The Node/Eleventy
stack renders the public pages, while a collection of Python “autopost” scripts
pull curated RSS feeds, clean up the articles, and store them as JSON content
for the static build.

## Prerequisites

- **Node.js 18+** (or another version supported by [Eleventy](https://www.11ty.dev/)).
- **npm** for managing JavaScript dependencies (bundled with Node.js).
- **Python 3.9+** for running the autopost utilities and unit tests.
  - The scripts work with the standard library, but installing
    [`trafilatura`](https://github.com/adbar/trafilatura) and
    [`readability-lxml`](https://github.com/alan-turing-institute/ReadabiliPy)
    is recommended for higher quality article extraction: `pip install
    trafilatura readability-lxml`.

## Installation

Clone the repository and install both the Node and Python tooling:

```bash
git clone <repository-url>
cd aventurootest

# Install Eleventy and other Node dependencies
npm install

# (Optional but recommended) set up an isolated Python environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -U pip trafilatura readability-lxml
```

The repository tracks generated articles in `data/posts.json`. The autopost
scripts update that file; Eleventy reads it when building the site.

## Building the site

Run Eleventy directly with `npx` or by using the npm script:

```bash
npx eleventy        # or: npm run build
```

This generates the static site inside the `_site/` directory. The default
`npm run build` command runs Eleventy and then compresses every `.html` and
`.json` output (including the archive/search trees) into `.gz` siblings so that
the CDN can serve precompressed responses.

## Running the autopost scripts

Each autopost module (news, travel, entertainment, etc.) lives in the
`autopost/` directory. They share a feed file (`feeds_*.txt`), a deduplication
database (`autopost/seen_all.json`), and write their results to
`data/posts.json`.

Common usage pattern:

```bash
# Pull the default set of news feeds
python autopost/pull_news.py

# Limit to a specific category or custom feed file
FEEDS_FILE=/path/to/feeds.txt CATEGORY="Travel" python autopost/pull_travel.py
```

Environment variables recognised by the scripts include:

- `FEEDS_FILE` – override the bundled feeds list.
- `CATEGORY` – restrict processing to one category.
- `MAX_PER_FEED`, `MAX_TOTAL`, `MAX_POSTS_PERSIST` – tune quantity limits. Per-subcategory caps are now derived from `feed_count × per-feed cap` (5 by default, 10 when marked important).
- `FALLBACK_COVER`, `DEFAULT_AUTHOR`, `IMG_PROXY`, etc. – control cover images
  and metadata.
- `HOT_MAX_ITEMS`, `HOT_PAGINATION_SIZE` – size the hot shard payloads that
  power rotation and pagination.

All autopost runs reuse `autopost/seen_all.json` to avoid duplicates. Removing
that file forces a full refresh.

## Hot shard rotation

Autopost runs populate high-frequency shards in `data/hot/<parent>/<child>/index.json`.
The `scripts/rotate_hot_to_archive.py` utility keeps those directories trimmed
and moves older entries into the long-term archive under
`data/archive/<parent>/<child>/<yyyy>/<mm>/index.json`. Each rotation pass also
refreshes lightweight manifests (`manifest.json` / `summary.json`) for both
trees so Eleventy knows how many static pages to generate per section and per
archive month.

Run the rotation manually with:

```bash
python scripts/rotate_hot_to_archive.py --retention-days 45
```

Retention knobs:

- `config.json` → `window_days` – fallback retention window when no CLI or
  environment overrides are provided.
- `config.json` → `archive_on_days` – exported for schedulers/cron jobs that
  coordinate how frequently the rotation should run.
- `HOT_RETENTION_DAYS` – overrides the retention window from `window_days` when
  set (defaulting to the config value).
- `HOT_PAGINATION_SIZE` – pagination size used when computing manifest counts
  (default: `12`).

In day-to-day operation the rotation happens automatically. The
`.github/workflows/autopost.yml` workflow runs on a staggered cron schedule and
each matrix job finishes by calling the "Rotate hot shards into archive" step,
which executes `scripts/rotate_hot_to_archive.py` immediately after the ingest
scripts complete. That keeps the hot shards trimmed without requiring a separate
maintenance workflow, while still allowing manual execution for ad-hoc cleanup.

## Autopost heartbeat & monitoring

Every autopost ingestion run now writes `_health/autopost.json` with a lightweight
heartbeat payload. The file is refreshed both by `autopost/pull_news.py` and by
the hot-rotation job so the latest run timestamp survives the nightly pruning
pass. The JSON schema is:

```json
{
  "last_run": "2024-04-18T15:30:00Z",
  "items_published": 12,
  "errors": ["fetch_bytes failed: …"]
}
```

- `last_run` – UTC timestamp written whenever the job finishes.
- `items_published` – count of newly published stories (preserved by the
  rotation task so the ingestion job remains authoritative).
- `errors` – deduplicated list of warnings or failures observed during the run.

Eleventy copies the `_health/` directory straight into `_site/` so the Netlify
deployment exposes the heartbeat alongside the rest of the static assets.

### Cloudflare Worker integration

`scripts/monitoring/cloudflare-health-worker.js` contains a Worker that performs
three duties:

1. Strip caching for requests to `/_health/autopost.json` so consumers always
   receive a fresh payload.
2. Inspect the heartbeat on edge fetches (and on a scheduled trigger) to detect
   stale `last_run` timestamps, low publication counts, or collected errors.
3. Forward Alertmanager-compatible alerts to a webhook when thresholds are
   breached.

Configure the Worker with the following environment variables:

- `HEALTH_ORIGIN` – base origin URL that exposes `/_health/autopost.json`.
- `ALERTMANAGER_WEBHOOK` – Alertmanager receiver URL (optional; monitoring is
  read-only when omitted).
- `MIN_ITEMS_PUBLISHED` – minimum acceptable `items_published` before raising a
  `AutopostLowPublication` alert (default: `1`).
- `MAX_HEALTH_AGE_MINUTES` – maximum age of `last_run` before emitting an
  `AutopostStale` alert (default: `120`).
- `ALERTMANAGER_SERVICE` – label value used for the `service` label in emitted
  alerts (defaults to `aventuroo-autopost`).
- `ALERTMANAGER_SEVERITY` / `ALERTMANAGER_SEVERITY_LOW` – optional severity
  overrides for the generated alerts.

Deploy the Worker via Wrangler (or the Cloudflare dashboard) and attach it to
the production zone. The Worker will also post alerts when invoked by a
Cloudflare Cron Trigger, so schedule a job that runs slightly more frequently
than the acceptable `MAX_HEALTH_AGE_MINUTES` window.

### Alertmanager routing

The Worker sends alerts as a JSON array compatible with Alertmanager’s v2
webhook. A minimal receiver configuration might look like:

```yaml
route:
  receiver: autopost-pager
  match:
    service: aventuroo-autopost

receivers:
  - name: autopost-pager
    webhook_configs:
      - url: https://hooks.internal.example/alertmanager
```

Any downstream Alertmanager template can then fan out notifications (PagerDuty,
Slack, etc.) when the Worker reports stale data or ingestion failures.

## Testing

The Python tests validate the shared autopost utilities. Run the full suite
with:

```bash
python -m unittest
```

## Deployment notes

Netlify deploys the site with the command `npm run build` and publishes the
generated `_site/` directory (see `netlify.toml`). When hosting behind a path
prefix, Eleventy reads the following environment variables to determine the
base URL:

- `ELEVENTY_PATH_PREFIX`
- `BASE_PATH` (used by Netlify path prefix configurations)
- `PUBLIC_URL`

If none of those are set, the build falls back to auto-detecting GitHub Pages
deployments via `GITHUB_REPOSITORY`, otherwise the site is rendered for the
root path (`/`).

## Serving precompressed assets

Because the build step writes `.gz` files next to every HTML and JSON asset,
your host needs to advertise them correctly:

- The CDN must deliver the `.gz` variant when the client sends
  `Accept-Encoding: gzip`.
- The response should include `Cache-Control: public, max-age=31536000, immutable`
  for those long-lived archive/search pages.

Netlify already understands precompressed siblings. To attach the immutable
cache header, the repository's `netlify.toml` enables it for the dated archive
and search payloads:

```toml
[[headers]]
  for = "/archive/*"
  [headers.values]
    Cache-Control = "public, max-age=31536000, immutable"

[[headers]]
  for = "/search/*"
  [headers.values]
    Cache-Control = "public, max-age=31536000, immutable"
```

If you host elsewhere, configure the equivalent behaviour (for example, enable
`gzip_static` in Nginx or `mod_deflate`/`mod_headers` in Apache) so requests to
`archive/` or `search/` automatically serve the `.gz` payloads with the same
cache policy.
