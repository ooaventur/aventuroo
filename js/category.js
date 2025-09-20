(function () {
  var basePath = window.AventurOOBasePath || {
    resolve: function (value) { return value; },
    resolveAll: function (values) { return Array.isArray(values) ? values.slice() : []; },
    articleUrl: function (slug) { return slug ? '/article.html?slug=' + encodeURIComponent(slug) : '#'; },
    categoryUrl: function (slug) {
      if (!slug) return '#';
      return '/category.html?cat=' + encodeURIComponent(slug);
    },
    sectionUrl: function (slug) {
      if (!slug) return '#';
      var normalized = String(slug).trim().replace(/^\/+|\/+$/g, '');
      return normalized ? '/' + normalized + '/' : '#';
    }
  };

  var DEFAULT_IMAGE = basePath.resolve ? basePath.resolve('/images/logo.png') : '/images/logo.png';
  var HOME_URL = basePath.resolve ? basePath.resolve('/') : '/';
  var LEGACY_POSTS_SOURCES = ['/data/posts.json', 'data/posts.json'];

  var TAXONOMY_SOURCES = ['/data/taxonomy.json', 'data/taxonomy.json'];
  var HOT_SUMMARY_SOURCES = ['/data/hot/summary.json', 'data/hot/summary.json'];
  var ARCHIVE_SUMMARY_SOURCES = ['/data/archive/summary.json', 'data/archive/summary.json'];
  var HOT_SHARD_ROOT = '/data/hot';
  var ARCHIVE_SHARD_ROOT = '/data/archive';
  var DEFAULT_SCOPE = { parent: 'index', child: 'index' };












  function fetchSequential(urls) {
    if (!window.AventurOODataLoader || typeof window.AventurOODataLoader.fetchSequential !== 'function') {
      return Promise.reject(new Error('Data loader is not available'));
    }
    return window.AventurOODataLoader.fetchSequential(urls);
  }

  function slugify(s) {
    return (s || '')
      .toString()
      .trim()
      .toLowerCase()
      .replace(/\.html?$/i, '')      // heq .html / .htm
      .replace(/&/g, 'and')
      .replace(/[_\W]+/g, '-')       // gjithçka jo-alfanumerike ose _ -> -
      .replace(/^-+|-+$/g, '');
  }
  function resolvePostCategorySlugs(post) {
    if (!post) return [];

    var slugs = [];
    var seen = Object.create(null);













    function appendSlug(value) {
      if (value == null) return;
      var trimmed = String(value).trim();
      if (!trimmed) return;
      var normalized = slugify(trimmed);
      if (!normalized || seen[normalized]) return;
      seen[normalized] = true;
      slugs.push(normalized);
    }

    var rawSlug = post.category_slug;
    if (rawSlug != null && String(rawSlug).trim()) {
      appendSlug(rawSlug);

      var rawSegments = String(rawSlug).split('/');
      if (rawSegments.length > 1) {
        var lastRawSegment = rawSegments[rawSegments.length - 1];
        appendSlug(lastRawSegment);
      }
    }

    var subcategory = post.subcategory;
    appendSlug(subcategory);

    if (subcategory != null && String(subcategory).indexOf('/') !== -1) {
      var subSegments = String(subcategory).split('/');
      var lastSubSegment = subSegments[subSegments.length - 1];
      appendSlug(lastSubSegment);
    }

    var category = post.category;
    appendSlug(category);
    if (category != null && String(category).indexOf('/') !== -1) {
      var categorySegments = String(category).split('/');
      var lastCategorySegment = categorySegments[categorySegments.length - 1];
      appendSlug(lastCategorySegment);
    }

    return slugs;
  }

  function resolvePostCategorySlug(post, preferredSlug) {
    var slugs = resolvePostCategorySlugs(post);
    if (!slugs.length) return '';

    var preferred = preferredSlug ? slugify(preferredSlug) : '';
    if (preferred) {
      for (var i = 0; i < slugs.length; i++) {
        if (slugs[i] === preferred) {
          return slugs[i];
        }
      }
    }

    return slugs[0];
  }


  var LABEL_PRIORITY_SUBCATEGORY = 1;
  var LABEL_PRIORITY_SLUG = 2;
  var LABEL_PRIORITY_CATEGORY = 3;
  var LABEL_PRIORITY_FALLBACK = 99;

  function resolvePostCategoryLabelInfo(post) {
    if (!post) {
      return { label: '', priority: LABEL_PRIORITY_FALLBACK };
    }

    var subcategory = post.subcategory;
    if (subcategory != null && String(subcategory).trim()) {
      return {
        label: String(subcategory).trim(),
        priority: LABEL_PRIORITY_SUBCATEGORY
      };
    }

    var rawSlug = post.category_slug;
    if (rawSlug != null && String(rawSlug).trim()) {
      var slugValue = String(rawSlug).trim();
      var normalized = slugify(slugValue);
      var formatted = normalized
        ? resolveCategoryLabelFromSlug(normalized, slugValue)
        : slugValue;
      return {
        label: formatted,
        priority: LABEL_PRIORITY_SLUG
      };
    }

    var category = post.category;
    if (category != null && String(category).trim()) {
      var categoryValue = String(category).trim();
      var normalizedCategory = slugify(categoryValue);
      var formattedCategory = normalizedCategory
        ? resolveCategoryLabelFromSlug(normalizedCategory, categoryValue)
        : categoryValue;
      return {
        label: formattedCategory,
        priority: LABEL_PRIORITY_CATEGORY
      };
    }

    return { label: '', priority: LABEL_PRIORITY_FALLBACK };
  }

  function resolvePostCategoryLabel(post) {
    return resolvePostCategoryLabelInfo(post).label;
  }


  function titleize(slug) {
    return (slug || '')
      .split('-')
      .map(function (w) { return w.charAt(0).toUpperCase() + w.slice(1); })
      .join(' ');
  }
  var CATEGORY_TITLE_LOOKUP = Object.create(null);
  var CATEGORY_PARENT_LOOKUP = Object.create(null);
  CATEGORY_PARENT_LOOKUP.index = { parent: 'index', child: 'index' };















  function registerCategoryParent(entry) {
    if (!entry || typeof entry !== 'object') return;
    var slug = slugify(entry.slug);
    if (!slug) return;

    var parent = '';
    var group = entry.group;
    if (Array.isArray(group)) {
      for (var i = 0; i < group.length; i++) {
        var candidate = slugify(group[i]);
        if (candidate) {
          parent = candidate;
          break;
        }
      }
    } else if (typeof group === 'string') {
      parent = slugify(group);
    }

    if (!parent) {
      parent = slug;
    }

    if (!CATEGORY_PARENT_LOOKUP[parent]) {
      CATEGORY_PARENT_LOOKUP[parent] = { parent: parent, child: 'index' };
    }

    var child = parent === slug ? 'index' : slug;
    CATEGORY_PARENT_LOOKUP[slug] = { parent: parent, child: child };

    if (typeof entry.slug === 'string' && entry.slug.indexOf('/') !== -1) {
      var normalizedComposite = slugify(entry.slug);
      if (normalizedComposite && !CATEGORY_PARENT_LOOKUP[normalizedComposite]) {
        CATEGORY_PARENT_LOOKUP[normalizedComposite] = { parent: parent, child: child };
      }
    }
  }

  function populateCategoryLookup(data) {
    if (!data || typeof data !== 'object') return;
    var categories = Array.isArray(data.categories) ? data.categories : [];
    categories.forEach(function (entry) {
      if (!entry || typeof entry !== 'object') return;
      var slug = slugify(entry.slug);
      if (!slug) return;
      var title = entry.title != null ? String(entry.title).trim() : '';
      if (!title) {
        title = titleize(slug);
      }
      CATEGORY_TITLE_LOOKUP[slug] = title;
      registerCategoryParent(entry);






















    });
  }

  function resolveCategoryLabelFromSlug(slug, rawLabel) {
    var normalizedSlug = slugify(slug);
    var trimmed = rawLabel == null ? '' : String(rawLabel).trim();

    if (!normalizedSlug) {
      return trimmed;
    }

    var lookupTitle = CATEGORY_TITLE_LOOKUP[normalizedSlug];
    if (lookupTitle) {
      return lookupTitle;
    }

    if (!trimmed) {
      return titleize(normalizedSlug);
    }

    var slugFromLabel = slugify(trimmed);
    if (slugFromLabel === normalizedSlug) {
      var pretty = titleize(normalizedSlug);
      var lowerTrimmed = trimmed.toLowerCase();
      if (
        lowerTrimmed === normalizedSlug ||
        trimmed === pretty ||
        lowerTrimmed === pretty.toLowerCase()
      ) {
        return pretty;
      }
    }

    return trimmed;
  }

  var HTML_ESCAPE = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  };

  function escapeHtml(value) {
    return (value == null ? '' : String(value)).replace(/[&<>"']/g, function (ch) {
      return HTML_ESCAPE[ch];
    });
  }

  function getPostTimestamp(post) {
    if (!post) return 0;
    var candidates = [post.date, post.updated_at, post.published_at, post.created_at];
    for (var i = 0; i < candidates.length; i++) {
      var value = candidates[i];
      if (!value) continue;
      var time = Date.parse(value);
      if (!isNaN(time)) return time;
    }
    return 0;
  }

  function formatDateString(dateValue) {
    if (!dateValue) return '';
    var raw = String(dateValue);
    var parts = raw.split('T');
    return parts[0] || raw;
  }

  function buildArticleUrl(post) {
    if (!post || !post.slug) return '#';
    var slug = encodeURIComponent(post.slug);
    if (basePath.articleUrl) {
      return basePath.articleUrl(post.slug);
    }
    return slug ? '/article.html?slug=' + slug : '#';
  }

  function buildCategoryUrl(slug) {
    if (!slug) return '#';
    if (basePath.categoryUrl) {
      return basePath.categoryUrl(slug);
    }
    return '/category.html?cat=' + encodeURIComponent(slug);
  }

  var HOT_SUMMARY_PROMISE = null;
  var ARCHIVE_SUMMARY_PROMISE = null;
  var HOT_SHARD_CACHE = Object.create(null);
  var ARCHIVE_SHARD_CACHE = Object.create(null);

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
    var result = [];
    for (var i = 0; i < posts.length; i++) {
      var post = posts[i];
      var key = resolvePostKey(post);
      if (key && seen[key]) continue;
      if (key) seen[key] = true;
      result.push(post);
    }
    return result;
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

  function buildShardCandidates(root, parent, child) {
    var normalizedParent = slugify(parent) || 'index';
    var normalizedChild = child != null && child !== '' ? slugify(child) : '';
    if (!normalizedChild) normalizedChild = 'index';
    var segments = [normalizedParent];
    if (normalizedChild !== 'index') {
      segments.push(normalizedChild);
    }
    var joined = segments.join('/');
    var prefix = typeof root === 'string' ? root.replace(/\/+$/, '') : '';
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

  function buildArchiveMonthCandidates(parent, child, year, month) {
    var normalizedParent = slugify(parent) || 'index';
    var normalizedChild = child != null && child !== '' ? slugify(child) : '';
    if (!normalizedChild) normalizedChild = 'index';
    var segments = [normalizedParent];
    if (normalizedChild !== 'index') {
      segments.push(normalizedChild);
    }
    segments.push(padNumber(year, 4));
    segments.push(padNumber(month, 2));
    var prefix = typeof ARCHIVE_SHARD_ROOT === 'string' ? ARCHIVE_SHARD_ROOT.replace(/\/+$/, '') : '';
    var joined = segments.join('/');
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
    if (HOT_SHARD_CACHE[scopeKey]) {
      return HOT_SHARD_CACHE[scopeKey];
    }
    var candidates = buildShardCandidates(HOT_SHARD_ROOT, parent, child);
    HOT_SHARD_CACHE[scopeKey] = fetchSequential(candidates)
      .then(function (payload) {
        return sortPosts(normalizePostsPayload(payload));
      })
      .catch(function (err) {
        delete HOT_SHARD_CACHE[scopeKey];
        throw err;
      });
    return HOT_SHARD_CACHE[scopeKey];
  }

  function fetchArchiveShard(parent, child, year, month) {
    var scopeKey = (parent || 'index') + '::' + (child || 'index') + '::' + padNumber(year, 4) + padNumber(month, 2);
    if (ARCHIVE_SHARD_CACHE[scopeKey]) {
      return ARCHIVE_SHARD_CACHE[scopeKey];
    }
    var candidates = buildArchiveMonthCandidates(parent, child, year, month);
    ARCHIVE_SHARD_CACHE[scopeKey] = fetchSequential(candidates)
      .then(function (payload) {
        return sortPosts(normalizePostsPayload(payload));
      })
      .catch(function (err) {
        delete ARCHIVE_SHARD_CACHE[scopeKey];
        throw err;
      });
    return ARCHIVE_SHARD_CACHE[scopeKey];
  }

  function getHotSummary() {
    if (HOT_SUMMARY_PROMISE) {
      return HOT_SUMMARY_PROMISE;
    }
    HOT_SUMMARY_PROMISE = fetchSequential(HOT_SUMMARY_SOURCES)
      .catch(function (err) {
        console.warn('hot summary load error', err);
        return null;
      });
    return HOT_SUMMARY_PROMISE;
  }

  function getArchiveSummary() {
    if (ARCHIVE_SUMMARY_PROMISE) {
      return ARCHIVE_SUMMARY_PROMISE;
    }
    ARCHIVE_SUMMARY_PROMISE = fetchSequential(ARCHIVE_SUMMARY_SOURCES)
      .catch(function (err) {
        console.warn('archive summary load error', err);
        return null;
      });
    return ARCHIVE_SUMMARY_PROMISE;
  }

  function findParentSummary(summary, parent) {
    if (!summary || typeof summary !== 'object') return null;
    var parents = Array.isArray(summary.parents) ? summary.parents : [];
    var normalized = slugify(parent);
    for (var i = 0; i < parents.length; i++) {
      var entry = parents[i];
      if (!entry) continue;
      var entryParent = slugify(entry.parent || entry.slug || '');
      if (entryParent === normalized) {
        return entry;
      }
    }
    return null;
  }

  function findChildSummary(summary, parent, child) {
    var parentEntry = findParentSummary(summary, parent);
    if (!parentEntry || !Array.isArray(parentEntry.children)) {
      return null;
    }
    var normalized = child === 'index' || !child ? 'index' : slugify(child);
    for (var i = 0; i < parentEntry.children.length; i++) {
      var entry = parentEntry.children[i];
      if (!entry) continue;
      var entryChild = entry.child === 'index' ? 'index' : slugify(entry.child || entry.slug || '');
      if (entryChild === normalized) {
        return entry;
      }
    }
    return null;
  }

  function resolveScopeFromSlug(slug) {
    if (!slug) {
      return DEFAULT_SCOPE;
    }
    var normalized = slugify(slug);
    if (!normalized) {
      return DEFAULT_SCOPE;
    }
    var mapping = CATEGORY_PARENT_LOOKUP[normalized];
    if (mapping) {
      return { parent: mapping.parent || 'index', child: mapping.child || 'index' };
    }
    if (normalized.indexOf('/') !== -1) {
      var parts = normalized.split('/');
      var parent = parts[0] || 'index';
      var child = parts[parts.length - 1] || 'index';
      return { parent: parent, child: child };
    }
    return { parent: normalized, child: 'index' };
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
      var slugs = resolvePostCategorySlugs(post);
      if (slugs.indexOf(child) !== -1) return true;
      return false;
    }

    if (!parent || parent === 'index') {
      return true;
    }

    var parentSlug = getPostParentSlug(post);
    if (parentSlug && parentSlug === parent) return true;

    var relatedSlugs = resolvePostCategorySlugs(post);
    for (var i = 0; i < relatedSlugs.length; i++) {
      var slug = relatedSlugs[i];
      var mapping = CATEGORY_PARENT_LOOKUP[slug];
      if (mapping && mapping.parent === parent) {
        return true;
      }
    }
    return false;
  }

  function filterPostsByScope(posts, scope) {
    if (!Array.isArray(posts)) return [];
    return posts.filter(function (post) { return matchesScope(post, scope); });
  }

  function loadAdditionalArchivePosts(scope, existingCount, targetCount, archiveSummary) {
    if (!archiveSummary || !scope) {
      return Promise.resolve([]);
    }
    var childInfo = findChildSummary(archiveSummary, scope.parent, scope.child);
    if (!childInfo || !Array.isArray(childInfo.months) || !childInfo.months.length) {
      return Promise.resolve([]);
    }
    var months = childInfo.months.slice();
    var collected = [];
    var index = 0;

    function next() {
      if (existingCount + collected.length >= targetCount) {
        return Promise.resolve(collected);
      }
      if (index >= months.length) {
        return Promise.resolve(collected);
      }
      var info = months[index++] || {};
      var year = info.year != null ? info.year : 1970;
      var month = info.month != null ? info.month : 1;
      return fetchArchiveShard(scope.parent, scope.child, year, month)
        .then(function (items) {
          if (Array.isArray(items) && items.length) {
            collected = collected.concat(items);
          }
        })
        .catch(function (err) {
          console.warn('archive shard load error', err);
        })
        .then(next);
    }

    return next();
  }

  function computePerPage(hotSummary, archiveSummary) {
    if (hotSummary && typeof hotSummary.per_page === 'number' && hotSummary.per_page > 0) {
      return hotSummary.per_page;
    }
    if (archiveSummary && typeof archiveSummary.per_page === 'number' && archiveSummary.per_page > 0) {
      return archiveSummary.per_page;
    }
    return 12;
  }

  function computeTotalItems(hotSummary, archiveSummary, scope, fallbackCount) {
    var total = 0;
    if (hotSummary) {
      var hotEntry = findChildSummary(hotSummary, scope.parent, scope.child);
      if (hotEntry && typeof hotEntry.items === 'number') {
        total += hotEntry.items;
      }
    }
    if (archiveSummary) {
      var archiveEntry = findChildSummary(archiveSummary, scope.parent, scope.child);
      if (archiveEntry && typeof archiveEntry.items === 'number') {
        total += archiveEntry.items;
      }
    }
    if (!total && typeof fallbackCount === 'number' && fallbackCount > 0) {
      total = fallbackCount;
    }
    return total;
  }

  var url = new URL(window.location.href);

  function getCatSub() {
    var catParam = url.searchParams.get('cat');
    var subParam = url.searchParams.get('sub');

    var cat = slugify(catParam);
    var alias = slugify(subParam);
    var label = '';

    if (alias) {
      cat = alias;
      label = subParam || '';
    } else if (catParam) {
      label = catParam;
    }

    if (!cat) {
      var pathName = window.location && window.location.pathname
        ? window.location.pathname
        : '';
      var trimmedPath = pathName.replace(/\/+$/, '');
      var segments = trimmedPath.split('/');
      for (var i = segments.length - 1; i >= 0; i--) {
        var segment = segments[i];
        if (!segment) continue;

        var decoded = segment;
        try {
          decoded = decodeURIComponent(segment);
        } catch (err) {
          // ignore decode errors and fall back to the raw segment
        }

        var cleaned = decoded.replace(/\.html?$/i, '');
        if (!cleaned || /^index$/i.test(cleaned)) continue;

        var derived = slugify(cleaned);
        if (derived) {
          cat = derived;
          label = cleaned;
          break;
        }
      }
    }

    // opsionale: lexo edhe data-attr në <body data-cat="..." data-sub="...">
    var body = document.body;
    if (!cat && body.dataset.cat) {
      cat = slugify(body.dataset.cat);
      label = body.dataset.cat;
    }
    if (!cat && body.dataset.sub) {
      cat = slugify(body.dataset.sub);
      label = body.dataset.sub;
    }

    if (label) {
      label = String(label)
        .replace(/[_-]+/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
    }
    label = resolveCategoryLabelFromSlug(cat, label);

    return { cat: cat, label: label };
  }

  function patchHeader(ctx) {
    var cat = ctx && ctx.cat ? ctx.cat : '';
    var label = '';
    if (ctx && ctx.label) {
      label = String(ctx.label).trim();
    }
    var resolvedLabel = resolveCategoryLabelFromSlug(cat, label);
    if (ctx && resolvedLabel !== label) {
      ctx.label = resolvedLabel;
    }
    label = resolvedLabel;

    var bc = document.querySelector('.breadcrumb');
    if (bc) {
      var parts = ['<li><a href="' + HOME_URL + '">Home</a></li>'];
      if (cat) {
        var catUrl = buildCategoryUrl(cat);
        parts.push('<li class="active"><a href="' + escapeHtml(catUrl) + '">' + escapeHtml(label) + '</a></li>');
      }
      bc.innerHTML = parts.join('');
    }
    var h1 = document.querySelector('.page-title');
    if (h1) {
      h1.textContent = cat ? 'Category: ' + label : 'Category';
    }
    var subt = document.querySelector('.page-subtitle');
    if (subt) {
      subt.innerHTML = cat
        ? 'Showing all posts with category <i>' + escapeHtml(label) + '</i>'
        : 'Showing all posts.';
    }
  }

  function renderPost(p) {
    var dateTxt = (p.date || '').split('T')[0];
    var art = document.createElement('article');
    art.className = 'col-md-12 article-list';
    var articleUrl = buildArticleUrl(p);
    var hasCover = p.cover && String(p.cover).trim();
    var coverSrc = hasCover ? (basePath.resolve ? basePath.resolve(p.cover) : p.cover) : DEFAULT_IMAGE;
    var coverAlt = (p.title ? String(p.title) : 'AventurOO') + ' cover image';
    var figureClass = hasCover ? '' : ' class="no-cover"';
    var figureHtml =
      '<figure' + figureClass + '>' +
        '<a href="' + articleUrl + '">' +
          '<img src="' + escapeHtml(coverSrc) + '" alt="' + escapeHtml(coverAlt) + '">' +
        '</a>' +
      '</figure>';
    var categoryName = resolvePostCategoryLabel(p);
    var preferredSlug = ctx && ctx.cat ? ctx.cat : '';
    var categorySlug = resolvePostCategorySlug(p, preferredSlug);
    var categoryLink = categorySlug ? buildCategoryUrl(categorySlug) : '#';
    var categoryHtml = categoryName
      ? '<div class="category"><a href="' + escapeHtml(categoryLink) + '">' + escapeHtml(categoryName) + '</a></div>'
      : '';
    art.innerHTML =
      '<div class="inner">' +
        figureHtml +
        '<div class="details">' +
          '<div class="detail">' +
            categoryHtml +
            '<div class="time">' + (dateTxt || '') + '</div>' +
          '</div>' +
          '<h1><a href="' + articleUrl + '">' +
            (p.title || '') + '</a></h1>' +
          '<p>' + (p.excerpt || '') + '</p>' +
          '<footer>' +
            '<a class="btn btn-primary more" href="' + articleUrl + '">' +
              '<div>More</div><div><i class="ion-ios-arrow-thin-right"></i></div>' +
            '</a>' +
          '</footer>' +
        '</div>' +
      '</div>';
    return art;
  }

  function renderList(posts) {
    var box = document.getElementById('post-list');
    if (!box) return;
    box.innerHTML = '';
    if (!posts.length) {
      box.innerHTML = '<p class="lead">No posts yet for this category.</p>';
      return;
    }
    posts.forEach(function (p) { box.appendChild(renderPost(p)); });
  }


  function createSidebarArticle(post, variant) {
    var article = document.createElement('article');
    var articleUrl = buildArticleUrl(post);
    var title = escapeHtml(post && post.title ? post.title : '');
    var rawLabel = resolvePostCategoryLabel(post);
    var category = escapeHtml(rawLabel);
    var preferredSlug = ctx && ctx.cat ? ctx.cat : '';
    var categorySlug = resolvePostCategorySlug(post, preferredSlug);
    var categoryHref = categorySlug ? buildCategoryUrl(categorySlug) : '#';
    var categoryAnchor = category
      ? '<div class="category"><a href="' + escapeHtml(categoryHref) + '">' + category + '</a></div>'
      : '';
    var excerpt = escapeHtml(post && post.excerpt ? post.excerpt : '');
    var dateTxt = escapeHtml(formatDateString(post && post.date));
    var hasCover = post && post.cover;
    var coverSrc = hasCover ? (basePath.resolve ? basePath.resolve(post.cover) : post.cover) : DEFAULT_IMAGE;
    var cover = escapeHtml(coverSrc);
    var figureClass = hasCover ? '' : ' class="no-cover"';
    if (variant === 'full') {
      article.className = 'article-fw';
      article.innerHTML =
        '<div class="inner">' +
          '<figure' + figureClass + '>' +
            '<a href="' + articleUrl + '">' +
              '<img src="' + cover + '" alt="' + title + '">' +
            '</a>' +
          '</figure>' +
          '<div class="details">' +
            '<div class="detail">' +
              categoryAnchor +
              '<div class="time">' + dateTxt + '</div>' +
            '</div>' +
            '<h1><a href="' + articleUrl + '">' + title + '</a></h1>' +
            '<p>' + excerpt + '</p>' +
          '</div>' +
        '</div>';
    } else {
      article.className = 'article-mini';
      article.innerHTML =
        '<div class="inner">' +
          '<figure' + figureClass + '>' +
            '<a href="' + articleUrl + '">' +
              '<img src="' + cover + '" alt="' + title + '">' +
            '</a>' +
          '</figure>' +
          '<div class="padding">' +
            '<h1><a href="' + articleUrl + '">' + title + '</a></h1>' +
            '<div class="detail">' +
              categoryAnchor +
              '<div class="time">' + dateTxt + '</div>' +
            '</div>' +
          '</div>' +
        '</div>';
    }

    return article;
  }

  function createLineDivider() {
    var line = document.createElement('div');
    line.className = 'line';
    return line;
  }

  function appendFallbackMessage(container, text) {
    if (!container) return;
    var message = document.createElement('p');
    message.className = 'text-muted sidebar-fallback';
    message.textContent = text;
    container.appendChild(message);
  }

  function renderRecentSidebar(posts) {
    var container = document.getElementById('sidebar-recent-posts');
    if (!container) return;
    container.innerHTML = '';

    if (!posts.length) {
      appendFallbackMessage(container, 'No recent posts available.');
      return;
    }

    var first = posts[0];
    if (first) {
      container.appendChild(createSidebarArticle(first, 'full'));
    }

    var minis = posts.slice(1, 3);
    if (minis.length) {
      container.appendChild(createLineDivider());
      minis.forEach(function (post) {
        container.appendChild(createSidebarArticle(post, 'mini'));
      });
    }

    if (posts.length < 3) {
      appendFallbackMessage(container, 'Only ' + posts.length + ' recent post' + (posts.length === 1 ? '' : 's') + ' available.');
    }
  }

  function renderMiniSidebar(posts) {
    var container = document.getElementById('sidebar-mini-articles');
    if (!container) return;
    container.innerHTML = '';

    if (!posts.length) {
      appendFallbackMessage(container, 'No additional stories available.');
      return;
    }

    posts.forEach(function (post) {
      container.appendChild(createSidebarArticle(post, 'mini'));
    });

    if (posts.length < 10) {
      appendFallbackMessage(container, 'No more stories available.');
    }
  }

  function resolveRequestedPage(totalPages) {
    var pageParam = parseInt(url.searchParams.get('page'), 10);
    var page = !isNaN(pageParam) && pageParam > 0 ? pageParam : 1;
    if (totalPages > 0 && page > totalPages) {
      page = totalPages;
    }
    if (page < 1) page = totalPages > 0 ? 1 : 1;
    return page;
  }

  function updateLabelFromPosts(posts) {
    if (!ctx.cat || !Array.isArray(posts) || !posts.length) {
      return;
    }
    var bestLabelInfo = null;
    for (var i = 0; i < posts.length; i++) {
      var info = resolvePostCategoryLabelInfo(posts[i]);
      if (!info.label) continue;
      if (!bestLabelInfo || info.priority < bestLabelInfo.priority) {
        bestLabelInfo = info;
      }
      if (bestLabelInfo && bestLabelInfo.priority === LABEL_PRIORITY_SUBCATEGORY) {
        break;
      }
    }

    if (bestLabelInfo && bestLabelInfo.label) {
      var currentLabel = ctx.label ? String(ctx.label).trim() : '';
      if (!currentLabel || slugify(currentLabel) === ctx.cat) {
        ctx.label = bestLabelInfo.label;
        patchHeader(ctx);
      }
    }
  }

  function renderCategoryDataset(dataset) {
    dataset = dataset || {};
    var filtered = Array.isArray(dataset.filtered) ? dataset.filtered.slice() : [];
    var allPosts = Array.isArray(dataset.allPosts) ? dataset.allPosts.slice() : filtered.slice();
    var perPage = dataset.perPage || 12;
    if (perPage <= 0) perPage = 12;
    var totalItems = typeof dataset.totalItems === 'number' ? dataset.totalItems : filtered.length;
    if (totalItems < filtered.length) {
      totalItems = filtered.length;
    }
    var totalPages = dataset.totalPages != null ? dataset.totalPages : (perPage > 0 ? Math.ceil(totalItems / perPage) : 0);
    if (totalPages < 0) totalPages = 0;
    var page = dataset.page || resolveRequestedPage(totalPages);
    if (totalPages > 0 && page > totalPages) {
      page = totalPages;
    }
    if (page < 1) page = totalPages > 0 ? 1 : 1;

    updateLabelFromPosts(filtered);

    renderRecentSidebar(allPosts.slice(0, 3));
    renderMiniSidebar(allPosts.slice(3, 13));

    var startIndex = (page - 1) * perPage;
    var pagedPosts = filtered.slice(startIndex, startIndex + perPage);
    renderList(pagedPosts);

    if (typeof renderPagination === 'function') {
      var baseQuery = dataset.baseQuery != null ? dataset.baseQuery : (ctx.cat ? '?cat=' + encodeURIComponent(ctx.cat) : '');
      renderPagination('pagination', totalItems, perPage, page, baseQuery);
    }

    var infoBox = document.getElementById('pagination-info');
    if (infoBox) {
      var displayPage = totalPages === 0 ? 0 : page;
      infoBox.textContent = 'Showing ' + pagedPosts.length + ' results of ' + totalItems + ' — Page ' + displayPage + ' of ' + totalPages;
    }
  }

  function loadLegacyDataset() {
    return fetchSequential(LEGACY_POSTS_SOURCES)
      .then(function (all) {
        all = Array.isArray(all) ? all : [];
        var allSorted = sortPosts(all);
        var filtered = ctx.cat
          ? all.filter(function (p) {
              var slugs = resolvePostCategorySlugs(p);
              return slugs.indexOf(ctx.cat) !== -1;
            })
          : all.slice();
        filtered = sortPosts(filtered);
        var perPage = 12;
        var totalItems = filtered.length;
        var totalPages = perPage > 0 ? Math.ceil(totalItems / perPage) : 0;
        var page = resolveRequestedPage(totalPages);
        var dataset = {
          filtered: filtered,
          allPosts: allSorted,
          perPage: perPage,
          totalItems: totalItems,
          totalPages: totalPages,
          page: page,
          baseQuery: ctx.cat ? '?cat=' + encodeURIComponent(ctx.cat) : ''
        };
        renderCategoryDataset(dataset);
      });
  }

  function loadHotCategory() {
    var scope = resolveScopeFromSlug(ctx.cat);
    return Promise.all([getHotSummary(), getArchiveSummary()])
      .then(function (summaries) {
        var hotSummary = summaries[0];
        var archiveSummary = summaries[1];
        return fetchHotShard(scope.parent, scope.child)
          .then(function (hotPosts) {
            var filteredHot = filterPostsByScope(hotPosts, scope);
            var sortedHot = sortPosts(filteredHot);
            var perPage = computePerPage(hotSummary, archiveSummary);
            if (!perPage || perPage <= 0) perPage = 12;
            var fallbackCount = sortedHot.length;
            var totalItems = computeTotalItems(hotSummary, archiveSummary, scope, fallbackCount);
            var totalPages = perPage > 0 ? Math.ceil(totalItems / perPage) : 0;
            if (!totalItems && sortedHot.length) {
              totalItems = sortedHot.length;
              totalPages = perPage > 0 ? Math.ceil(totalItems / perPage) : 0;
            }
            var page = resolveRequestedPage(totalPages);
            var targetCount = page > 0 ? page * perPage : perPage;
            if (!targetCount || targetCount < perPage) {
              targetCount = perPage;
            }
            return loadAdditionalArchivePosts(scope, sortedHot.length, targetCount, archiveSummary)
              .then(function (archivePosts) {
                var filteredArchive = filterPostsByScope(archivePosts, scope);
                var combined = dedupePosts(sortPosts(sortedHot.concat(filteredArchive)));
                if (!totalItems) {
                  totalItems = combined.length;
                  totalPages = perPage > 0 ? Math.ceil(totalItems / perPage) : 0;
                  page = resolveRequestedPage(totalPages);
                }
                var dataset = {
                  filtered: combined,
                  allPosts: combined,
                  perPage: perPage,
                  totalItems: totalItems,
                  totalPages: totalPages,
                  page: page,
                  baseQuery: ctx.cat ? '?cat=' + encodeURIComponent(ctx.cat) : ''
                };
                renderCategoryDataset(dataset);
              });
          });
      });
  }

  var ctx = getCatSub();
  patchHeader(ctx);

  var taxonomyPromise = fetchSequential(TAXONOMY_SOURCES)
    .then(function (taxonomy) {
      populateCategoryLookup(taxonomy);
    })
    .catch(function (err) {
      console.warn('taxonomy load error', err);
    })
    .then(function () {
      var updatedLabel = resolveCategoryLabelFromSlug(ctx.cat, ctx.label);
      if (updatedLabel !== ctx.label) {
        ctx.label = updatedLabel;
        patchHeader(ctx);
      }
    });

  taxonomyPromise
    .then(function () {
      return loadHotCategory()
        .catch(function (hotErr) {
          console.warn('hot category load error', hotErr);
          return loadLegacyDataset()
            .catch(function (legacyErr) {
              console.error('legacy category load error', legacyErr);
            });
        });
    })
    .catch(function (err) {
      console.error('category load error', err);
    });
})();
