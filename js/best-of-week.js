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
  var BEST_OF_WEEK_SOURCES = ['data/best-of-week.json', '/data/best-of-week.json'];
  var DEFAULT_IMAGE = basePath.resolve ? basePath.resolve('/images/logo.png') : '/images/logo.png';
  var HOT_SHARD_ROOT = '/data/hot';
  var DEFAULT_SCOPE = { parent: 'index', child: 'index' };
  var HOT_POSTS_CACHE = Object.create(null);

  function fetchSequential(urls) {
    if (!window.AventurOODataLoader || typeof window.AventurOODataLoader.fetchSequential !== 'function') {
      return Promise.reject(new Error('Data loader is not available'));
    }
    return window.AventurOODataLoader.fetchSequential(urls);
  }

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

  function getPostTimestamp(post) {
    if (!post || typeof post !== 'object') return 0;
    var sources = [post.date, post.updated_at, post.published_at, post.created_at];
    for (var i = 0; i < sources.length; i++) {
      var value = sources[i];
      if (!value) continue;
      var parsed = Date.parse(value);
      if (!isNaN(parsed)) return parsed;
    }
    return 0;
  }

  function sortPosts(posts) {
    if (!Array.isArray(posts)) return [];
    return posts.slice().sort(function (a, b) {
      return getPostTimestamp(b) - getPostTimestamp(a);
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

  function uniqueStrings(values) {
    var seen = Object.create(null);
    var list = [];
    if (!Array.isArray(values)) return list;
    for (var i = 0; i < values.length; i++) {
      var value = values[i];
      if (typeof value !== 'string') continue;
      var trimmed = value.trim();
      if (!trimmed || seen[trimmed]) continue;
      seen[trimmed] = true;
      list.push(trimmed);
    }
    return list;
  }

  function padNumber(value, length) {
    var number = parseInt(value, 10);
    if (isNaN(number)) number = 0;
    var str = String(Math.abs(number));
    while (str.length < length) {
      str = '0' + str;
    }
    return str;
  }

  function buildShardCandidates(parent, child) {
    var normalizedParent = slugify(parent) || 'index';
    var normalizedChild = child != null && child !== '' ? slugify(child) : '';
    if (!normalizedChild) normalizedChild = 'index';
    var segments = [normalizedParent];
    if (normalizedChild !== 'index') {
      segments.push(normalizedChild);
    }
    var joined = segments.join('/');
    var prefix = HOT_SHARD_ROOT.replace(/\/+$/, '');
    var basePath = prefix ? prefix + '/' + joined : joined;
    var relative = basePath.replace(/^\//, '');
    return uniqueStrings([
      basePath + '.json',
      relative + '.json',
      basePath + '/index.json',
      relative + '/index.json',
      basePath + '.json.gz',
      relative + '.json.gz',
      basePath + '/index.json.gz',
      relative + '/index.json.gz'
    ]);
  }

  function fetchHotShard(parent, child) {
    var scopeKey = (parent || 'index') + '::' + (child || 'index');
    if (HOT_POSTS_CACHE[scopeKey]) {
      return HOT_POSTS_CACHE[scopeKey];
    }
    var candidates = buildShardCandidates(parent, child);
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
        console.warn('best-of-week hot shard error', err);
        return fetchSequential(LEGACY_POSTS_SOURCES)
          .then(function (payload) {
            var posts = dedupePosts(sortPosts(normalizePostsPayload(payload)));
            return filterPostsByScope(posts, scope);
          });
      });
  }

  function slugify(str) {
    return (str || '')
      .toString()
      .trim()
      .toLowerCase()
      .replace(/\.html?$/i, '')
      .replace(/&/g, 'and')
      .replace(/[_\W]+/g, '-')
      .replace(/^-+|-+$/g, '');
  }

  function escapeHtml(str) {
    return (str == null ? '' : String(str))
      .replace(/[&<>"']/g, function (ch) {
        return {
          '&': '&amp;',
          '<': '&lt;',
          '>': '&gt;',
          '"': '&quot;',
          "'": '&#39;'
        }[ch];
      });
  }

  function formatDate(dateValue) {
    if (!dateValue) return '';
    var raw = String(dateValue);
    var parsed = new Date(raw);
    if (!isNaN(parsed.getTime())) {
      var months = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
      ];
      var month = months[parsed.getMonth()];
      var day = parsed.getDate();
      var year = parsed.getFullYear();
      return month + ' ' + day + ', ' + year;
    }
    var parts = raw.split('T');
    return parts[0] || raw;
  }

  function buildArticleUrl(post) {
    if (!post) return '#';
    if (post.url) {
      return basePath.resolve ? basePath.resolve(post.url) : post.url;
    }
    var slug = post.slug ? encodeURIComponent(post.slug) : '';
    return slug ? (basePath.articleUrl ? basePath.articleUrl(post.slug) : '/article.html?slug=' + slug) : '#';
  }
  function normalizeEntries(raw) {
    if (!raw) return [];
    var list;
    if (Array.isArray(raw)) {
      list = raw;
    } else if (Array.isArray(raw.items)) {
      list = raw.items;
    } else if (Array.isArray(raw.slugs)) {
      list = raw.slugs;
    } else if (raw.slug || raw.url) {
      list = [raw];
    } else {
      return [];
    }
    return list
      .map(function (entry) {
        if (!entry) return null;
        if (typeof entry === 'string') {
          var slug = slugify(entry);
          return slug ? { slug: slug } : null;
        }
        if (typeof entry === 'object') {
          var normalized = {};
          if (entry.slug) normalized.slug = slugify(entry.slug);
          if (entry.url) normalized.url = entry.url;
          if (entry.title) normalized.title = entry.title;
          if (entry.excerpt) normalized.excerpt = entry.excerpt;
          if (entry.cover) normalized.cover = entry.cover;
          if (entry.category) normalized.category = entry.category;
          if (entry.date) normalized.date = entry.date;
          return normalized.slug || normalized.url ? normalized : null;
        }
        return null;
      })
      .filter(function (entry) { return entry && (entry.slug || entry.url); });
  }

  function mergePostWithMeta(post, meta) {
    if (!post && !meta) return null;
    var data = {
      slug: post && post.slug ? post.slug : meta && meta.slug ? meta.slug : '',
      title: post && post.title ? post.title : '',
      excerpt: post && post.excerpt ? post.excerpt : '',
      cover: post && post.cover ? post.cover : '',
      category: post && post.category ? post.category : '',
      date: post && post.date ? post.date : '',
      url: post ? buildArticleUrl(post) : '#'
    };
    if (meta) {
      if (meta.title) data.title = meta.title;
      if (meta.excerpt) data.excerpt = meta.excerpt;
      if (meta.cover) data.cover = meta.cover;
      if (meta.category) data.category = meta.category;
      if (meta.date) data.date = meta.date;
      if (meta.url) data.url = basePath.resolve ? basePath.resolve(meta.url) : meta.url;
    }
    return data;
  }

  function categoryUrl(category) {
    if (!category) return '#';
    var slug = slugify(category);
    if (!slug) return '#';
    if (basePath.categoryUrl) {
      return basePath.categoryUrl(slug);
    }
    return '/category.html?cat=' + encodeURIComponent(slug);
  }

  function createArticle(data) {
    if (!data) return null;
    var title = escapeHtml(data.title || '');
    var excerpt = escapeHtml(data.excerpt || '');
    var category = escapeHtml(data.category || '');
    var date = escapeHtml(formatDate(data.date));
    var coverSrc = data.cover ? (basePath.resolve ? basePath.resolve(data.cover) : data.cover) : DEFAULT_IMAGE;
    var cover = escapeHtml(coverSrc);
    var link = escapeHtml((data.url ? data.url : buildArticleUrl(data))); // data.url already resolved
    var categoryLink = category ? escapeHtml(categoryUrl(data.category)) : '#';
    var figureClass = data.cover ? '' : ' class="no-cover"';
    var alt = title || 'AventurOO';

    var article = document.createElement('article');
    article.className = 'article';
    article.innerHTML =
      '<div class="inner">' +
        '<figure' + figureClass + '>' +
          '<a href="' + link + '">' +
            '<img src="' + cover + '" alt="' + alt + '">' +
          '</a>' +
        '</figure>' +
        '<div class="padding">' +
          '<div class="detail">' +
            '<div class="time">' + date + '</div>' +
            (category ? '<div class="category"><a href="' + categoryLink + '">' + category + '</a></div>' : '') +
          '</div>' +
          '<h2><a href="' + link + '">' + title + '</a></h2>' +
          '<p>' + excerpt + '</p>' +
        '</div>' +
      '</div>';
    return article;
  }

  function loadJson(urls) {
    return fetchSequential(urls);
  }

  function init() {
    var wrapper = document.querySelector('.best-of-the-week');
    if (!wrapper) return;
    var carousel = wrapper.querySelector('.owl-carousel');
    if (!carousel) return;

    var scope = resolveScopeHint([wrapper, carousel, document.body]);

    Promise.all([
      loadPostsForScope(scope).catch(function (err) {
        console.error('Failed to load best-of-week posts', err);
        return [];
      }),
      loadJson(BEST_OF_WEEK_SOURCES).catch(function (err) {
        console.error('Failed to load best-of-week.json', err);
        return [];
      })
    ]).then(function (results) {
      var posts = Array.isArray(results[0]) ? results[0] : [];
      var botwRaw = results[1];
      var entries = normalizeEntries(botwRaw);
      if (!entries.length) {
        wrapper.style.display = 'none';
        return;
      }

      var postMap = posts.reduce(function (acc, post) {
        if (!post || !post.slug) return acc;
        var key = slugify(post.slug);
        if (!key) return acc;
        acc[key] = post;
        return acc;
      }, {});

      carousel.innerHTML = '';
      var fragment = document.createDocumentFragment();
      entries.forEach(function (entry) {
        var key = entry.slug ? slugify(entry.slug) : '';
        var post = key ? postMap[key] : null;
        var merged = mergePostWithMeta(post, entry);
        if (!merged || (!merged.title && !merged.excerpt)) return;
        var article = createArticle(merged);
        if (article) fragment.appendChild(article);
      });

      if (!fragment.childNodes.length) {
        wrapper.style.display = 'none';
        return;
      }

      carousel.appendChild(fragment);

      if (typeof window.initBestOfTheWeekCarousel === 'function') {
        window.initBestOfTheWeekCarousel();
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
