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
- `MAX_PER_CAT`, `MAX_TOTAL`, `MAX_POSTS_PERSIST` – tune quantity limits.
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

- `HOT_RETENTION_DAYS` – number of days to keep in `data/hot` (default: `30`).
- `HOT_PAGINATION_SIZE` – pagination size used when computing manifest counts
  (default: `12`).

The GitHub Actions workflow `rotate-hot-archive.yml` runs the script on a
schedule so pruning happens independently of the ingestion jobs.

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
