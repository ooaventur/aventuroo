// Post Grid renderer and topbar search handler

function renderPostGrid02(items) {
  const grid = document.getElementById('pg02-grid');
  if (!grid) return;

  grid.innerHTML = items.map(p => {
    const date = new Date(p.date);
    const dateStr = date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: '2-digit' });
    const mins = p.readingMinutes ? `${p.readingMinutes} min read` : '';
    return `
      <article class="pg02-card">
        <div class="pg02-media">
          <a href="${p.url}" aria-label="${p.title}">
            <img src="${p.cover}" alt="${p.title}">
            <span class="pg02-cat">${p.category ?? 'General'}</span>
          </a>
        </div>
        <div class="pg02-body">
          <a class="pg02-title-link" href="${p.url}">${p.title}</a>
          ${p.excerpt ? `<p class="pg02-excerpt">${p.excerpt}</p>` : ''}
          <div class="pg02-meta">
            <span>${dateStr}</span>
            <span class="pg02-dot"></span>
            <span>${mins}</span>
          </div>
          <div class="pg02-read">
            <a href="${p.url}">
              Read more
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M5 12h14M13 5l7 7-7 7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
              </svg>
            </a>
          </div>
        </div>
      </article>
    `;
  }).join('');
}

// Auto-render if global POSTS array is present
if (typeof POSTS !== 'undefined') {
  renderPostGrid02(POSTS.slice(0, 6));
}

// Topbar search handler with null check
const topSearch = document.getElementById('topbar-search');
if (topSearch) {
  topSearch.addEventListener('submit', e => {
    e.preventDefault();
    const q = new FormData(topSearch).get('q')?.toString().trim() || '';
    const url = new URL('/search/', location.origin);
    if (q) url.searchParams.set('q', q);
    location.href = url.toString();
  });
}
