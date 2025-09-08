// ===== AventurOO - External Feeds (client-side) =====
// Lexon RSS/Atom nga data/external-feeds.json dhe mbush seksionet:
// - në kategoritë: <div class="external-category-feed" data-category-feed="travel"></div>
// - në home:       <section data-home-feed></section>

(async function () {
  const FEEDS_CONFIG_URL = 'data/external-feeds.json';
  const MAX_ITEMS_CATEGORY = 6; // sa karta të shfaqen në faqe kategorie
  const MAX_ITEMS_HOME = 8;     // sa karta në faqen kryesore

  // ---- helpers ----
  const el = (sel, root = document) => root.querySelector(sel);
  const els = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  function fmtDate(dStr) {
    try {
      const d = new Date(dStr);
      if (isNaN(d.getTime())) return '';
      return d.toLocaleDateString('sq-AL', { year: 'numeric', month: 'short', day: '2-digit' });
    } catch { return ''; }
  }

  function card({ link, title, img, date, source }) {
    const safeImg = img || 'assets/img/placeholder-800x450.jpg';
    const safeTitle = (title || '').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    const meta = [fmtDate(date), source].filter(Boolean).join(' • ');
    return `
      <div class="col-sm-6 col-lg-4">
        <article class="card border-0 shadow-soft h-100">
          <a href="${link}" target="_blank" rel="noopener">
            <img src="${safeImg}" class="card-img-top" alt="${safeTitle}" loading="lazy">
          </a>
          <div class="card-body d-flex flex-column">
            <span class="badge bg-light text-dark">From the web</span>
            <h6 class="card-title mt-2">
              <a href="${link}" target="_blank" rel="noopener" class="link-dark">${safeTitle}</a>
            </h6>
            <div class="mt-auto small muted">${meta}</div>
          </div>
        </article>
      </div>
    `;
  }

  // Parsim RSS/Atom në një listë uniforme
  function parseFeed(xmlText, sourceName = '') {
    const out = [];
    try {
      const doc = new DOMParser().parseFromString(xmlText, 'text/xml');
      const isAtom = doc.documentElement.nodeName.toLowerCase().includes('feed');
      const items = isAtom ? doc.querySelectorAll('entry') : doc.querySelectorAll('item');

      items.forEach(it => {
        const get = sel => it.querySelector(sel)?.textContent?.trim() || '';
        const title = get('title');
        const link  = isAtom ? (it.querySelector('link')?.getAttribute('href') || '') : get('link');
        const date  = get(isAtom ? 'updated' : 'pubDate') || get('dc\\:date');

        // imazhi: media:content, enclosure, ose lëre bosh
        let img =
          it.querySelector('media\\:content, content[url]')?.getAttribute('url') ||
          it.querySelector('enclosure[type^="image"]')?.getAttribute('url') || '';

        out.push({ title, link, date, img, source: sourceName });
      });
    } catch (e) {
      console.warn('Feed parse error:', e);
    }
    return out;
  }

  // Marrim feed me AllOrigins (CORS bypass publik)
  async function fetchFeed(url) {
    try {
      const prox = `https://api.allorigins.win/get?url=${encodeURIComponent(url)}`;
      const r = await fetch(prox, { cache: 'no-store' });
      if (!r.ok) throw new Error('Bad response');
      const data = await r.json();
      return data.contents || '';
    } catch (e) {
      console.warn('Feed fetch failed:', url, e?.message);
      return '';
    }
  }

  // Lexo konfigurimin e feed-eve
  async function readConfig() {
    try {
      const r = await fetch(FEEDS_CONFIG_URL, { cache: 'no-store' });
      return r.ok ? await r.json() : {};
    } catch { return {}; }
  }

  // Mbush një seksion kategorie
  async function renderCategorySection(wrapper, catKey, cfg) {
    const feeds = cfg[catKey] || [];
    if (!feeds.length) return;

    const all = [];
    for (const src of feeds) {
      const url = typeof src === 'string' ? src : (src.url || '');
      if (!url) continue;
      const xml = await fetchFeed(url);
      if (!xml) continue;
      const sourceName = typeof src === 'string'
        ? new URL(url).hostname.replace('www.', '')
        : (src.name || new URL(url).hostname.replace('www.', ''));
      all.push(...parseFeed(xml, sourceName));
    }

    all.sort((a,b)=> new Date(b.date||0) - new Date(a.date||0));
    const html = all.slice(0, MAX_ITEMS_CATEGORY).map(card).join('') || `
      <div class="col-12"><div class="text-muted">No external items yet.</div></div>
    `;
    wrapper.innerHTML = `<div class="row g-4">${html}</div>`;
  }

  // Mbush seksionin në home me përzierje kategorish
  async function renderHomeFeed(wrapper, cfg) {
    const categories = Object.keys(cfg);
    const picks = [];

    for (const cat of categories) {
      const feeds = cfg[cat] || [];
      if (!feeds.length) continue;
      const src = feeds[0];
      const url = typeof src === 'string' ? src : (src.url || '');
      if (!url) continue;
      const xml = await fetchFeed(url);
      if (!xml) continue;
      const sourceName = typeof src === 'string'
        ? new URL(url).hostname.replace('www.', '')
        : (src.name || new URL(url).hostname.replace('www.', ''));
      picks.push(...parseFeed(xml, sourceName).slice(0, 4));
    }

    picks.sort((a,b)=> new Date(b.date||0) - new Date(a.date||0));
    const html = picks.slice(0, MAX_ITEMS_HOME).map(card).join('') || `<div class="text-muted">No external items yet.</div>`;
    wrapper.innerHTML = `<div class="row g-4">${html}</div>`;
  }

  // ---- Run ----
  const cfg = await readConfig();

  // kategori
  Array.from(document.querySelectorAll('.external-category-feed')).forEach(sec => {
    const catKey = (sec.getAttribute('data-category-feed') || '').toLowerCase();
    if (catKey) renderCategorySection(sec, catKey, cfg);
  });

  // home
  const homeSec = document.querySelector('section[data-home-feed]');
  if (homeSec) renderHomeFeed(homeSec, cfg);
})();
