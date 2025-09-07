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

// --- Posts loading with simple caching and fetch guard ---
let postsCache = null;
let postsFetchPromise = null;
const POSTS_LS_KEY = 'posts-json-cache';

async function loadPosts() {
  // Return cached data if available
  if (postsCache) return postsCache;

  // If a request is already in-flight, return the same promise
  if (postsFetchPromise) return postsFetchPromise;

  // Try to read from localStorage first
  try {
    const cached = localStorage.getItem(POSTS_LS_KEY);
    if (cached) {
      postsCache = JSON.parse(cached);
      return postsCache;
    }
  } catch (e) {
    console.warn('Failed to parse cached posts:', e);
  }

  // Fetch posts.json with network error handling
  postsFetchPromise = fetch('/posts.json')
    .then(r => {
      if (!r.ok) throw new Error('Network response was not ok');
      return r.json();
    })
    .then(data => {
      postsCache = data;
      try {
        localStorage.setItem(POSTS_LS_KEY, JSON.stringify(data));
      } catch (e) {
        console.warn('Failed to cache posts:', e);
      }
      return data;
    })
    .catch(err => {
      console.error('Failed to load posts:', err);
      const grid = document.getElementById('pg02-grid');
      if (grid) {
        grid.innerHTML = '<div class="text-muted">Failed to load posts.</div>';
      }
      return [];
    })
    .finally(() => {
      postsFetchPromise = null;
    });

  return postsFetchPromise;
}

// Auto-render if global POSTS array is present, otherwise fetch
if (typeof POSTS !== 'undefined') {
  renderPostGrid02(POSTS.slice(0, 6));
} else {
  loadPosts().then(data => renderPostGrid02(data.slice(0, 6)));
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
