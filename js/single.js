(function () {
  'use strict';

  var basePath = window.AventurOOBasePath || {
    resolve: function (value) { return value; },
    resolveAll: function (values) { return Array.isArray(values) ? values.slice() : []; },
    articleUrl: function (slugValue) { return slugValue ? '/article.html?slug=' + encodeURIComponent(slugValue) : '#'; },
    categoryUrl: function (slugValue) { return slugValue ? '/category.html?cat=' + encodeURIComponent(slugValue) : '#'; }
  };

  var LEGACY_LOOKUP_SOURCES = basePath.resolveAll
    ? basePath.resolveAll(['/data/legacy/index.json', 'data/legacy/index.json'])
    : ['/data/legacy/index.json', 'data/legacy/index.json'];
  var LEGACY_POSTS_SOURCES = basePath.resolveAll
    ? basePath.resolveAll(['/data/posts.json', 'data/posts.json'])
    : ['/data/posts.json', 'data/posts.json'];
  var HOT_MANIFEST_SOURCES = basePath.resolveAll
    ? basePath.resolveAll(['/data/hot/manifest.json', 'data/hot/manifest.json'])
    : ['/data/hot/manifest.json', 'data/hot/manifest.json'];

  var HOT_SHARD_ROOT = '/data/hot';
  var DEFAULT_SCOPE = { parent: 'index', child: 'index' };

  var ARCHIVE_ORIGIN = (function () {
    if (window.AventurOOArchiveOrigin) {
      var provided = String(window.AventurOOArchiveOrigin).trim();
      if (provided) return provided.replace(/\/+$/, '');
    }
    var body = document.body || null;
    if (body) {
      var attr = '';
      if (body.getAttribute) {
        attr = body.getAttribute('data-archive-origin') || '';
      }
      if (!attr && body.dataset && body.dataset.archiveOrigin) {
        attr = body.dataset.archiveOrigin;
      }
      if (attr) {
        var cleaned = String(attr).trim();
        if (cleaned) return cleaned.replace(/\/+$/, '');
      }
    }
    return 'https://archive.aventuroo.com';
  })();

  var HOT_SHARD_CACHE = Object.create(null);
  var HOT_MANIFEST_PROMISE = null;

  var articleContainer = document.querySelector('.main-article');
  if (!articleContainer) {
    return;
  }

  var headElement = document.head || document.getElementsByTagName('head')[0] || null;

  function fetchSequential(urls, options) {
    if (!window.AventurOODataLoader || typeof window.AventurOODataLoader.fetchSequential !== 'function') {
      return Promise.reject(new Error('Data loader is not available'));
    }
    return window.AventurOODataLoader.fetchSequential(urls, options);
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

  function stripHtml(value) {
    if (value == null) return '';
    return String(value).replace(/<[^>]*>/g, ' ');
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

  function sortPostsByDate(posts) {
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

  function parseDateValue(value) {
    if (!value) return 0;
    var parsed = Date.parse(value);
    if (isNaN(parsed)) return 0;
    return parsed;
  }

  function formatDisplayDate(value) {
    if (!value) return '';
    var parsed = new Date(value);
    if (!isNaN(parsed.getTime())) {
      return parsed.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      });
    }
    var fallback = Date.parse(value);
    if (!isNaN(fallback)) {
      return new Date(fallback).toDateString();
    }
    return String(value);
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

  function extractYearMonth(value) {
    if (value == null) {
      return { year: 0, month: 0 };
    }
    if (value instanceof Date) {
      if (isNaN(value.getTime())) return { year: 0, month: 0 };
      return { year: value.getUTCFullYear(), month: value.getUTCMonth() + 1 };
    }
    if (typeof value === 'number' && isFinite(value)) {
      var fromNumber = new Date(value);
      if (!isNaN(fromNumber.getTime())) {
        return { year: fromNumber.getUTCFullYear(), month: fromNumber.getUTCMonth() + 1 };
      }
    }
    var text = '';
    if (typeof value === 'string') {
      text = value.trim();
    } else if (value && typeof value.toString === 'function') {
      text = String(value);
    }
    if (!text) return { year: 0, month: 0 };
    var parsed = new Date(text);
    if (!isNaN(parsed.getTime())) {
      return { year: parsed.getUTCFullYear(), month: parsed.getUTCMonth() + 1 };
    }
    var match = text.match(/(\d{4})[-/](\d{1,2})/);
    if (match) {
      var yr = parseInt(match[1], 10);
      var mo = parseInt(match[2], 10);
      if (!isNaN(yr) && !isNaN(mo)) {
        return { year: yr, month: mo };
      }
    }
    var compact = text.match(/(\d{4})(\d{2})/);
    if (compact) {
      var yr2 = parseInt(compact[1], 10);
      var mo2 = parseInt(compact[2], 10);
      if (!isNaN(yr2) && !isNaN(mo2)) {
        return { year: yr2, month: mo2 };
      }
    }
    return { year: 0, month: 0 };
  }

  function normalizeLegacyLookupPayload(payload) {
    var lookup = Object.create(null);
    if (!payload) return lookup;

    function addEntry(entry, slugHint) {
      if (!entry || typeof entry !== 'object') return;
      var slug = slugify(entry.slug || slugHint || '');
      if (!slug) return;

      var post = {
        slug: slug,
        title: entry.title || '',
        excerpt: entry.excerpt || '',
        cover: entry.cover || '',
        category: entry.category || '',
        subcategory: entry.subcategory || '',
        category_slug: entry.category_slug || '',
        date: entry.date || entry.published_at || entry.publishedAt || '',
        source: entry.source || '',
        source_name: entry.source_name || '',
        source_domain: entry.source_domain || '',
        author: entry.author || '',
        rights: entry.rights || '',
        canonical: entry.canonical || entry.archive_url || ''
      };

      var parent = slugify(entry.parent || '') || getPostParentSlug(post) || 'index';
      var child = slugify(entry.child || '') || getPostChildSlug(post) || 'index';

      var archivePath = '';
      if (typeof entry.archive_path === 'string' && entry.archive_path.trim()) {
        archivePath = entry.archive_path.trim().replace(/^\/+/, '').replace(/^data\/archive\//, '');
      }

      var year = 0;
      var month = 0;
      if (typeof entry.year === 'number' && !isNaN(entry.year)) year = entry.year;
      if (typeof entry.month === 'number' && !isNaN(entry.month)) month = entry.month;

      if ((!year || !month) && post.date) {
        var derived = extractYearMonth(post.date);
        if (!year && derived.year) year = derived.year;
        if (!month && derived.month) month = derived.month;
      }

      if (!archivePath && parent && year && month) {
        archivePath = parent + '/' + (child || 'index') + '/' + padNumber(year, 4) + '/' + padNumber(month, 2) + '/index.json';
      }

      var record = {
        slug: slug,
        post: post,
        scope: { parent: parent || 'index', child: child || 'index' }
      };

      if (post.canonical) record.canonical = post.canonical;
      if (archivePath) record.archive_path = archivePath;
      if (year) record.year = year;
      if (month) record.month = month;
      if (post.date) record.date = post.date;

      lookup[slug] = record;
    }

    if (Array.isArray(payload)) {
      for (var i = 0; i < payload.length; i++) {
        addEntry(payload[i]);
      }
      return lookup;
    }

    if (payload && typeof payload === 'object') {
      if (Array.isArray(payload.items)) {
        for (var j = 0; j < payload.items.length; j++) {
          addEntry(payload.items[j]);
        }
        return lookup;
      }
      if (payload.items && typeof payload.items === 'object') {
        Object.keys(payload.items).forEach(function (key) {
          addEntry(payload.items[key], key);
        });
        return lookup;
      }
      if (Array.isArray(payload.data)) {
        for (var k = 0; k < payload.data.length; k++) {
          addEntry(payload.data[k]);
        }
        return lookup;
      }
    }

    return lookup;
  }

  function buildLegacyArchiveUrls(path) {
    var trimmed = typeof path === 'string' ? path.trim() : '';
    if (!trimmed) return [];
    var normalized = trimmed.replace(/^\/+/, '').replace(/^data\/archive\//, '');
    if (!normalized) return [];
    var relative = 'data/archive/' + normalized;
    return uniqueStrings([relative, '/' + relative]);
  }

  function fetchArchivePostsForRecord(record) {
    if (!record || typeof record !== 'object') {
      return Promise.resolve([]);
    }

    var archivePath = record.archive_path || '';
    var scope = record.scope || {};
    var parent = scope.parent || '';
    var child = scope.child || '';
    var year = record.year || 0;
    var month = record.month || 0;

    if (!archivePath) {
      if ((!year || !month) && record.date) {
        var derived = extractYearMonth(record.date);
        if (!year && derived.year) year = derived.year;
        if (!month && derived.month) month = derived.month;
      }
      if (!parent && record.post) {
        parent = getPostParentSlug(record.post) || 'index';
      }
      if (!child && record.post) {
        child = getPostChildSlug(record.post) || 'index';
      }
      if (parent && year && month) {
        archivePath = parent + '/' + (child || 'index') + '/' + padNumber(year, 4) + '/' + padNumber(month, 2) + '/index.json';
      }
    }

    if (!archivePath) {
      return Promise.resolve([]);
    }

    var urls = buildLegacyArchiveUrls(archivePath);
    if (!urls.length) {
      return Promise.resolve([]);
    }

    return fetchSequential(urls)
      .then(function (payload) {
        return dedupePosts(sortPostsByDate(normalizePostsPayload(payload)));
      })
      .catch(function (err) {
        console.warn('legacy archive index load error', err);
        return [];
      });
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

  function buildHotShardUrls(parent, child) {
    var normalizedParent = slugify(parent) || 'index';
    var normalizedChild = child != null && child !== '' ? slugify(child) : '';
    if (!normalizedChild) normalizedChild = 'index';
    var prefix = HOT_SHARD_ROOT.replace(/\/+$/, '');
    var basePath = prefix ? prefix + '/' + normalizedParent : normalizedParent;
    var childIndexSegment = normalizedChild === 'index' ? 'index' : normalizedChild + '/index';
    var rawCandidates = [
      basePath + '/' + childIndexSegment + '.json',
      basePath + '/' + normalizedChild + '.json'
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
    return uniqueStrings(urls);
  }

  function fetchHotShard(parent, child) {
    var scopeKey = (parent || 'index') + '::' + (child || 'index');
    if (!HOT_SHARD_CACHE[scopeKey]) {
      var candidates = buildHotShardUrls(parent, child);
      HOT_SHARD_CACHE[scopeKey] = fetchSequential(candidates)
        .then(function (payload) {
          return dedupePosts(sortPostsByDate(normalizePostsPayload(payload)));
        })
        .catch(function (err) {
          delete HOT_SHARD_CACHE[scopeKey];
          throw err;
        });
    }
    return HOT_SHARD_CACHE[scopeKey];
  }

  function getHotManifest() {
    if (!HOT_MANIFEST_PROMISE) {
      HOT_MANIFEST_PROMISE = fetchSequential(HOT_MANIFEST_SOURCES)
        .catch(function (err) {
          console.warn('hot manifest load error', err);
          return null;
        });
    }
    return HOT_MANIFEST_PROMISE;
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
    if (!scope) return true;
    var parent = scope.parent || 'index';
    var child = scope.child || 'index';
    if (parent === 'index' && child === 'index') {
      return true;
    }
    if (child !== 'index') {
      var childSlug = getPostChildSlug(post);
      if (childSlug && childSlug === child) return true;
      return false;
    }
    if (!parent || parent === 'index') {
      return true;
    }
    var parentSlug = getPostParentSlug(post);
    return parentSlug ? parentSlug === parent : false;
  }

  function filterPostsByScope(posts, scope) {
    if (!Array.isArray(posts)) return [];
    return posts.filter(function (post) { return matchesScope(post, scope); });
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
    var result = String(value).trim();
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
      var params = new URLSearchParams(window.location.search || '');
      return params.get('slug') || '';
    } catch (err) {
      return '';
    }
  }

  function getSlugFromHash() {
    var hash = window.location.hash || '';
    if (!hash) return '';
    var trimmed = hash.replace(/^#/, '').trim();
    if (!trimmed) return '';
    if (trimmed.indexOf('=') !== -1) {
      try {
        var params = new URLSearchParams(trimmed);
        var value = params.get('slug');
        if (value) return value;
      } catch (err) {
        // ignore invalid hash params
      }
    }
    return trimmed;
  }

  function stripBaseSegments(segments) {
    if (!Array.isArray(segments) || !segments.length) return segments || [];
    var helper = basePath.basePath || '';
    if (!helper) return segments;
    var baseSegments = helper.split('/').filter(Boolean).map(function (segment) { return segment.toLowerCase(); });
    var result = segments.slice();
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
    var pathname = window.location.pathname || '';
    if (!pathname) return '';
    var rawSegments = pathname.split('/').filter(Boolean);
    if (!rawSegments.length) return '';

    var segments = stripBaseSegments(rawSegments)
      .filter(function (segment) { return segment.toLowerCase() !== 'index.html'; });

    while (segments.length && /^article(?:\.html)?$/i.test(segments[0])) {
      segments.shift();
    }

    if (!segments.length) return '';
    var candidate = segments[segments.length - 1];
    if (!candidate || /^category(?:\.html)?$/i.test(candidate)) {
      return '';
    }
    return candidate;
  }

  function extractSlugHints() {
    var seen = Object.create(null);
    var hints = [];

    function push(value) {
      var cleaned = cleanSlugCandidate(value);
      if (!cleaned) return '';
      var normalized = slugify(cleaned);
      if (!normalized || seen[normalized]) return cleaned;
      seen[normalized] = true;
      hints.push(cleaned);
      return cleaned;
    }

    var direct = push(getSlugFromQuery());
    push(getSlugFromHash());
    push(getSlugFromPath());

    return {
      direct: direct || '',
      hints: hints
    };
  }

  function resolveScopeHint(elements) {
    var parent = '';
    var child = '';

    for (var i = 0; i < elements.length; i++) {
      var element = elements[i];
      if (!element) continue;

      if (!parent) {
        if (element.getAttribute) {
          var attrParent = element.getAttribute('data-hot-parent') || element.getAttribute('data-cat');
          if (!attrParent && element.dataset) {
            attrParent = element.dataset.hotParent || element.dataset.cat;
          }
          if (attrParent) {
            parent = slugify(attrParent);
          }
        }
      }

      if (!child) {
        if (element.getAttribute) {
          var attrChild = element.getAttribute('data-hot-child') || element.getAttribute('data-sub');
          if (!attrChild && element.dataset) {
            attrChild = element.dataset.hotChild || element.dataset.sub;
          }
          if (attrChild) {
            child = slugify(attrChild);
          }
        }
      }

      if (!child && element.getAttribute) {
        var combined = element.getAttribute('data-hot-scope');
        if (!combined && element.dataset) {
          combined = element.dataset.hotScope;
        }
        if (combined) {
          var trimmed = String(combined).trim().replace(/^\/+|\/+$/g, '');
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

    try {
      var params = new URLSearchParams(window.location.search || '');
      if (!parent) {
        var catParam = params.get('cat') || params.get('parent');
        if (catParam) parent = slugify(catParam);
      }
      if (!child) {
        var subParam = params.get('sub') || params.get('child');
        if (subParam) child = slugify(subParam);
      }
      if (!parent && !child) {
        var scopeParam = params.get('scope');
        if (scopeParam) {
          var trimmedScope = scopeParam.trim().replace(/^\/+|\/+$/g, '');
          if (trimmedScope.indexOf('/') !== -1) {
            var partsScope = trimmedScope.split('/');
            parent = slugify(partsScope[0]);
            child = slugify(partsScope[partsScope.length - 1]);
          } else {
            child = slugify(trimmedScope);
          }
        }
      }
    } catch (err) {
      // ignore search param errors
    }

    if (!parent && child) parent = 'index';
    if (parent && !child) child = 'index';
    if (!parent) parent = DEFAULT_SCOPE.parent;
    if (!child) child = DEFAULT_SCOPE.child;

    return { parent: parent, child: child };
  }

  function findPostBySlug(posts, slugValue) {
    if (!Array.isArray(posts)) return null;
    var normalized = slugify(slugValue);
    if (!normalized) return null;
    for (var i = 0; i < posts.length; i++) {
      var post = posts[i];
      if (!post) continue;
      if (post.slug && slugify(post.slug) === normalized) return post;
      if (!post.slug && post.title && slugify(post.title) === normalized) return post;
    }
    return null;
  }
  function parseCanonicalUrl(url) {
    if (!url) return null;
    var trimmed = String(url).trim();
    if (!trimmed) return null;
    var parsed;
    try {
      parsed = new URL(trimmed, window.location.href);
    } catch (err) {
      return null;
    }
    var pathname = parsed.pathname || '';
    var segments = pathname.split('/').filter(function (segment) { return !!segment; });
    if (!segments.length) return null;

    var slugSegment = segments[segments.length - 1];
    var childSegment = segments.length >= 2 ? segments[segments.length - 2] : 'index';
    var parentSegment = segments.length >= 3 ? segments[segments.length - 3] : 'index';

    return {
      origin: parsed.origin || '',
      parent: slugify(parentSegment) || 'index',
      child: slugify(childSegment) || 'index',
      slug: slugify(slugSegment) || ''
    };
  }

  function buildCanonicalPath(context, slugValue) {
    var parent = context && context.parent ? slugify(context.parent) : '';
    if (!parent) parent = 'index';
    var child = context && context.child != null && context.child !== '' ? slugify(context.child) : '';
    if (!child) child = 'index';
    var finalSlug = slugify(context && context.slug ? context.slug : slugValue);
    var segments = [parent || 'index', child || 'index'];
    if (finalSlug) segments.push(finalSlug);
    return segments.join('/') + '/';
  }

  function computeCanonicalUrl(post, context) {
    if (post && typeof post.canonical === 'string') {
      var canonicalTrimmed = post.canonical.trim();
      if (canonicalTrimmed) return canonicalTrimmed;
    }
    var baseOrigin = ARCHIVE_ORIGIN || '';
    if (context && context.origin) {
      var originCandidate = String(context.origin).trim();
      if (originCandidate) baseOrigin = originCandidate;
    }
    if (!baseOrigin) return '';
    var path = buildCanonicalPath(context || {}, post ? post.slug : '');
    if (!path) return '';
    return baseOrigin.replace(/\/+$/, '') + '/' + path.replace(/^\/+/, '');
  }

  function ensureArchiveContextFromPost(post, fallbackScope) {
    if (!post) return null;
    var canonicalInfo = parseCanonicalUrl(post.canonical || post.archive_url || '');
    if (canonicalInfo) {
      if ((!canonicalInfo.parent || canonicalInfo.parent === 'index') && fallbackScope && fallbackScope.parent) {
        canonicalInfo.parent = fallbackScope.parent;
      }
      if ((!canonicalInfo.child || canonicalInfo.child === 'index') && fallbackScope && fallbackScope.child) {
        canonicalInfo.child = fallbackScope.child;
      }
      if (!canonicalInfo.origin) {
        canonicalInfo.origin = ARCHIVE_ORIGIN;
      }
      return canonicalInfo;
    }
    var parent = fallbackScope && fallbackScope.parent ? fallbackScope.parent : getPostParentSlug(post) || 'index';
    var child = fallbackScope && fallbackScope.child ? fallbackScope.child : getPostChildSlug(post) || 'index';
    return {
      origin: ARCHIVE_ORIGIN,
      parent: parent || 'index',
      child: child || 'index',
      slug: slugify(post.slug || post.title || '')
    };
  }


  function searchHotShard(scope, slugValue) {
    if (!scope) return Promise.resolve(null);
    return fetchHotShard(scope.parent, scope.child)
      .then(function (items) {
        var filtered = filterPostsByScope(items, scope);
        var post = findPostBySlug(filtered, slugValue);
        if (!post) return null;
        return {
          post: post,
          posts: filtered,
          source: 'hot',
          scope: scope
        };
      })
      .catch(function (err) {
        console.warn('hot shard load error', err);
        return null;
      });
  }

  function searchHotViaManifest(slugValue) {
    return getHotManifest().then(function (manifest) {
      if (!manifest || !Array.isArray(manifest.shards) || !manifest.shards.length) {
        return null;
      }
      var shards = manifest.shards.slice();
      var index = shards.length - 1;

      function next() {
        if (index < 0) return Promise.resolve(null);
        var entry = shards[index--] || {};
        var parent = entry.parent || 'index';
        var child = entry.child || 'index';
        return fetchHotShard(parent, child)
          .then(function (items) {
            var filtered = filterPostsByScope(items, { parent: parent, child: child });
            var post = findPostBySlug(filtered, slugValue);
            if (post) {
              return {
                post: post,
                posts: filtered,
                source: 'hot',
                scope: { parent: parent, child: child }
              };
            }
            return next();
          })
          .catch(function (err) {
            console.warn('hot manifest shard error', err);
            return next();
          });
      }

      return next();
    });
  }


  function loadHotPost(slugValue, scope) {
    return searchHotShard(scope, slugValue)
      .then(function (result) {
        if (result) return result;
        return searchHotViaManifest(slugValue);
      });
  }

  function buildCanonicalCandidates(canonicalUrl) {
    var trimmed = typeof canonicalUrl === 'string' ? canonicalUrl.trim() : '';
    if (!trimmed) return [];
    var normalized = trimmed.replace(/\/index\.html?$/i, '').replace(/\/+$/, '');
    var plain = normalized.replace(/\.json(?:\.gz)?$/i, '');
    return uniqueStrings([
      trimmed,
      normalized,
      plain,
      plain + '.json',
      plain + '/index.json',
      plain + '.json.gz',
      plain + '/index.json.gz'
    ]);
  }

  function normalizeArchiveArticlePayload(payload, slugValue) {
    var article = null;
    var related = [];
    var collection = [];

    if (Array.isArray(payload)) {
      collection = payload.slice();
      article = findPostBySlug(collection, slugValue) || (collection.length ? collection[0] : null);
      return { article: article, related: related, collection: collection };
    }

    if (payload && typeof payload === 'object') {
      if (Array.isArray(payload.related)) {
        related = payload.related.slice();
      } else if (Array.isArray(payload.related_posts)) {
        related = payload.related_posts.slice();
      }

      if (payload.post && typeof payload.post === 'object') {
        article = payload.post;
        if (!collection.length && Array.isArray(payload.posts)) {
          collection = payload.posts.slice();
        } else if (!collection.length && Array.isArray(payload.items)) {
          collection = payload.items.slice();
        }
        if (!related.length && Array.isArray(payload.post.related)) {
          related = payload.post.related.slice();
        }
      }

      if (!article && payload.article && typeof payload.article === 'object') {
        article = payload.article;
      }

      if (!article && Array.isArray(payload.posts)) {
        collection = payload.posts.slice();
        article = findPostBySlug(collection, slugValue) || collection[0] || article;
      }

      if (!article && Array.isArray(payload.items)) {
        if (!collection.length) {
          collection = payload.items.slice();
        }
        var match = findPostBySlug(payload.items, slugValue);
        article = match || payload.items[0] || article;
      }

      if (!article && payload.data) {
        var nested = normalizeArchiveArticlePayload(payload.data, slugValue);
        if (nested.article && !article) article = nested.article;
        if (!collection.length && nested.collection.length) collection = nested.collection;
        if (!related.length && nested.related.length) related = nested.related;
      }

      if (!article && payload.entry && typeof payload.entry === 'object') {
        article = payload.entry;
      }

      if (!article && (payload.slug || payload.title || payload.body || payload.content)) {
        article = payload;
      }
    }

    return { article: article, related: related, collection: collection };
  }

  function fetchCanonicalArticle(canonicalUrl, slugValue) {
    var candidates = buildCanonicalCandidates(canonicalUrl);
    if (!candidates.length) {
      return Promise.resolve(null);
    }
    return fetchSequential(candidates)
      .then(function (payload) {
        var normalized = normalizeArchiveArticlePayload(payload, slugValue);
        if (!normalized.article) {
          return null;
        }
        return normalized;
      })
      .catch(function (err) {
        console.warn('canonical article load error', err);
        return null;
      });
  }

  function mergeArchiveWithHot(archivePost, hotPost, slugValue) {
    var archive = archivePost || {};
    var hot = hotPost || {};
    var merged = {};

    merged.slug = slugify(archive.slug || hot.slug || slugValue || '');
    merged.title = archive.title || hot.title || '';
    merged.excerpt = archive.excerpt || archive.summary || archive.description || hot.excerpt || '';
    merged.body = archive.body || archive.content || archive.html || archive.content_html || hot.body || '';
    if (!merged.body && archive.body_html) merged.body = archive.body_html;
    if (!merged.body && archive.summary_html) merged.body = archive.summary_html;
    merged.cover = archive.cover || archive.image || hot.cover || '';
    merged.category = archive.category || hot.category || '';
    merged.subcategory = archive.subcategory || hot.subcategory || '';
    merged.category_slug = archive.category_slug || hot.category_slug || '';
    merged.date = archive.date || archive.published_at || archive.created_at || hot.date || hot.published_at || hot.created_at || '';
    merged.published_at = archive.published_at || hot.published_at || '';
    merged.updated_at = archive.updated_at || hot.updated_at || '';
    merged.source = archive.source || hot.source || '';
    merged.source_name = archive.source_name || hot.source_name || '';
    merged.source_domain = archive.source_domain || hot.source_domain || '';
    merged.author = archive.author || hot.author || '';
    merged.rights = archive.rights || hot.rights || '';
    merged.canonical = archive.canonical || hot.canonical || '';
    merged.archive_url = archive.archive_url || hot.archive_url || merged.canonical || '';
    merged.url = archive.url || hot.url || '';

    if (!merged.excerpt && archive.summary_html) {
      merged.excerpt = stripHtml(archive.summary_html);
    }

    return merged;
  }

  function loadCanonicalFromHot(hotResult, slugValue) {
    if (!hotResult || !hotResult.post) {
      return Promise.resolve(null);
    }
    var slug = slugValue || hotResult.post.slug || hotResult.post.title || '';
    var canonicalUrl = hotResult.post.canonical || hotResult.post.archive_url || '';
    if (!canonicalUrl) {
      return Promise.resolve(null);
    }

    return fetchCanonicalArticle(canonicalUrl, slug)
      .then(function (normalized) {
        if (!normalized || !normalized.article) {
          return null;
        }
        var mergedPost = mergeArchiveWithHot(normalized.article, hotResult.post, slug);
        var parsedCanonical = parseCanonicalUrl(normalized.article.canonical || canonicalUrl) || parseCanonicalUrl(canonicalUrl);
        if (parsedCanonical && !parsedCanonical.origin) {
          parsedCanonical.origin = ARCHIVE_ORIGIN;
        }
        var context = parsedCanonical || ensureArchiveContextFromPost(mergedPost, hotResult.scope);
        var relatedPools = [];
        if (Array.isArray(normalized.related) && normalized.related.length) {
          relatedPools.push(normalized.related);
        }
        if (Array.isArray(normalized.collection) && normalized.collection.length) {
          relatedPools.push(normalized.collection);
        }
        if (Array.isArray(hotResult.posts) && hotResult.posts.length) {
          relatedPools.push(hotResult.posts);
        }
        return {
          post: mergedPost,
          posts: Array.isArray(normalized.collection) && normalized.collection.length ? normalized.collection : hotResult.posts,
          source: 'archive',
          context: context,
          scope: hotResult.scope,
          relatedSources: relatedPools
        };
      })
      .catch(function (err) {
        console.warn('canonical article fetch failed', err);
        return null;
      });
  }

  function loadLegacyPostFromPostsJson(slugValue) {
    return fetchSequential(LEGACY_POSTS_SOURCES)
      .then(function (payload) {
        var posts = dedupePosts(sortPostsByDate(normalizePostsPayload(payload)));
        var post = findPostBySlug(posts, slugValue);
        if (!post) return null;
        return {
          post: post,
          posts: posts,
          source: 'legacy'
        };
      })
      .catch(function (err) {
        console.error('legacy posts fallback load error', err);
        return null;
      });
  }

  function loadLegacyPost(slugValue) {
    var normalized = slugify(slugValue);
    if (!normalized) return Promise.resolve(null);
    return fetchSequential(LEGACY_LOOKUP_SOURCES)
      .then(function (payload) {
        var lookup = normalizeLegacyLookupPayload(payload);
        var entry = lookup[normalized];
        if (!entry) return null;

        var legacyPost = entry.post || null;
        var scope = entry.scope || {
          parent: legacyPost ? getPostParentSlug(legacyPost) || 'index' : 'index',
          child: legacyPost ? getPostChildSlug(legacyPost) || 'index' : 'index'
        };
        var canonicalUrl = entry.canonical || (legacyPost && legacyPost.canonical) || '';
        var canonicalPromise = canonicalUrl
          ? fetchCanonicalArticle(canonicalUrl, normalized)
          : Promise.resolve(null);

        return Promise.all([canonicalPromise, fetchArchivePostsForRecord(entry)]).then(function (results) {
          var canonicalData = results[0];
          var archivePosts = Array.isArray(results[1]) ? results[1].slice() : [];
          var relatedPools = [];
          var mergedPost = null;

          if (canonicalData && canonicalData.article) {
            mergedPost = mergeArchiveWithHot(canonicalData.article, legacyPost, normalized);
            if (Array.isArray(canonicalData.related) && canonicalData.related.length) {
              relatedPools.push(canonicalData.related);
            }
            if (Array.isArray(canonicalData.collection) && canonicalData.collection.length) {
              relatedPools.push(canonicalData.collection);
              if (!archivePosts.length) {
                archivePosts = dedupePosts(sortPostsByDate(canonicalData.collection));
              }
            }
          }

          if (!mergedPost || !mergedPost.body) {
            return null;
          }

          if (!archivePosts.length && legacyPost) {
            archivePosts = [legacyPost];
          }

          if (!findPostBySlug(archivePosts, normalized)) {
            archivePosts.unshift(mergedPost);
          }

          var context = ensureArchiveContextFromPost(mergedPost, scope);
          return {
            post: mergedPost,
            posts: archivePosts,
            source: 'legacy',
            context: context,
            scope: scope,
            relatedSources: relatedPools
          };
        });
      })
      .catch(function (err) {
        console.error('legacy lookup load error', err);
        return null;
      })
      .then(function (result) {
        if (result) return result;
        return loadLegacyPostFromPostsJson(normalized);
      });
  }
  function loadArticleForSlug(slugValue, scope) {
    if (!slugValue) return Promise.resolve(null);
    return loadHotPost(slugValue, scope)
      .then(function (hotResult) {
        if (!hotResult) {
          return loadLegacyPost(slugValue);
        }
        return loadCanonicalFromHot(hotResult, slugValue)
          .then(function (archiveResult) {
            if (archiveResult) {
              return archiveResult;
            }
            hotResult.relatedSources = hotResult.relatedSources || [];
            return hotResult;
          })
          .catch(function () {
            hotResult.relatedSources = hotResult.relatedSources || [];
            return hotResult;
          });
      })
      .then(function (result) {
        if (result) return result;
        return loadLegacyPost(slugValue);
      });
  }

  function loadArticle(slugCandidates, scope) {
    var list = Array.isArray(slugCandidates) && slugCandidates.length ? slugCandidates : [''];
    var index = 0;

    function next() {
      if (index >= list.length) {
        return Promise.resolve(null);
      }
      var candidate = list[index++];
      return loadArticleForSlug(candidate, scope).then(function (result) {
        if (result) return result;
        return next();
      });
    }

    return next();
  }

  function collectRelatedPools(result) {
    var pools = [];
    if (result) {
      if (Array.isArray(result.posts) && result.posts.length) {
        pools.push(result.posts);
      }
      if (Array.isArray(result.relatedSources)) {
        for (var i = 0; i < result.relatedSources.length; i++) {
          var pool = result.relatedSources[i];
          if (Array.isArray(pool) && pool.length) {
            pools.push(pool);
          }
        }
      }
    }
    return pools;
  }

  function readMetaContent(attribute, value) {
    if (!headElement) return '';
    var element = headElement.querySelector('meta[' + attribute + '="' + value + '"]');
    return element ? element.getAttribute('content') || '' : '';
  }

  function getCanonicalHref() {
    if (!headElement) return '';
    var link = headElement.querySelector('link[rel="canonical"]');
    return link ? link.getAttribute('href') || '' : '';
  }

  var defaultSeoState = {
    title: document.title || '',
    description: readMetaContent('name', 'description'),
    ogTitle: readMetaContent('property', 'og:title'),
    ogDescription: readMetaContent('property', 'og:description'),
    ogUrl: readMetaContent('property', 'og:url'),
    ogImage: readMetaContent('property', 'og:image'),
    canonical: getCanonicalHref()
  };

  function pickSeoValue(value, fallback) {
    if (typeof value === 'string') {
      var trimmed = value.trim();
      if (trimmed) return trimmed;
    }
    return typeof fallback === 'string' ? fallback : '';
  }

  function ensureMetaContent(attribute, key, value) {
    if (!headElement) return;
    var selector = 'meta[' + attribute + '="' + key + '"]';
    var element = headElement.querySelector(selector);
    if (!element) {
      element = document.createElement('meta');
      element.setAttribute(attribute, key);
      headElement.appendChild(element);
    }
    element.setAttribute('content', typeof value === 'string' ? value : '');
  }

  function setCanonicalLink(url) {
    if (!headElement) return;
    var finalUrl = pickSeoValue(url, defaultSeoState.canonical);
    var link = headElement.querySelector('link[rel="canonical"]');
    if (!finalUrl) {
      if (link && defaultSeoState.canonical) {
        link.setAttribute('href', defaultSeoState.canonical);
      }
      return;
    }
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
    var protocol = window.location.protocol || '';
    var host = window.location.host || '';
    if (protocol && host) {
      return protocol + '//' + host;
    }
    return '';
  }

  function stripHash(url) {
    if (typeof url !== 'string') return '';
    var index = url.indexOf('#');
    return index === -1 ? url : url.slice(0, index);
  }

  function absolutizeUrl(url) {
    if (typeof url !== 'string') return '';
    var trimmed = url.trim();
    if (!trimmed) return '';
    if (/^(?:[a-z][a-z0-9+.-]*:)?\/\//i.test(trimmed)) {
      return trimmed;
    }
    var origin = getWindowOrigin();
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

  function setDocumentTitle(value) {
    var finalTitle = pickSeoValue(value, defaultSeoState.title);
    if (finalTitle || defaultSeoState.title) {
      document.title = finalTitle;
    }
  }

  function updateSeoMetadata(post, context) {
    var data = post || {};
    var canonicalContext = context && context.context ? context.context : ensureArchiveContextFromPost(data, context && context.scope);
    var canonicalUrl = computeCanonicalUrl(data, canonicalContext || {});

    setDocumentTitle(data.title ? data.title + ' — AventurOO' : '');

    var description = pickSeoValue(data.excerpt, defaultSeoState.description);
    var ogDescription = pickSeoValue(description, defaultSeoState.ogDescription);
    var ogTitle = pickSeoValue(data.title, defaultSeoState.ogTitle);
    var ogImage = pickSeoValue(context && context.image, defaultSeoState.ogImage);
    var finalCanonical = pickSeoValue(canonicalUrl, defaultSeoState.canonical || defaultSeoState.ogUrl);

    ensureMetaContent('name', 'description', description);
    ensureMetaContent('property', 'og:title', ogTitle);
    ensureMetaContent('property', 'og:description', ogDescription);
    ensureMetaContent('property', 'og:url', finalCanonical);
    ensureMetaContent('property', 'og:image', ogImage);
    setCanonicalLink(finalCanonical);
  }

  function hostFrom(url) {
    try {
      return new URL(url).hostname.replace(/^www\./, '');
    } catch (err) {
      return '';
    }
  }

  function shortenUrl(url) {
    try {
      var parsed = new URL(url);
      var host = parsed.hostname.replace(/^www\./, '');
      var path = (parsed.pathname || '/').replace(/\/+/g, '/').slice(0, 60);
      if (path.length > 1 && path.endsWith('/')) path = path.slice(0, -1);
      return host + (path === '/' ? '' : path) + (parsed.search ? '…' : '');
    } catch (err) {
      return url;
    }
  }

  function titleizeHost(host) {
    if (!host) return '';
    var base = host.split('.').slice(0, -1)[0].replace(/-/g, ' ');
    return base ? base.replace(/\b\w/g, function (ch) { return ch.toUpperCase(); }) : host;
  }

  function extractFirstImage(html) {
    if (!html) return '';
    var template = document.createElement('template');
    template.innerHTML = html;
    var img = template.content.querySelector('img[src]');
    if (!img) return '';
    var src = img.getAttribute('src');
    return src ? src.trim() : '';
  }

  function renderPost(post, context) {
    var bodyHtml = post.body || post.content || '';
    var fallbackImageFromBody = extractFirstImage(bodyHtml);

    var titleEl = document.querySelector('.main-article header h1');
    if (titleEl) titleEl.textContent = post.title || '';

    var dateEl = document.querySelector('.main-article header .details .date');
    if (dateEl) {
      if (post.date) {
        dateEl.textContent = 'Posted on ' + formatDisplayDate(post.date);
      } else {
        dateEl.textContent = '';
      }
    }

    var authorEl = document.querySelector('.main-article .details .author');
    if (authorEl) {
      var authorTxt = post.author;
      if (!authorTxt) {
        var host = hostFrom(post.source);
        authorTxt = post.source_name || titleizeHost(host) || host || '';
      }
      if (authorTxt) {
        authorEl.textContent = 'By ' + authorTxt;
      } else {
        authorEl.remove();
      }
    }

    var resolvedBodyFallback = fallbackImageFromBody
      ? (basePath.resolve ? basePath.resolve(fallbackImageFromBody) : fallbackImageFromBody)
      : '';
    var resolvedCoverImage = post.cover
      ? (basePath.resolve ? basePath.resolve(post.cover) : post.cover)
      : '';

    var coverImg = document.querySelector('.main-article .featured img');
    if (coverImg) {
      var placeholderSrc = basePath.resolve ? basePath.resolve('/images/logo.png') : '/images/logo.png';
      var attemptedBodyFallback = false;
      var attemptedPlaceholder = false;
      var handleCoverError = function () {
        if (!attemptedBodyFallback) {
          attemptedBodyFallback = true;
          var fallbackSrc = resolvedBodyFallback;
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

    var bodyEl = document.querySelector('.main-article .main');
    if (bodyEl) {
      bodyEl.innerHTML = bodyHtml;
    }

    var sourceEl = document.querySelector('.main-article .source');
    if (sourceEl) {
      if (post.source) {
        var host = hostFrom(post.source);
        var name = post.source_name || titleizeHost(host) || host || 'Source';
        var shortHref = shortenUrl(post.source);
        sourceEl.innerHTML =
          'Source: <strong>' + escapeHtml(name) + '</strong> — ' +
          '<a href="' + escapeHtml(post.source) + '" target="_blank" rel="nofollow noopener noreferrer">' +
          escapeHtml(shortHref) + '</a>';
      } else {
        sourceEl.remove();
      }
    }

    var rightsEl = document.querySelector('.main-article .rights');
    if (rightsEl) {
      var host = hostFrom(post.source);
      var owner = (post.rights && post.rights !== 'Unknown')
        ? post.rights
        : (post.source_name || host || 'the original publisher');
      rightsEl.innerHTML =
        'This post cites partial content from <strong>' + escapeHtml(owner) + '</strong>. ' +
        'All material remains the property of the original author and publisher; ' +
        'we do not perform editorial modification and do not republish the full article. ' +
        'To read the complete piece, please visit the ' +
        '<a href="' + escapeHtml(post.source || '') + '" target="_blank" rel="nofollow noopener noreferrer">original page</a>.';
    }

    var resolvedFallbackImage = resolvedBodyFallback || '';
    var bestImage = resolvedCoverImage || resolvedFallbackImage;
    var ogImage = absolutizeUrl(bestImage) || bestImage;

    updateSeoMetadata(post, {
      context: context,
      image: ogImage,
      scope: context && context.scope ? context.scope : null
    });
  }

  function createRelatedCard(post) {
    var article = document.createElement('article');
    article.className = 'article related col-md-6 col-sm-6 col-xs-12';

    var articleUrlValue = post.slug
      ? (basePath.articleUrl ? basePath.articleUrl(post.slug) : '/article.html?slug=' + encodeURIComponent(post.slug))
      : '#';

    var inner = document.createElement('div');
    inner.className = 'inner';

    var figure = document.createElement('figure');
    var figureLink = document.createElement('a');
    figureLink.href = articleUrlValue;

    var img = document.createElement('img');
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

    var padding = document.createElement('div');
    padding.className = 'padding';

    var titleEl = document.createElement('h2');
    var titleLink = document.createElement('a');
    titleLink.href = articleUrlValue;
    titleLink.textContent = post.title || '';
    titleEl.appendChild(titleLink);
    padding.appendChild(titleEl);

    var detail = document.createElement('div');
    detail.className = 'detail';
    var hasDetail = false;

    if (post.category) {
      var catDiv = document.createElement('div');
      catDiv.className = 'category';
      var catLink = document.createElement('a');
      var catSlug = slugify(post.category);
      if (catSlug) {
        catLink.href = basePath.categoryUrl
          ? basePath.categoryUrl(catSlug)
          : '/category.html?cat=' + encodeURIComponent(catSlug);
      } else {
        catLink.href = '#';
      }
      catLink.textContent = post.category;
      catDiv.appendChild(catLink);
      detail.appendChild(catDiv);
      hasDetail = true;
    }

    var formattedDate = formatDisplayDate(post.date);
    if (formattedDate) {
      var timeDiv = document.createElement('div');
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

  function renderRelated(allPools, currentPost) {
    var container = document.getElementById('related-posts');
    if (!container) return;

    function showMessage(message) {
      container.innerHTML = '<p class="col-xs-12 text-muted">' + escapeHtml(message) + '</p>';
    }

    if (!currentPost) {
      showMessage('No related posts yet.');
      return;
    }

    var list = [];
    for (var i = 0; i < allPools.length; i++) {
      var pool = allPools[i];
      if (!Array.isArray(pool)) continue;
      for (var j = 0; j < pool.length; j++) {
        var candidate = pool[j];
        if (!candidate || !candidate.slug || !candidate.title) continue;
        list.push(candidate);
      }
    }

    if (!list.length) {
      showMessage('No related posts yet.');
      return;
    }

    var currentSlug = currentPost.slug ? slugify(currentPost.slug) : '';
    var currentCat = slugify(currentPost.category);

    var candidates = [];
    var seen = Object.create(null);

    function pushCandidate(post) {
      if (!post || !post.slug) return;
      var slug = slugify(post.slug);
      if (!slug || slug === currentSlug || seen[slug]) return;
      seen[slug] = true;
      candidates.push(post);
    }

    if (currentCat) {
      list.forEach(function (post) {
        if (slugify(post.category) === currentCat) {
          pushCandidate(post);
        }
      });
    }

    list.forEach(pushCandidate);

    var selected = candidates
      .slice()
      .sort(function (a, b) { return parseDateValue(b.date) - parseDateValue(a.date); })
      .slice(0, 2);

    if (!selected.length) {
      showMessage('No related posts yet.');
      return;
    }

    container.innerHTML = '';
    selected.forEach(function (post) {
      container.appendChild(createRelatedCard(post));
    });
  }

  function showError(message) {
    var article = document.querySelector('.main-article');
    if (article) {
      article.innerHTML = '<p>' + escapeHtml(message || 'Article not found.') + '</p>';
    } else {
      document.body.innerHTML = '<p>' + escapeHtml(message || 'Article not found.') + '</p>';
    }
  }

  var slugHints = extractSlugHints();
  var slugCandidates = slugHints.hints.length ? slugHints.hints : (slugHints.direct ? [slugHints.direct] : []);
  if (!slugCandidates.length) {
    showError('Post not specified.');
    return;
  }

  var scopeHint = resolveScopeHint([document.body, articleContainer]);

  loadArticle(slugCandidates, scopeHint)
    .then(function (result) {
      if (!result || !result.post) {
        showError('Post not found.');
        return;
      }
      renderPost(result.post, { context: result.context, scope: result.scope });
      var relatedPools = collectRelatedPools(result);
      renderRelated(relatedPools, result.post);
    })
    .catch(function (err) {
      console.error('Failed to load article', err);
      showError('Failed to load post.');
    });
})();
