function renderHeader(active){
  const nav = [
    {title:'Home', url:'index.html'},
    {title:'Travel', url:'travel.html'},
    {title:'Stories', url:'stories.html'},
    {title:'Culture', url:'culture.html'},
    {title:'Lifestyle', url:'lifestyle.html'},
    {title:'Guides', url:'guides.html'},
    {title:'Deals', url:'deals.html'},
    {title:'About', url:'about.html'},
    {title:'Contact', url:'contact.html'}
  ];

  const links = nav.map(n => `
    <li class="nav-item">
      <a class="nav-link ${active===n.title?'active fw-semibold':''}" href="${n.url}">${n.title}</a>
    </li>
  `).join('');

  document.getElementById('site-header').innerHTML = `
  <header class="navbar navbar-expand-lg navbar-light bg-white border-bottom shadow-sm">
    <div class="container">
      <a class="navbar-brand fw-bold" href="index.html">AventurOO</a>
      <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
        <span class="navbar-toggler-icon"></span>
      </button>
      <div class="collapse navbar-collapse" id="navbarNav">
        <ul class="navbar-nav ms-auto mb-2 mb-lg-0">
          ${links}
          <li class="nav-item">
            <a class="nav-link" href="search.html" title="Search">
              <i class="fa-solid fa-magnifying-glass"></i>
            </a>
          </li>
        </ul>
      </div>
    </div>
  </header>`;
}

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
            <li><a class="link-secondary text-decoration-none" href="travel.html">Travel</a></li>
            <li><a class="link-secondary text-decoration-none" href="stories.html">Stories</a></li>
            <li><a class="link-secondary text-decoration-none" href="culture.html">Culture</a></li>
            <li><a class="link-secondary text-decoration-none" href="lifestyle.html">Lifestyle</a></li>
            <li><a class="link-secondary text-decoration-none" href="guides.html">Guides</a></li>
            <li><a class="link-secondary text-decoration-none" href="deals.html">Deals</a></li>
          </ul>
        </div>
        <div class="col-md-2">
          <h6 class="fw-bold">Company</h6>
          <ul class="list-unstyled small">
            <li><a class="link-secondary text-decoration-none" href="about.html">About</a></li>
            <li><a class="link-secondary text-decoration-none" href="contact.html">Contact</a></li>
            <li><a class="link-secondary text-decoration-none" href="privacy.html">Privacy</a></li>
            <li><a class="link-secondary text-decoration-none" href="terms.html">Terms</a></li>
          </ul>
        </div>
        <div class="col-md-4">
          <h6 class="fw-bold">Stay updated</h6>
          <p class="small text-muted">Follow our feeds or subscribe for updates.</p>
          <a class="btn btn-sm btn-outline-brand me-2" href="rss.xml" target="_blank">
            <i class="fa-solid fa-rss me-1"></i> RSS
          </a>
          <a class="btn btn-sm btn-outline-brand" href="sitemap.xml" target="_blank">
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