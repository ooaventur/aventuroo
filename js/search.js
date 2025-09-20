(function () {
  'use strict';

  var basePath = window.AventurOOBasePath || {
    resolve: function (value) { return value; },
    resolveAll: function (values) { return Array.isArray(values) ? values.slice() : []; },
    articleUrl: function (slug) { return slug ? '/article.html?slug=' + encodeURIComponent(slug) : '#'; },
    categoryUrl: function (slug) { return slug ? '/category.html?cat=' + encodeURIComponent(slug) : '#'; }
  };

  var ARCHIVE_SUMMARY_SOURCES = basePath.resolveAll
    ? basePath.resolveAll(['/data/archive/summary.json', 'data/archive/summary.json'])
    : ['/data/archive/summary.json', 'data/archive/summary.json'];
  var SEARCH_INDEX_ROOT = '/search-index';
  var DEFAULT_SCOPE = { parent: 'index', child: 'index' };
  var MAX_MONTHS = 12;

  var INDEX_CACHE = Object.create(null);
  var ARCHIVE_SUMMARY_PROMISE = null;

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

  function normalizeEntries(payload) {
    if (!payload) return [];
    if (Array.isArray(payload)) return payload.slice();
    if (typeof payload !== 'object') return [];
    if (Array.isArray(payload.items)) return payload.items.slice();
    if (Array.isArray(payload.entries)) return payload.entries.slice();
    if (Array.isArray(payload.results)) return payload.results.slice();
    if (Array.isArray(payload.data)) return payload.data.slice();
    return [];
  }

  function parseDateValue(value) {
    if (!value) return 0;
    var parsed = Date.parse(value);
    return isNaN(parsed) ? 0 : parsed;
  }

  function formatDate(dateValue) {
    if (!dateValue) return '';
    var parsed = new Date(dateValue);
    if (!isNaN(parsed.getTime())) {
      return parsed.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      });
    }
    var fallback = Date.parse(dateValue);
    if (!isNaN(fallback)) {
      return new Date(fallback).toDateString();
    }
    return String(dateValue);
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

  function removeDiacritics(value) {
    if (typeof value.normalize === 'function') {
      return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    }
    return value;
  }

  function normalizeText(value) {
    if (value == null) return '';
    var stringValue = removeDiacritics(String(value));
    return stringValue
      .toLowerCase()
      .replace(/\s+/g, ' ')
      .trim();
  }

  function tokenize(value) {
    var normalized = normalizeText(value);
    return normalized ? normalized.split(' ') : [];
  }

  function resolveScopeHint(elements) {
    var parent = '';
    var child = '';

    for (var i = 0; i < elements.length; i++) {
      var element = elements[i];
      if (!element) continue;
      if (!parent && element.getAttribute) {
        var p = element.getAttribute('data-hot-parent') || element.getAttribute('data-cat');
        if (!p && element.dataset) {
          p = element.dataset.hotParent || element.dataset.cat;
        }
        if (p) parent = slugify(p);
      }
      if (!child && element.getAttribute) {
        var c = element.getAttribute('data-hot-child') || element.getAttribute('data-sub');
        if (!c && element.dataset) {
          c = element.dataset.hotChild || element.dataset.sub;
        }
        if (c) child = slugify(c);
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
            var scopeParts = trimmedScope.split('/');
            parent = slugify(scopeParts[0]);
            child = slugify(scopeParts[scopeParts.length - 1]);
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

  function buildSearchIndexCandidates(parent, child, year, month) {
    var normalizedParent = slugify(parent) || 'index';
    var normalizedChild = child != null && child !== '' ? slugify(child) : '';
    if (!normalizedChild) normalizedChild = 'index';
    var yearMonth = padNumber(year, 4) + '-' + padNumber(month, 2);
    var segments = [normalizedParent];
    if (normalizedChild !== 'index') {
      segments.push(normalizedChild);
    }
    segments.push(yearMonth);
    var prefix = SEARCH_INDEX_ROOT.replace(/\/+$/, '');
    var joined = segments.join('/');
    var basePath = prefix ? prefix + '/' + joined : joined;
    var relative = basePath.replace(/^\//, '');
    return [
      basePath + '.json.gz',
      relative + '.json.gz',
      basePath + '.json',
      relative + '.json',
      basePath + '/index.json',
      relative + '/index.json',
      basePath + '/index.json.gz',
      relative + '/index.json.gz'
    ];
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

  function getArchiveSummary() {
    if (!ARCHIVE_SUMMARY_PROMISE) {
      ARCHIVE_SUMMARY_PROMISE = fetchSequential(ARCHIVE_SUMMARY_SOURCES)
        .catch(function (err) {
          console.warn('archive summary load error', err);
          return null;
        });
    }
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

  function loadIndexForMonth(scope, year, month) {
    var cacheKey = (scope.parent || 'index') + '::' + (scope.child || 'index') + '::' + padNumber(year, 4) + padNumber(month, 2);
    if (!INDEX_CACHE[cacheKey]) {
      var candidates = buildSearchIndexCandidates(scope.parent, scope.child, year, month);
      INDEX_CACHE[cacheKey] = fetchSequential(candidates)
        .then(function (payload) {
          return normalizeEntries(payload);
        })
        .catch(function (err) {
          console.warn('search index load error', err);
          return [];
        });
    }
    return INDEX_CACHE[cacheKey];
  }

  function ensureIndexes(scope) {
    var scopeKey = (scope.parent || 'index') + '::' + (scope.child || 'index');
    if (INDEX_CACHE[scopeKey]) {
      return INDEX_CACHE[scopeKey];
    }
    INDEX_CACHE[scopeKey] = getArchiveSummary()
      .then(function (summary) {
        var childEntry = summary ? findChildSummary(summary, scope.parent, scope.child) : null;
        var months = childEntry && Array.isArray(childEntry.months) ? childEntry.months.slice() : [];
        if (!months.length) {
          months = [{ year: new Date().getFullYear(), month: new Date().getMonth() + 1 }];
        }
        months.sort(function (a, b) {
          if (a.year === b.year) return b.month - a.month;
          return b.year - a.year;
        });
        months = months.slice(0, MAX_MONTHS);
        var promises = months.map(function (info) {
          return loadIndexForMonth(scope, info.year, info.month);
        });
        return Promise.all(promises).then(function (lists) {
          var combined = [];
          for (var i = 0; i < lists.length; i++) {
            var list = lists[i];
            if (Array.isArray(list) && list.length) {
              combined = combined.concat(list);
            }
          }
          return combined;
        });
      });
    return INDEX_CACHE[scopeKey];
  }

  function matchesQuery(entry, queryTokens) {
    if (!queryTokens.length) return true;
    var haystack = normalizeText(
      [entry.title, entry.excerpt, entry.summary, entry.category, entry.subcategory, stripHtml(entry.body)]
        .filter(Boolean)
        .join(' ')
    );
    if (!haystack) return false;
    for (var i = 0; i < queryTokens.length; i++) {
      if (haystack.indexOf(queryTokens[i]) === -1) {
        return false;
      }
    }
    return true;
  }

  function renderResults(entries, queryTokens) {
    var resultInfo = document.querySelector('.search-result');
    var resultsContainer = document.getElementById('search-results');
    if (!resultsContainer) return;

    resultsContainer.innerHTML = '';

    var filtered = entries
      .filter(function (entry) { return entry && (entry.slug || entry.title); })
      .filter(function (entry) { return matchesQuery(entry, queryTokens); })
      .sort(function (a, b) { return parseDateValue(b.date) - parseDateValue(a.date); });

    if (resultInfo) {
      if (filtered.length) {
        resultInfo.textContent = 'Found ' + filtered.length + ' result' + (filtered.length === 1 ? '' : 's') + '.';
      } else {
        resultInfo.textContent = 'No matching results found.';
      }
    }

    if (!filtered.length) {
      var wrapper = document.createElement('div');
      wrapper.className = 'col-md-12 no-search-results';
      var inner = document.createElement('div');
      inner.className = 'inner';
      var paragraph = document.createElement('p');
      paragraph.textContent = 'No matching results found.';
      inner.appendChild(paragraph);
      wrapper.appendChild(inner);
      resultsContainer.appendChild(wrapper);
      return;
    }

    filtered.forEach(function (entry) {
      var titleText = entry.title ? stripHtml(entry.title) : 'Untitled';
      var title = escapeHtml(titleText);
      var slug = entry.slug || slugify(entry.title || '');
      var link = slug ? (basePath.articleUrl ? basePath.articleUrl(slug) : '/article.html?slug=' + encodeURIComponent(slug)) : '#';
      var image = entry.cover ? (basePath.resolve ? basePath.resolve(entry.cover) : entry.cover) : (basePath.resolve ? basePath.resolve('/images/logo.png') : '/images/logo.png');
      var category = entry.category ? escapeHtml(entry.category) : '';
      var categoryLink = '#';
      if (category) {
        var catSlug = slugify(entry.category);
        categoryLink = catSlug ? (basePath.categoryUrl ? basePath.categoryUrl(catSlug) : '/category.html?cat=' + encodeURIComponent(catSlug)) : '#';
      }
      var date = entry.date ? escapeHtml(formatDate(entry.date)) : '';
      var excerptText = entry.excerpt ? stripHtml(entry.excerpt) : '';
      var excerpt = excerptText ? escapeHtml(excerptText) : '';

      var article = document.createElement('article');
      article.className = 'col-md-12 article-list';
      article.innerHTML =
        '<div class="inner">' +
          '<figure><a href="' + escapeHtml(link) + '"><img src="' + escapeHtml(image) + '" alt="' + title + '"></a></figure>' +
          '<div class="details">' +
            '<div class="detail">' +
              (category ? '<div class="category"><a href="' + escapeHtml(categoryLink) + '">' + category + '</a></div>' : '') +
              (date ? '<time>' + date + '</time>' : '') +
            '</div>' +
            '<h1><a href="' + escapeHtml(link) + '">' + title + '</a></h1>' +
            (excerpt ? '<p>' + excerpt + '</p>' : '') +
            '<footer><a class="btn btn-primary more" href="' + escapeHtml(link) + '"><div>More</div><div><i class="ion-ios-arrow-thin-right"></i></div></a></footer>' +
          '</div>' +
        '</div>';
      resultsContainer.appendChild(article);
    });
  }

  function getQuery() {
    try {
      var params = new URLSearchParams(window.location.search || '');
      return params.get('q') || '';
    } catch (err) {
      return '';
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    var query = getQuery();
    var input = document.querySelector('input[name="q"]');
    if (input) {
      input.value = query;
    }

    var scope = resolveScopeHint([document.body]);

    ensureIndexes(scope)
      .then(function (entries) {
        var tokens = tokenize(query);
        renderResults(entries || [], tokens);
      })
      .catch(function (err) {
        console.error('Failed to load search indexes', err);
        renderResults([], tokenize(query));
      });
  });
})();
