// ========================
// site.js – AventurOO Layout
// ========================

// Sub-kategoritë e Stories (slug = adresa, val = kategoria në posts.json)
const storySubs = [
  { label: 'Flash Fiction',   slug: 'flash',    val: 'Stories-Flash' },
  { label: 'Literary',        slug: 'literary', val: 'Stories-Literary' },
  { label: 'Nonfiction',      slug: 'nonfiction', val: 'Stories-Nonfiction' },
  { label: 'Personal',        slug: 'personal', val: 'Stories-Personal' },
  { label: 'Fantasy/Horror',  slug: 'fantasy',  val: 'Stories-Fantasy' }
];

// Struktura kryesore e navigimit
const nav = [
  {title:'Home',      url:'/index.html'},
  {title:'Travel',    url:'/travel/'},
  {title:'Stories',   url:'/stories/', subs: storySubs}, // ka dropdown
  {title:'Culture',   url:'/culture/'},
  {title:'Lifestyle', url:'/lifestyle/'},
  {title:'Guides',    url:'/guides/'},
  {title:'Deals',     url:'/deals/'},
  {title:'About',     url:'/about.html'},
  {title:'Contact',   url:'/contact.html'}
];

// ========== HEADER ==========
function renderHeader(activeTitle){
  const links = nav.map(n => {
    if (!n.subs) {
      return `
        <li class="nav-item">
          <a class="nav-link ${activeTitle===n.title?'active fw-semibold':''}" 
             href="${n.url}">${n.title}</a>
        </li>`;
    }
    // nën-kategoritë e Stories
    const subs = n.subs.map(s =>
      `<li><a class="dropdown-item" href="/stories/${s.slug}/">${s.label}</a></li>`
    ).join('');
    return `
      <li class="nav-item dropdown">
        <a class="nav-link dropdown-toggle ${activeTitle===n.title?'active fw-semibold':''}"
           href="${n.url}" id="navStories" role="button"
           data-bs-toggle="dropdown" aria-expanded="false">
          ${n.title}
        </a>
        <ul class="dropdown-menu" aria-labelledby="navStories">
          ${subs}
        </ul>
      </li>`;
  }).join('');

  // Form kërkimi (dërgon te /search/?q=...)
  const searchForm = `
    <form id="site-search" class="d-flex ms-lg-3 mt-3 mt-lg-0" role="search">
      <input class="form-control me-2" name="q" type="search" placeholder="Search…" aria-label="Search">
      <button class="btn btn-outline-primary" type="submit">
        <i class="fa-solid fa-magnifying-glass me-1"></i> Search
      </button>
    </form>`;

  document.getElementById('site-header').innerHTML = `
  <header class="navbar navbar-expand-lg navbar-light bg-white border-bottom shadow-sm">
    <div class="container">
      <a class="navbar-brand fw-bold" href="/index.html">AventurOO</a>
      <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
        <span class="navbar-toggler-icon"></span>
      </button>
      <div class="collapse navbar-collapse" id="navbarNav">
        <ul class="navbar-nav ms-auto mb-2 mb-lg-0">
          ${links}
        </ul>
        ${searchForm}
      </div>
    </div>
  </header>`;

  // Event për submit të search
  const form = document.getElementById('site-search');
  if (form) {
    form.addEventListener('submit', e => {
      e.preventDefault();
      const q = new FormData(form).get('q')?.toString().trim() || '';
      const url = new URL('/search/', location.origin);
      if (q) url.searchParams.set('q', q);
      location.href = url.toString();
    });
  }
}

// ========== FOOTER ==========
function renderFooter(){
  document.getElementById('site-footer').innerHTML = `
  <footer class="bg-light py-5 mt-5 border-top">
    <div class="container">
      <div class="row g-4">
        <div class="col-md-4">
          <h5 class="fw-bold">AventurOO</h5>
          <p class="small text-muted">Travel • Stories • Culture • Lifestyle • Deals • Guides</p>
        </div>
        <div class="col-md-2">
          <h6 class="fw-bold">Explore</h6>
          <ul class="list-unstyled small">
            <li><a class="link-secondary text-decoration-none" href="/travel/">Travel</a></li>
            <li><a class="link-secondary text-decoration-none" href="/stories/">Stories</a></li>
            <li><a class="link-secondary text-decoration-none" href="/culture/">Culture</a></li>
            <li><a class="link-secondary text-decoration-none" href="/lifestyle/">Lifestyle</a></li>
            <li><a class="link-secondary text-decoration-none" href="/guides/">Guides</a></li>
            <li><a class="link-secondary text-decoration-none" href="/deals/">Deals</a></li>
          </ul>
        </div>
        <div class="col-md-2">
          <h6 class="fw-bold">Company</h6>
          <ul class="list-unstyled small">
            <li><a class="link-secondary text-decoration-none" href="/about.html">About</a></li>
            <li><a class="link-secondary text-decoration-none" href="/contact.html">Contact</a></li>
            <li><a class="link-secondary text-decoration-none" href="/privacy.html">Privacy</a></li>
            <li><a class="link-secondary text-decoration-none" href="/terms.html">Terms</a></li>
          </ul>
        </div>
        <div class="col-md-4">
          <h6 class="fw-bold">Stay updated</h6>
          <p class="small text-muted">Follow our feeds or subscribe for updates.</p>
          <a class="btn btn-sm btn-outline-secondary me-2" href="/rss.xml" target="_blank">
            <i class="fa-solid fa-rss me-1"></i> RSS
          </a>
          <a class="btn btn-sm btn-outline-secondary" href="/sitemap.xml" target="_blank">
            <i class="fa-solid fa-sitemap me-1"></i> Sitemap
          </a>
        </div>
      </div>
      <div class="text-center small text-muted mt-4">
        &copy; ${new Date().getFullYear()} AventurOO. All rights reserved.
      </div>
    </div>
  </footer>`;
}

// ========== Ndihmëse ==========
function getCategoryFromPath() {
  const parts = location.pathname.split("/").filter(Boolean);
  return parts.length ? parts[0] : null;
}

// Auto-aktivizo linkun sipas path-it
function activateNavByPath(){
  const cat = getCategoryFromPath(); // p.sh. "travel"
  const links = document.querySelectorAll('header .nav-link[href]');
  links.forEach(a => {
    try {
      const u = new URL(a.href);
      const first = u.pathname.split('/').filter(Boolean)[0];
      if (first === cat) a.classList.add('active','fw-semibold');
    } catch {}
  });
}