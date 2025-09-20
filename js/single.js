(function () {
  const basePath = window.AventurOOBasePath || {
    resolve: (value) => value,
    resolveAll: (values) => (Array.isArray(values) ? values.slice() : []),
    articleUrl: (slugValue) => `/article.html?slug=${encodeURIComponent(slugValue)}`,
    categoryUrl: (slugValue) => {
      if (!slugValue) return '#';
      return `/category.html?cat=${encodeURIComponent(slugValue)}`;
    }
  };

  const POSTS_SOURCES = basePath.resolveAll
    ? basePath.resolveAll(['/data/posts.json', 'data/posts.json'])
    : ['/data/posts.json', 'data/posts.json'];
  const articleContainer = document.querySelector('.main-article');
  const headElement = document.head || document.getElementsByTagName('head')[0] || null;

  function readMetaContent(attribute, value) {
    if (!headElement) return '';
    const element = headElement.querySelector(`meta[${attribute}="${value}"]`);
    return element ? element.getAttribute('content') || '' : '';
  }

  function getCanonicalHref() {
    if (!headElement) return '';
    const link = headElement.querySelector('link[rel="canonical"]');
    return link ? link.getAttribute('href') || '' : '';
  }

  const defaultSeoState = {
    title: document.title || '',
    description: readMetaContent('name', 'description'),
    ogTitle: readMetaContent('property', 'og:title'),
    ogDescription: readMetaContent('property', 'og:description'),
    ogUrl: readMetaContent('property', 'og:url'),
    ogImage: readMetaContent('property', 'og:image'),
    canonical: getCanonicalHref()
  };

  if (!articleContainer) {
    return;
  }

  function pickSeoValue(value, fallback) {
    if (typeof value === 'string') {
      const trimmed = value.trim();
      if (trimmed) {
        return trimmed;
      }
    }
    return typeof fallback === 'string' ? fallback : '';
  }

  function ensureMetaContent(attribute, key, value) {
    if (!headElement) return;
    let element = headElement.querySelector(`meta[${attribute}="${key}"]`);
    if (!element) {
      element = document.createElement('meta');
      element.setAttribute(attribute, key);
      headElement.appendChild(element);
    }
    element.setAttribute('content', typeof value === 'string' ? value : '');
  }

  function setCanonicalLink(url) {
    if (!headElement) return;
    const finalUrl = pickSeoValue(url, defaultSeoState.canonical);
    if (!finalUrl) {
      const existing = headElement.querySelector('link[rel="canonical"]');
      if (existing && defaultSeoState.canonical) {
        existing.setAttribute('href', defaultSeoState.canonical);
      }
      return;
    }
    let link = headElement.querySelector('link[rel="canonical"]');
    if (!link) {
      link = document.createElement('link');
      link.setAttribute('rel', 'canonical');
      headElement.appendChild(link);
    }
    link.setAttribute('href', finalUrl);
  }

  function getWindowOrigin() {
    if (typeof window === 'undefined' || !window.location) {
      return '';
    }
    if (window.location.origin) {
      return window.location.origin;
    }
    const protocol = window.location.protocol || '';
    const host = window.location.host || '';
    if (protocol && host) {
      return `${protocol}//${host}`;
    }
    return '';
  }

  function stripHash(url) {
    if (typeof url !== 'string') return '';
    const index = url.indexOf('#');
    return index === -1 ? url : url.slice(0, index);
  }

  function absolutizeUrl(url) {
    if (typeof url !== 'string') return '';
    const trimmed = url.trim();
    if (!trimmed) return '';
    if (/^(?:[a-z][a-z0-9+.-]*:)?\/\//i.test(trimmed)) {
      return trimmed;
    }
    const origin = getWindowOrigin();
    if (!origin) {
      return trimmed;
    }
    if (trimmed[0] === '/') {
      return origin + trimmed;
    }
    try {
      return new URL(trimmed, origin).toString();
    } catch (err) {
      return trimmed;
    }
  }

  function buildCanonicalUrl(post) {
    const locationHref = (typeof window !== 'undefined' && window.location && window.location.href)
      ? stripHash(String(window.location.href))
      : '';
    if (!post || !post.slug) {
      return locationHref;
    }
    const articlePath = typeof basePath.articleUrl === 'function'
      ? basePath.articleUrl(post.slug)
      : `/article.html?slug=${encodeURIComponent(post.slug)}`;
    const absolute = stripHash(absolutizeUrl(articlePath));
    return absolute || locationHref;
  }

  function setDocumentTitle(value) {
    const finalTitle = pickSeoValue(value, defaultSeoState.title);
    if (finalTitle || defaultSeoState.title) {
      document.title = finalTitle;
    }
  }

  function updateSeoMetadata(post, options) {
    const data = post || {};
    const opts = options || {};

    setDocumentTitle(data.title ? `${data.title} — AventurOO` : '');

    const description = pickSeoValue(opts.description, defaultSeoState.description);
    const ogDescription = pickSeoValue(opts.ogDescription || description, defaultSeoState.ogDescription);
    const ogTitle = pickSeoValue(data.title, defaultSeoState.ogTitle);
    const canonicalUrl = pickSeoValue(opts.canonicalUrl, defaultSeoState.ogUrl || defaultSeoState.canonical);
    const ogImage = pickSeoValue(opts.image, defaultSeoState.ogImage);

    ensureMetaContent('name', 'description', description);
    ensureMetaContent('property', 'og:title', ogTitle);
    ensureMetaContent('property', 'og:description', ogDescription);
    ensureMetaContent('property', 'og:url', canonicalUrl);
    ensureMetaContent('property', 'og:image', ogImage);
    setCanonicalLink(canonicalUrl);
  }

  function fetchSequential(urls) {
    if (!window.AventurOODataLoader || typeof window.AventurOODataLoader.fetchSequential !== 'function') {
      return Promise.reject(new Error('Data loader is not available'));
    }
    return window.AventurOODataLoader.fetchSequential(urls);
  }

  function slugify(value) {
    return (value || '')
      .toString()
      .trim()
      .toLowerCase()
      .replace(/\.html?$/i, '')
      .replace(/&/g, 'and')
      .replace(/[_\W]+/g, '-')
      .replace(/^-+|-+$/g, '');
  }

  function parseDateValue(value) {
    if (!value) return 0;
    const time = Date.parse(value);
    return Number.isNaN(time) ? 0 : time;
  }

  function formatDate(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
  }

  function safeDecode(value) {
    if (typeof value !== 'string') return value;
    try {
      return decodeURIComponent(value);
    } catch (err) {
      return value;
    }
  }

  function cleanSlugCandidate(value) {
    if (!value) return '';
    let result = String(value).trim();
    if (!result) return '';
    result = result.replace(/^#+/, '');
    if (!result) return '';
    result = safeDecode(result);
    result = result.replace(/^[?&]*/, '');
    result = result.replace(/\.html?$/i, '');
    return result.trim();
  }

  function getSlugFromQuery() {
    try {
      const params = new URLSearchParams(window.location.search || '');
      return params.get('slug') || '';
    } catch (err) {
      return '';
    }
  }

  function getSlugFromHash() {
    const hash = window.location.hash || '';
    if (!hash) return '';
    const trimmed = hash.replace(/^#/, '').trim();
    if (!trimmed) return '';
    if (trimmed.indexOf('=') !== -1) {
      try {
        const params = new URLSearchParams(trimmed);
        const value = params.get('slug');
        if (value) return value;
      } catch (err) {
        // ignore invalid hash params
      }
    }
    return trimmed;
  }

  function stripBaseSegments(segments) {
    if (!Array.isArray(segments) || !segments.length) return segments || [];
    const helper = basePath.basePath || '';
    if (!helper) return segments;
    const baseSegments = helper.split('/').filter(Boolean).map(segment => segment.toLowerCase());
    const result = segments.slice();
    while (baseSegments.length && result.length) {
      if (result[0].toLowerCase() === baseSegments[0]) {
        result.shift();
        baseSegments.shift();
      } else {
        break;
      }
    }
    return result;
  }

  function getSlugFromPath() {
    const pathname = window.location.pathname || '';
    if (!pathname) return '';
    const rawSegments = pathname.split('/').filter(Boolean);
    if (!rawSegments.length) return '';

    const segments = stripBaseSegments(rawSegments)
      .filter(segment => segment.toLowerCase() !== 'index.html');

    while (segments.length && /^article(?:\.html)?$/i.test(segments[0])) {
      segments.shift();
    }

    if (!segments.length) return '';
    const candidate = segments[segments.length - 1];
    if (!candidate || /^category(?:\.html)?$/i.test(candidate)) {
      return '';
    }
    return candidate;
  }

  function extractSlugHints() {
    const seen = Object.create(null);
    const hints = [];

    function push(value) {
      const cleaned = cleanSlugCandidate(value);
      if (!cleaned) return '';
      const normalized = slugify(cleaned);
      if (!normalized || seen[normalized]) return cleaned;
      seen[normalized] = true;
      hints.push(cleaned);
      return cleaned;
    }

    const direct = push(getSlugFromQuery());
    push(getSlugFromHash());
    push(getSlugFromPath());

    return {
      direct: direct || '',
      hints
    };
  }

  const slugHints = extractSlugHints();
  let slug = slugHints.direct || '';
  const slugCandidates = slugHints.hints;
  const hasSlugHint = slugCandidates.length > 0;

  function findPostFromCandidates(posts, candidates) {
    if (!Array.isArray(posts) || !posts.length) return null;
    if (!Array.isArray(candidates) || !candidates.length) return null;

    const normalizedCandidates = candidates
      .map(value => slugify(value))
      .filter(Boolean);

    if (!normalizedCandidates.length) return null;

    for (let i = 0; i < normalizedCandidates.length; i++) {
      const candidate = normalizedCandidates[i];
      const match = posts.find(post => post && slugify(post.slug) === candidate);
      if (match) return match;
    }

    for (let i = 0; i < normalizedCandidates.length; i++) {
      const candidate = normalizedCandidates[i];
      const match = posts.find(post => post && slugify(post.title) === candidate);
      if (match) return match;
    }

    return null;
  }

  async function load() {
    try {
      const data = await fetchSequential(POSTS_SOURCES);
      const posts = Array.isArray(data) ? data : [];
      let post = slug ? posts.find(p => p && p.slug === slug) : null;

      if (!post) {
        const fallback = findPostFromCandidates(posts, slugCandidates);
        if (fallback) {
          post = fallback;
          slug = fallback.slug || slug;
        }
      }

      if (!post) {
        showError(hasSlugHint ? 'Post not found.' : 'Post not specified.');
        renderRelated(posts, null);
        return;
      }
      renderPost(post);
      renderRelated(posts, post);
    } catch (err) {
      console.error(err);
      showError('Failed to load post.');
      renderRelated([], null);
    }
  }

  function escapeHtml(s){return (s||"").replace(/[&<>"']/g,m=>({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;" }[m]));}
  function hostFrom(u){ try{ return new URL(u).hostname.replace(/^www\./,''); } catch(e){ return ''; } }
  function shortenUrl(u){
    try{
      const url = new URL(u);
      const host = url.hostname.replace(/^www\./,'');
      let path = (url.pathname || '/').replace(/\/+/g,'/').slice(0,60);
      if(path.length > 1 && path.endsWith('/')) path = path.slice(0,-1);
      return host + (path === '/' ? '' : path) + (url.search ? '…' : '');
    } catch(e){ return u; }
  }
  function titleizeHost(host){
    if(!host) return '';
    const base = host.split('.').slice(0,-1)[0].replace(/-/g,' ');
    return base ? base.replace(/\b\w/g,ch=>ch.toUpperCase()) : host;
  }

  function extractFirstImage(html) {
    if (!html) return '';
    const template = document.createElement('template');
    template.innerHTML = html;
    const img = template.content.querySelector('img[src]');
    if (!img) return '';
    const src = img.getAttribute('src');
    return src ? src.trim() : '';
  }

  function renderPost(post) {
    const bodyHtml = post.body || post.content || '';
    const fallbackImageFromBody = extractFirstImage(bodyHtml);

    const titleEl = document.querySelector('.main-article header h1');
    if (titleEl) titleEl.textContent = post.title;

    const dateEl = document.querySelector('.main-article header .details .date');
    if (dateEl) {
      const date = new Date(post.date);
      if (!isNaN(date)) {
        const options = { year: 'numeric', month: 'long', day: 'numeric' };
        dateEl.textContent = `Posted on ${date.toLocaleDateString(undefined, options)}`;
      } else {
        dateEl.textContent = post.date || '';
      }
    }

    const authorEl = document.querySelector('.main-article .details .author');
    if (authorEl) {
      let authorTxt = post.author;
      if (!authorTxt) {
        const host = hostFrom(post.source);
        authorTxt = post.source_name || titleizeHost(host) || host || '';
      }
      if (authorTxt) authorEl.textContent = `By ${authorTxt}`;
      else authorEl.remove();
    }

    const resolvedBodyFallback = fallbackImageFromBody
      ? (basePath.resolve ? basePath.resolve(fallbackImageFromBody) : fallbackImageFromBody)
      : '';
    const resolvedCoverImage = post.cover
      ? (basePath.resolve ? basePath.resolve(post.cover) : post.cover)
      : '';

    const coverImg = document.querySelector('.main-article .featured img');
    if (coverImg) {
      const placeholderSrc = basePath.resolve ? basePath.resolve('/images/logo.png') : '/images/logo.png';
      let attemptedBodyFallback = false;
      let attemptedPlaceholder = false;
      const handleCoverError = () => {
        if (!attemptedBodyFallback) {
          attemptedBodyFallback = true;
          const fallbackSrc = resolvedBodyFallback;
          if (fallbackSrc && coverImg.src !== fallbackSrc) {
            coverImg.src = fallbackSrc;
            return;
          }
        }
        if (!attemptedPlaceholder) {
          attemptedPlaceholder = true;
          if (coverImg.src !== placeholderSrc) {
            coverImg.src = placeholderSrc;
            return;
          }
        }
        coverImg.removeEventListener('error', handleCoverError);
        if (coverImg.parentElement) coverImg.remove();
      };

      coverImg.addEventListener('error', handleCoverError);

      coverImg.loading = 'lazy';
      coverImg.decoding = 'async';
      coverImg.referrerPolicy = 'no-referrer';
      coverImg.alt = (post.title || 'Cover') + (post.source_name ? (' — ' + post.source_name) : '');

      if (post.cover) {
        coverImg.src = resolvedCoverImage;
      } else {
        coverImg.removeEventListener('error', handleCoverError);
        coverImg.remove();
      }
    }

    const bodyEl = document.querySelector('.main-article .main');
    if (bodyEl) {
      bodyEl.innerHTML = bodyHtml;
    }

    const sourceEl = document.querySelector('.main-article .source');
    if (sourceEl) {
      if (post.source) {
        const host = hostFrom(post.source);
        const name = post.source_name || titleizeHost(host) || host || 'Source';
        const shortHref = shortenUrl(post.source);
        sourceEl.innerHTML =
          'Source: <strong>' + escapeHtml(name) + '</strong> — ' +
          '<a href="' + escapeHtml(post.source) + '" target="_blank" rel="nofollow noopener noreferrer">' +
          escapeHtml(shortHref) + '</a>';
      } else {
        sourceEl.remove();
      }
    }

    const rightsEl = document.querySelector('.main-article .rights');
    if (rightsEl) {
      const host = hostFrom(post.source);
      const owner = (post.rights && post.rights !== 'Unknown')
        ? post.rights
        : (post.source_name || host || 'the original publisher');
      rightsEl.innerHTML =
        `This post cites partial content from <strong>${escapeHtml(owner)}</strong>. ` +
        `All material remains the property of the original author and publisher; ` +
        `we do not perform editorial modification and do not republish the full article. ` +
        `To read the complete piece, please visit the ` +
        `<a href="${escapeHtml(post.source || '')}" target="_blank" rel="nofollow noopener noreferrer">original page</a>.`;
    }
    
    const resolvedFallbackImage = resolvedBodyFallback || '';
    const bestImage = resolvedCoverImage || resolvedFallbackImage;
    const ogImage = absolutizeUrl(bestImage) || bestImage;
    const description = typeof post.excerpt === 'string' ? post.excerpt.trim() : '';
    const canonicalUrl = buildCanonicalUrl(post);

    updateSeoMetadata(post, {
      description,
      canonicalUrl,
      image: ogImage
    });
  }

  function renderRelated(allPosts, currentPost) {
    const container = document.getElementById('related-posts');
    if (!container) return;

    function showMessage(text) {
      container.innerHTML = '';
      const empty = document.createElement('p');
      empty.className = 'col-xs-12 text-muted';
      empty.textContent = text;
      container.appendChild(empty);
    }

    if (!currentPost) {
      showMessage('Related posts not available.');
      return;
    }

    const list = Array.isArray(allPosts) ? allPosts : [];
    if (!list.length) {
      showMessage('No related posts yet.');
      return;
    }

    const currentSlug = currentPost.slug;
    const currentCat = slugify(currentPost.category);

    const candidates = [];

    function pushCandidates(items) {
      items.forEach(post => {
        if (!post || !post.slug || !post.title) return;
        if (post.slug === currentSlug) return;
        if (candidates.some(existing => existing.slug === post.slug)) return;
        candidates.push(post);
      });
    }

    if (currentCat) {
      pushCandidates(list.filter(post => slugify(post.category) === currentCat));
    }

    pushCandidates(list);

    const selected = candidates
      .sort((a, b) => parseDateValue(b.date) - parseDateValue(a.date))
      .slice(0, 2);

    if (!selected.length) {
      showMessage('No related posts yet.');
      return;
    }

    container.innerHTML = '';
    selected.forEach(post => container.appendChild(createRelatedCard(post)));
  }

  function createRelatedCard(post) {
    const article = document.createElement('article');
    article.className = 'article related col-md-6 col-sm-6 col-xs-12';

  const articleUrl = basePath.articleUrl ? basePath.articleUrl(post.slug) : '/article.html?slug=' + encodeURIComponent(post.slug);

    const inner = document.createElement('div');
    inner.className = 'inner';

    const figure = document.createElement('figure');
    const figureLink = document.createElement('a');
    figureLink.href = articleUrl;

    const img = document.createElement('img');
    if (post.cover) {
      img.src = post.cover;
      img.alt = post.title || 'Related article';
      img.loading = 'lazy';
      img.decoding = 'async';
      img.referrerPolicy = 'no-referrer-when-downgrade';
    } else {
      img.src = basePath.resolve ? basePath.resolve('/images/logo.png') : '/images/logo.png';
      img.alt = 'AventurOO Logo';
    }
    figureLink.appendChild(img);
    figure.appendChild(figureLink);
    inner.appendChild(figure);

    const padding = document.createElement('div');
    padding.className = 'padding';

    const titleEl = document.createElement('h2');
    const titleLink = document.createElement('a');
    titleLink.href = articleUrl;
    titleLink.textContent = post.title || '';
    titleEl.appendChild(titleLink);
    padding.appendChild(titleEl);

    const detail = document.createElement('div');
    detail.className = 'detail';
    let hasDetail = false;

    if (post.category) {
      const catDiv = document.createElement('div');
      catDiv.className = 'category';
      const catLink = document.createElement('a');
      const catSlug = slugify(post.category);
      if (catSlug) {
        catLink.href = basePath.categoryUrl
          ? basePath.categoryUrl(catSlug)
          : `/category.html?cat=${encodeURIComponent(catSlug)}`;
      } else {
        catLink.href = '#';
      }
      catLink.textContent = post.category;
      catDiv.appendChild(catLink);
      detail.appendChild(catDiv);
      hasDetail = true;
    }

    const formattedDate = formatDate(post.date);
    if (formattedDate) {
      const timeDiv = document.createElement('div');
      timeDiv.className = 'time';
      timeDiv.textContent = formattedDate;
      detail.appendChild(timeDiv);
      hasDetail = true;
    }

    if (hasDetail) {
      padding.appendChild(detail);
    }

    inner.appendChild(padding);
    article.appendChild(inner);
    return article;
  }

  function showError(message) {
    const article = document.querySelector('.main-article');
    if (article) {
      article.innerHTML = `<p>${message}</p>`;
    } else {
      document.body.innerHTML = `<p>${message}</p>`;
    }
  }

  load();
})();
