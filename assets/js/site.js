function renderHeader(active){
  const nav=[["index.html","Home"],["travel.html","Travel"],["lifestyle.html","Lifestyle"],["culture.html","Culture"],["stories.html","Stories"],["about.html","About"]];
  const links=nav.map(([href,label])=>`<li class="nav-item"><a class="nav-link ${label===active?'active':''}" href="${href}">${label}</a></li>`).join('');
  const headerHTML=`<nav class="navbar navbar-expand-lg bg-white border-bottom sticky-top">
    <div class="container">
      <a class="navbar-brand fw-bold" href="index.html"><i class="fa-solid fa-compass me-2 text-primary"></i>AventurOO</a>
      <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#mainNav">
        <span class="navbar-toggler-icon"></span></button>
      <div class="collapse navbar-collapse" id="mainNav">
        <ul class="navbar-nav me-auto mb-2 mb-lg-0">${links}</ul>
        <form class="d-flex" role="search" onsubmit="goSearch(event)">
          <input id="q" class="form-control me-2" type="search" placeholder="Search articles…" aria-label="Search">
          <button class="btn btn-dark">Search</button>
        </form>
      </div></div></nav>`;
  const c=document.getElementById('site-header'); if(c) c.innerHTML=headerHTML;
}
function renderFooter(){
  const year=new Date().getFullYear();
  const footerHTML=`<footer class="bg-white border-top mt-5"><div class="container py-4">
      <div class="row g-3">
        <div class="col-md-6"><div class="fw-bold mb-2"><i class="fa-solid fa-compass me-2 text-primary"></i>AventurOO</div>
          <div class="text-muted small">Travel magazine & inspiration. Curated guides, stories and practical tips.</div></div>
        <div class="col-md-6"><div class="fw-semibold mb-2">Newsletter</div>
          <form class="d-flex gap-2"><input type="email" class="form-control" placeholder="Enter your email">
            <button class="btn btn-dark" type="button">Subscribe</button></form></div></div>
      <hr class="my-4"><div class="d-flex justify-content-between small text-muted">
        <div>© ${year} AventurOO · All rights reserved</div>
        <div class="footer-links"><a href="privacy.html">Privacy</a><a href="terms.html">Terms</a><a href="contact.html">Contact</a></div>
      </div></div></footer>`;
  const c=document.getElementById('site-footer'); if(c) c.innerHTML=footerHTML;
}
function goSearch(e){e.preventDefault();const q=(document.getElementById('q')?.value||'').trim();window.location.href='search.html?q='+encodeURIComponent(q)}
function qs(name){const u=new URL(location.href);return u.searchParams.get(name)||''}