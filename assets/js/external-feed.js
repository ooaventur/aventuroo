<script>
(async () => {
  // Lexo listën e feed-eve
  const res = await fetch("/data/external-feeds.json");
  const feeds = await res.json();

  async function fetchFeed(rssUrl) {
    const api = "https://api.rss2json.com/v1/api.json?rss_url=" + encodeURIComponent(rssUrl);
    try {
      const r = await fetch(api);
      const d = await r.json();
      return d.items.map(it => ({
        title: it.title,
        url: it.link,
        excerpt: (it.description || "").replace(/<[^>]+>/g,"").slice(0,150),
        image: it.enclosure?.link || it.thumbnail || "",
        date: new Date(it.pubDate || Date.now())
      }));
    } catch(e) {
      console.warn("Feed error:", rssUrl, e);
      return [];
    }
  }

  async function loadCategory(cat) {
    let items = [];
    for (const url of feeds[cat] || []) {
      const arr = await fetchFeed(url);
      items = items.concat(arr);
    }
    // rendit sipas dates
    items.sort((a,b) => b.date - a.date);
    return items;
  }

  function cardHTML(p) {
    return `
      <article class="post-card">
        <a href="${p.url}" target="_blank">
          ${p.image ? `<img src="${p.image}" alt="${p.title}" loading="lazy">` : ""}
          <h3>${p.title}</h3>
          <p>${p.excerpt}</p>
        </a>
      </article>
    `;
  }

  // Home page
  const homeEl = document.querySelector("[data-home-feed]");
  if (homeEl) {
    for (const cat of ["travel","deals","guides"]) {
      const items = await loadCategory(cat);
      const slice = items.slice(0, 4); // 4 artikuj për secilen kategori
      homeEl.insertAdjacentHTML("beforeend", `
        <section>
          <h2>${cat.toUpperCase()}</h2>
          <div class="cards">${slice.map(cardHTML).join("")}</div>
        </section>
      `);
    }
  }

  // Faqet e kategorive
  const catEl = document.querySelector("[data-category-feed]");
  if (catEl) {
    const cat = catEl.getAttribute("data-category-feed");
    const items = await loadCategory(cat);
    catEl.innerHTML = items.slice(0,12).map(cardHTML).join("");
  }
})();
</script>