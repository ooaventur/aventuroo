(function () {
  var basePath = window.AventurOOBasePath || {
    resolve: function (value) { return value; },
    resolveAll: function (values) { return Array.isArray(values) ? values.slice() : []; },
    articleUrl: function (slug) { return slug ? '/article.html?slug=' + encodeURIComponent(slug) : '#'; },
    categoryUrl: function (slug) { return slug ? '/category.html?cat=' + encodeURIComponent(slug) : '#'; },
    sectionUrl: function (slug) {
      if (!slug) return '#';
      var normalized = String(slug).trim().replace(/^\/+|\/+$/g, '');
      return normalized ? '/' + normalized + '/' : '#';
    }
  };

  var LEGACY_POSTS_SOURCES = ['/data/posts.json', 'data/posts.json'];
  var BANNERS_SOURCES = ['data/banners.json', '/data/banners.json'];
  var MAX_ARTICLES = 12;
  var BANNER_FREQUENCY = 4;
  var DEFAULT_IMAGE = basePath.resolve ? basePath.resolve('/images/logo.png') : '/images/logo.png';
  var DEFAULT_BANNER_IMAGE = basePath.resolve ? basePath.resolve('/images/ads.png') : '/images/ads.png';
  var HOT_SHARD_ROOT = '/data/hot';
  var DEFAULT_SCOPE = { parent: 'index', child: 'index' };

  function fetchSequential(urls, options) {
    if (!window.AventurOODataLoader || typeof window.AventurOODataLoader.fetchSequential !== 'function') {
      return Promise.reject(new Error('Data loader is not available'));
    }
    return window.AventurOODataLoader.fetchSequential(urls, options);
  }

  function loadJson(urls) {
    return fetchSequential(urls);
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

  function escapeHtml(value) {
    return (value == null ? '' : String(value)).replace(/[&<>"']/g, function (character) {
      return {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      }[character];
    });
  }

  function truncate(value, maxLength) {
    if (value == null) return '';
    var str = String(value).trim();
    if (str.length <= maxLength) return str;
    return str.slice(0, Math.max(0, maxLength - 1)).trimEnd() + '…';
  }

  function formatDate(dateValue) {
    if (!dateValue) return '';
    var parsed = new Date(dateValue);
    if (!isNaN(parsed.getTime())) {
      var months = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
      ];
      return months[parsed.getMonth()] + ' ' + parsed.getDate() + ', ' + parsed.getFullYear();
    }
    var fallback = Date.parse(dateValue);
    if (!isNaN(fallback)) {
      return new Date(fallback).toDateString();
    }
    return String(dateValue);
  }

  function articleUrl(post) {
    if (!post) return '#';
    if (post.url) {
      return basePath.resolve ? basePath.resolve(post.url) : post.url;
    }
    var slug = slugify(post.slug || post.title || '');
    return slug ? basePath.articleUrl ? basePath.articleUrl(slug) : '/article.html?slug=' + encodeURIComponent(slug) : '#';
  }

  function categoryUrl(category) {
    var slug = slugify(category);
    if (!slug) return '#';
    if (basePath.categoryUrl) {
      return basePath.categoryUrl(slug);
    }
    return '/category.html?cat=' + encodeURIComponent(slug);
  }

  var HOT_POSTS_CACHE = Object.create(null);

  function normalizePostsPayload(payload) {
    if (!payload) return [];
    if (Array.isArray(payload)) return payload.slice();
    if (typeof payload !== 'object') return [];
    if (Array.isArray(payload.items)) return payload.items.slice();
    if (Array.isArray(payload.posts)) return payload.posts.slice();
    if (Array.isArray(payload.data)) return payload.data.slice();
    if (Array.isArray(payload.results)) return payload.results.slice();
    return [];
  }

  function sortPosts(posts) {
    if (!Array.isArray(posts)) return [];
    return posts.slice().sort(function (a, b) {
      return parseDateValue(b.date) - parseDateValue(a.date);
    });
  }

  function resolvePostKey(post) {
    if (!post || typeof post !== 'object') return '';
    if (post.slug) return slugify(post.slug);
    if (post.url) return String(post.url).trim().toLowerCase();
    if (post.source) return String(post.source).trim().toLowerCase();
    if (post.title) return slugify(post.title);
    return '';
  }

  function dedupePosts(posts) {
    if (!Array.isArray(posts)) return [];
    var seen = Object.create(null);
    var list = [];
    for (var i = 0; i < posts.length; i++) {
      var post = posts[i];
      var key = resolvePostKey(post);
      if (key && seen[key]) continue;
      if (key) seen[key] = true;
      list.push(post);
    }
    return list;
  }

  function normalizeScope(parent, child) {
    var normalizedParent = slugify(parent) || 'index';
    var normalizedChild = child != null && child !== '' ? slugify(child) : '';
    if (!normalizedChild) normalizedChild = 'index';
    return { parent: normalizedParent, child: normalizedChild };
  }

  function buildShardUrls(parent, child) {
    var scope = normalizeScope(parent, child);
    if (scope.parent === 'index' && scope.child === 'index') {
      return [];
    }
    var prefix = HOT_SHARD_ROOT.replace(/\/+$/, '');
    var basePath = prefix ? prefix + '/' + scope.parent : scope.parent;
    var childIndexSegment = scope.child === 'index' ? 'index' : scope.child + '/index';
    var rawCandidates = [
      basePath + '/' + childIndexSegment + '.json',
      basePath + '/' + scope.child + '.json'
    ];
    var urls = [];
    for (var i = 0; i < rawCandidates.length; i++) {
      var raw = rawCandidates[i];
      if (!raw) continue;
      var relative = raw.replace(/^\/+/, '');
      if (!relative) continue;
      urls.push(relative);
      urls.push('/' + relative);
    }
    var seen = Object.create(null);
    var deduped = [];
    for (var j = 0; j < urls.length; j++) {
      var candidate = urls[j];
      if (typeof candidate !== 'string') continue;
      var trimmed = candidate.trim();
      if (!trimmed || seen[trimmed]) continue;
      seen[trimmed] = true;
      deduped.push(trimmed);
    }
    return deduped;
  }

  function fetchHotShard(parent, child) {
    var scope = normalizeScope(parent, child);
    if (scope.parent === 'index' && scope.child === 'index') {
      return Promise.reject(new Error('Root hot shard is not available'));
    }
    var scopeKey = scope.parent + '::' + scope.child;
    if (HOT_POSTS_CACHE[scopeKey]) {
      return HOT_POSTS_CACHE[scopeKey];
    }
    var candidates = buildShardUrls(scope.parent, scope.child);
    HOT_POSTS_CACHE[scopeKey] = fetchSequential(candidates)
      .then(function (payload) {
        return dedupePosts(sortPosts(normalizePostsPayload(payload)));
      })
      .catch(function (err) {
        delete HOT_POSTS_CACHE[scopeKey];
        throw err;
      });
    return HOT_POSTS_CACHE[scopeKey];
  }

  function getPostParentSlug(post) {
    if (!post || typeof post !== 'object') return '';
    var raw = post.category_slug;
    if (raw && typeof raw === 'string') {
      var parts = raw.split('/');
      if (parts.length > 1) {
        var parent = slugify(parts[0]);
        if (parent) return parent;
      }
      var normalizedAll = slugify(raw);
      if (normalizedAll && normalizedAll.indexOf('-') !== -1) {
        var maybeParent = normalizedAll.split('-')[0];
        if (maybeParent) return maybeParent;
      }
    }
    if (post.category) {
      var normalized = slugify(post.category);
      if (normalized) return normalized;
    }
    return '';
  }

  function getPostChildSlug(post) {
    if (!post || typeof post !== 'object') return '';
    var raw = post.category_slug;
    if (raw && typeof raw === 'string') {
      var parts = raw.split('/');
      if (parts.length > 1) {
        var child = slugify(parts[parts.length - 1]);
        if (child) return child;
      }
    }
    if (post.subcategory) {
      var normalized = slugify(post.subcategory);
      if (normalized) return normalized;
    }
    return '';
  }

  function matchesScope(post, scope) {
    if (!post) return false;
    var parent = scope && scope.parent ? scope.parent : 'index';
    var child = scope && scope.child ? scope.child : 'index';
    if (parent === 'index' && child === 'index') return true;
    if (child !== 'index') {
      var childSlug = getPostChildSlug(post);
      if (childSlug && childSlug === child) return true;
      return false;
    }
    if (!parent || parent === 'index') return true;
    var parentSlug = getPostParentSlug(post);
    return parentSlug ? parentSlug === parent : false;
  }

  function filterPostsByScope(posts, scope) {
    if (!Array.isArray(posts)) return [];
    return posts.filter(function (post) { return matchesScope(post, scope); });
  }

  function resolveScopeHint(elements) {
    var parent = '';
    var child = '';
    for (var i = 0; i < elements.length; i++) {
      var element = elements[i];
      if (!element || !element.getAttribute) continue;
      if (!parent) {
        var p = element.getAttribute('data-hot-parent');
        if (p) parent = slugify(p);
      }
      if (!child) {
        var c = element.getAttribute('data-hot-child');
        if (c) child = slugify(c);
      }
      if (!child) {
        var combined = element.getAttribute('data-hot-scope');
        if (combined) {
          var trimmed = combined.trim().replace(/^\/+|\/+$/g, '');
          if (trimmed.indexOf('/') !== -1) {
            var parts = trimmed.split('/');
            if (!parent) parent = slugify(parts[0]);
            child = slugify(parts[parts.length - 1]);
          } else {
            child = slugify(trimmed);
          }
        }
      }
    }
    if (!parent) parent = '';
    if (!child) child = '';
    if (parent && !child) child = 'index';
    if (!parent && child) parent = 'index';
    if (!parent) parent = DEFAULT_SCOPE.parent;
    if (!child) child = DEFAULT_SCOPE.child;
    return { parent: parent, child: child };
  }

  function loadPostsForScope(scope) {
    return fetchHotShard(scope.parent, scope.child)
      .catch(function (err) {
        console.warn('latest news hot shard error', err);
        return fetchSequential(LEGACY_POSTS_SOURCES)
          .then(function (payload) {
            var posts = dedupePosts(sortPosts(normalizePostsPayload(payload)));
            return filterPostsByScope(posts, scope);
          });
      });
  }

  function pickArticles(posts, limit) {
    var sorted = posts
      .filter(function (item) { return item && (item.slug || item.title); })
      .slice()
      .sort(function (a, b) {
        return parseDateValue(b.date) - parseDateValue(a.date);
      });

    var groups = {};
    var order = [];

    sorted.forEach(function (post) {
      var category = post.category || 'News';
      var key = slugify(category) || category.toLowerCase();
      if (!groups[key]) {
        groups[key] = { name: category, items: [] };
        order.push(key);
      }
      groups[key].items.push(post);
    });

    var selected = [];
    var pointer = 0;
    while (selected.length < limit && order.length) {
      if (pointer >= order.length) pointer = 0;
      var key = order[pointer];
      var bucket = groups[key];
      if (!bucket || !bucket.items.length) {
        order.splice(pointer, 1);
        continue;
      }
      selected.push(bucket.items.shift());
      pointer += 1;
    }

    return selected;
  }

  function parseDateValue(value) {
    if (!value) return 0;
    var parsed = new Date(value);
    if (!isNaN(parsed.getTime())) return parsed.getTime();
    var fallback = Date.parse(value);
    return isNaN(fallback) ? 0 : fallback;
  }

  function createArticleElement(post) {
    if (!post) return null;
    var title = escapeHtml(post.title || 'Untitled');
    var rawExcerpt = post.excerpt ? truncate(post.excerpt, 140) : '';
    var excerpt = rawExcerpt ? escapeHtml(rawExcerpt) : '';
    var category = post.category ? escapeHtml(post.category) : '';
    var date = escapeHtml(formatDate(post.date));
    var coverSrc = post.cover ? (basePath.resolve ? basePath.resolve(post.cover) : post.cover) : DEFAULT_IMAGE;
    var cover = escapeHtml(coverSrc);
    var link = escapeHtml(articleUrl(post));
    var categoryLink = category ? escapeHtml(categoryUrl(post.category)) : '#';
    var figureClass = post.cover ? '' : ' class="no-cover"';
    var article = document.createElement('article');
    article.className = 'article article-mini latest-news-item';
    article.innerHTML =
      '<div class="inner">' +
        '<figure' + figureClass + '>' +
          '<a href="' + link + '">' +
            '<img src="' + cover + '" alt="' + title + '">' +
          '</a>' +
        '</figure>' +
        '<div class="padding">' +
          '<div class="detail">' +
            (date ? '<div class="time">' + date + '</div>' : '') +
            (category ? '<div class="category"><a href="' + categoryLink + '">' + category + '</a></div>' : '') +
          '</div>' +
          '<h2><a href="' + link + '">' + title + '</a></h2>' +
          (excerpt ? '<p>' + excerpt + '</p>' : '') +
        '</div>' +
      '</div>';
    return article;
  }

  function createBannerElement(banner, index) {
    var href = banner.href ? (basePath.resolve ? basePath.resolve(banner.href) : banner.href) : '#';
    var imageSrc = banner.image ? (basePath.resolve ? basePath.resolve(banner.image) : banner.image) : DEFAULT_BANNER_IMAGE;
    var image = banner.image ? String(imageSrc) : imageSrc;
    var alt = banner.alt ? String(banner.alt) : 'Advertisement';
    var bannerWrapper = document.createElement('div');
    bannerWrapper.className = 'banner latest-news-banner';
    bannerWrapper.innerHTML =
      '<a href="' + escapeHtml(href) + '" target="_blank" rel="noopener noreferrer">' +
        '<img src="' + escapeHtml(image) + '" alt="' + escapeHtml(alt) + '">' +
      '</a>';
    return bannerWrapper;
  }

  function wrapColumn(element) {
    var column = document.createElement('div');
    column.className = 'col-xs-12 latest-news-col';
    column.appendChild(element);
    return column;
  }

  function hideBlock(block) {
    if (block) {
      block.style.display = 'none';
    }
  }

  function queryFirst(selectors) {
    for (var i = 0; i < selectors.length; i += 1) {
      var element = document.querySelector(selectors[i]);
      if (element) return element;
    }
    return null;
  }

  function findLatestNewsBlock(container) {
    var element = container;
    while (element && element.nodeType === 1) {
      if (element.getAttribute && element.getAttribute('data-latest-news-block') !== null) {
        return element;
      }
      var className = element.className || '';
      if (
        (element.classList && element.classList.contains('latest-news-block')) ||
        (' ' + className + ' ').indexOf(' latest-news-block ') !== -1
      ) {
        return element;
      }
      element = element.parentElement;
    }
    return queryFirst(['[data-latest-news-block]', '.latest-news-block', '#latest-news-block']);
  }

  function init() {
    var container = queryFirst(['[data-latest-news-grid]', '.latest-news-grid', '#latest-news-grid']);
    if (!container) return;
    var block = findLatestNewsBlock(container);


    var scope = resolveScopeHint([container, block, document.body]);

    Promise.all([
      loadPostsForScope(scope).catch(function (error) {
        console.error('Failed to load latest posts', error);
        return [];
      }),
      loadJson(BANNERS_SOURCES).catch(function (error) {
        console.warn('Failed to load banners.json', error);
        return [];
      })
    ]).then(function (results) {
      var posts = Array.isArray(results[0]) ? results[0] : [];
      var banners = Array.isArray(results[1]) ? results[1] : [];

      if (!posts.length) {
        hideBlock(block);
        return;
      }

      var selected = pickArticles(posts, MAX_ARTICLES);
      if (!selected.length) {
        hideBlock(block);
        return;
      }

      container.innerHTML = '';
      var fragment = document.createDocumentFragment();
      var bannerIndex = 0;

      selected.forEach(function (post, index) {
        var articleEl = createArticleElement(post);
        if (articleEl) {
          fragment.appendChild(wrapColumn(articleEl));
        }
        if ((index + 1) % BANNER_FREQUENCY === 0 && banners.length) {
          var bannerData = banners[bannerIndex % banners.length];
          var bannerEl = createBannerElement(bannerData, bannerIndex);
          if (bannerEl) {
            fragment.appendChild(wrapColumn(bannerEl));
            bannerIndex += 1;
          }
        }
      });

      if (!fragment.childNodes.length) {
        hideBlock(block);
        return;
      }

      container.appendChild(fragment);
    }).catch(function (error) {
      console.error('Failed to initialize latest news', error);
      hideBlock(block);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
