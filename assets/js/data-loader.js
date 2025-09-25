(function (window, document) {
  'use strict';

  if (!window || !document) {
    return;
  }

  var fetchFn = typeof window.fetch === 'function' ? window.fetch.bind(window) : null;
  var baseHelper = window.AventurOOBasePath || null;
  var archiveSummaryPromise = null;
  var hotCategoryAliasesPromise = null;
  var HOT_ALIAS_DEFAULT_CHILD = 'general';
  var HOT_ALIAS_MANIFEST_PATH = '/data/hot/category_aliases.json';
  var categoryState = null;

  function resolve(path) {
    if (typeof path !== 'string') {
      return path;
    }
    if (baseHelper && typeof baseHelper.resolve === 'function') {
      return baseHelper.resolve(path);
    }
    return path;
  }

  var DEFAULT_IMAGE = resolve('/images/logo.png');
  var MAX_CATEGORY_ARCHIVE_DAYS = 5;

  function ready(callback) {
    if (typeof callback !== 'function') {
      return;
    }
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', callback, false);
    } else {
      callback();
    }
  }

  function getString(value) {
    if (value == null) {
      return '';
    }
    if (typeof value === 'string') {
      return value;
    }
    if (typeof value === 'number') {
      return String(value);
    }
    return '';
  }

  function fetchJson(path, options) {
    if (!fetchFn) {
      return Promise.reject(new Error('Fetch API is not available.'));
    }
    var url = resolve(path);
    var settings = { credentials: 'same-origin' };
    if (options && typeof options === 'object') {
      for (var key in options) {
        if (Object.prototype.hasOwnProperty.call(options, key)) {
          settings[key] = options[key];
        }
      }
    }
    return fetchFn(url, settings).then(function (response) {
      if (!response || !response.ok) {
        var status = response ? response.status : '0';
        throw new Error('Request failed with status ' + status);
      }
      return response.text().then(function (text) {
        if (text == null) {
          return null;
        }
        var sanitized = String(text).replace(/^[\uFEFF\u200B]+/, '').trim();
        if (!sanitized) {
          return null;
        }
        try {
          return JSON.parse(sanitized);
        } catch (err) {
          err.message = 'Could not parse JSON from ' + url + ': ' + err.message;
          throw err;
        }
      });
    });
  }

  function getHotCategoryAliases() {
    if (!hotCategoryAliasesPromise) {
      hotCategoryAliasesPromise = fetchJson(HOT_ALIAS_MANIFEST_PATH, { cache: 'no-store' })
        .catch(function (err) {
          console.warn('Hot category aliases load failed:', err);
          return null;
        });
    }
    return hotCategoryAliasesPromise;
  }

  function resolveHotFallbackPath(slug) {
    var normalizedSlug = normalizeSlug(slug);
    if (!normalizedSlug) {
      return Promise.resolve('');
    }
    return getHotCategoryAliases().then(function (config) {
      var aliasValue = '';
      if (config && config.aliases && typeof config.aliases === 'object') {
        var aliasKey = normalizedSlug + '/index';
        if (Object.prototype.hasOwnProperty.call(config.aliases, aliasKey)) {
          aliasValue = getString(config.aliases[aliasKey]);
        }
      }
      var fallbackTarget;
      if (aliasValue) {
        fallbackTarget = normalizeSlug(aliasValue);
      }
      if (!fallbackTarget) {
        var standardChild = config && config.standard_child ? normalizeSlug(config.standard_child) : '';
        if (!standardChild) {
          standardChild = HOT_ALIAS_DEFAULT_CHILD;
        }
        fallbackTarget = normalizedSlug + '/' + standardChild;
      }
      if (!fallbackTarget) {
        return '';
      }
      return '/data/hot/' + fallbackTarget + '/index.json';
    });
  }

  function normalizeSlug(value) {
    if (value == null) {
      return '';
    }
    var str = String(value).trim();
    if (!str) {
      return '';
    }
    var lowered = str.toLowerCase();
    if (lowered.indexOf('/') !== -1) {
      var segments = lowered.split('/');
      var cleaned = [];
      for (var i = 0; i < segments.length; i++) {
        var part = slugifySegment(segments[i]);
        if (part) {
          cleaned.push(part);
        }
      }
      return cleaned.join('/');
    }
    if (/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(lowered)) {
      return lowered;
    }
    return slugifySegment(lowered);
  }

  function slugifySegment(value) {
    return String(value || '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');
  }

  function matchesSlug(candidate, target) {
    var normalizedCandidate = normalizeSlug(candidate);
    var normalizedTarget = normalizeSlug(target);
    if (!normalizedCandidate || !normalizedTarget) {
      return false;
    }
    if (normalizedCandidate === normalizedTarget) {
      return true;
    }
    var candidateParts = normalizedCandidate.split('/');
    var targetParts = normalizedTarget.split('/');
    return candidateParts[candidateParts.length - 1] === targetParts[targetParts.length - 1];
  }

  function normalizePath(pathname) {
    if (!pathname) {
      return '/';
    }
    var path = String(pathname).split(/[?#]/)[0];
    path = path.replace(/\/+$/, '');
    if (!path) {
      return '/';
    }
    return path;
  }

  function monthLabel(year, month) {
    var y = parseInt(year, 10);
    var m = parseInt(month, 10);
    if (!y || !m) {
      return '';
    }
    var date = new Date(Date.UTC(y, m - 1, 1));
    if (isNaN(date.getTime())) {
      return y + '-' + (m < 10 ? '0' + m : m);
    }
    var formatter;
    try {
      formatter = date.toLocaleString(undefined, { month: 'long', year: 'numeric' });
    } catch (err) {
      formatter = y + '-' + (m < 10 ? '0' + m : m);
    }
    return formatter;
  }

  function padMonth(value) {
    var num = parseInt(value, 10);
    if (!num || num < 1) {
      return '01';
    }
    return num < 10 ? '0' + num : String(num);
  }

  function limitArchiveQueue(entries) {
    if (!Array.isArray(entries) || !entries.length) {
      return [];
    }
    var limited = [];
    var seen = Object.create(null);
    for (var i = 0; i < entries.length && limited.length < MAX_CATEGORY_ARCHIVE_DAYS; i++) {
      var entry = entries[i];
      if (!entry || typeof entry !== 'object') {
        continue;
      }
      var year = parseInt(entry.year, 10);
      var month = parseInt(entry.month, 10);
      if (!year || !month) {
        if (entry.date) {
          var dateParts = String(entry.date).split('-');
          if (dateParts.length >= 3) {
            year = parseInt(dateParts[0], 10);
            month = parseInt(dateParts[1], 10);
            entry = { year: year, month: month, day: parseInt(dateParts[2], 10) };
          }
        }
      }
      if (!year || !month) {
        continue;
      }
      var normalized = { year: year, month: month };
      var dayValue = entry.day;
      if (dayValue == null && entry.date) {
        var parts = String(entry.date).split('-');
        if (parts.length >= 3) {
          dayValue = parseInt(parts[2], 10);
        }
      }
      var day = parseInt(dayValue, 10);
      if (!isNaN(day) && day >= 1 && day <= 31) {
        normalized.day = day;
      }
      var key = normalized.year + '-' + normalized.month + (normalized.day != null ? '-' + normalized.day : '');
      if (seen[key]) {
        continue;
      }
      seen[key] = true;
      limited.push(normalized);
    }
    return limited;
  }

  function addArchiveEntry(entry, target) {
    if (!entry || typeof entry !== 'object' || !target) {
      return;
    }
    if (Array.isArray(entry.days) && entry.days.length) {
      for (var i = 0; i < entry.days.length; i++) {
        var dayEntry = entry.days[i];
        var candidate = {};
        if (dayEntry && typeof dayEntry === 'object') {
          candidate.year = dayEntry.year != null ? dayEntry.year : entry.year;
          candidate.month = dayEntry.month != null ? dayEntry.month : entry.month;
          if (dayEntry.day != null) {
            candidate.day = dayEntry.day;
          } else if (dayEntry.date) {
            candidate.day = dayEntry.date;
          } else if (dayEntry.value != null) {
            candidate.day = dayEntry.value;
          }
          if (dayEntry.date) {
            candidate.date = dayEntry.date;
          } else if (entry.date) {
            candidate.date = entry.date;
          }
        } else {
          candidate.year = entry.year;
          candidate.month = entry.month;
          candidate.day = dayEntry;
          if (entry.date) {
            candidate.date = entry.date;
          }
        }
        target.push(candidate);
      }
      return;
    }
    target.push(entry);
  }

  function formatArchiveLabel(entry) {
    if (!entry || typeof entry !== 'object') {
      return '';
    }
    var year = parseInt(entry.year, 10);
    var month = parseInt(entry.month, 10);
    if (!year || !month) {
      return '';
    }
    var day = entry.day != null ? parseInt(entry.day, 10) : NaN;
    if (!isNaN(day) && day >= 1 && day <= 31) {
      var date = new Date(Date.UTC(year, month - 1, day));
      if (!isNaN(date.getTime())) {
        try {
          return date.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
        } catch (err) {
          return year + '-' + padMonth(month) + '-' + padMonth(day);
        }
      }
      return year + '-' + padMonth(month) + '-' + padMonth(day);
    }
    return monthLabel(year, month);
  }

  function Deduper() {
    this._seen = Object.create(null);
  }

  Deduper.prototype._keysFor = function (post) {
    var keys = [];
    if (!post || typeof post !== 'object') {
      return keys;
    }
    var id = getString(post.id);
    if (id) {
      keys.push('id:' + id);
    }
    var slug = getString(post.slug);
    if (slug) {
      keys.push('slug:' + slug.toLowerCase());
    }
    var url = getString(post.url || post.link || post.permalink);
    if (url) {
      keys.push('url:' + url);
    }
    var guid = getString(post.guid);
    if (guid) {
      keys.push('guid:' + guid);
    }
    var title = getString(post.title).trim();
    var date = getString(post.date || post.published_at || post.pubDate || post.published || post.datetime).trim();
    if (title) {
      keys.push('title-date:' + title + '|' + date);
    }
    return keys;
  };

  Deduper.prototype.add = function (post) {
    var keys = this._keysFor(post);
    if (!keys.length) {
      return true;
    }
    for (var i = 0; i < keys.length; i++) {
      var key = keys[i];
      if (key && this._seen[key]) {
        return false;
      }
    }
    for (var j = 0; j < keys.length; j++) {
      var k = keys[j];
      if (k) {
        this._seen[k] = true;
      }
    }
    return true;
  };

  function extractPosts(payload) {
    if (!payload || typeof payload !== 'object') {
      return [];
    }
    if (Array.isArray(payload.posts)) {
      return payload.posts;
    }
    if (Array.isArray(payload.items)) {
      return payload.items;
    }
    if (payload.data) {
      if (Array.isArray(payload.data.posts)) {
        return payload.data.posts;
      }
      if (Array.isArray(payload.data.items)) {
        return payload.data.items;
      }
    }
    if (Array.isArray(payload.results)) {
      return payload.results;
    }
    if (payload.results && Array.isArray(payload.results.items)) {
      return payload.results.items;
    }
    if (payload.page && Array.isArray(payload.page.items)) {
      return payload.page.items;
    }
    if (payload.pagination && Array.isArray(payload.pagination.items)) {
      return payload.pagination.items;
    }
    return [];
  }

  function extractArchiveQueue(payload) {
    var queue = [];
    if (!payload || typeof payload !== 'object') {
      return queue;
    }
    var sources = [];
    if (Array.isArray(payload.archive)) {
      sources.push(payload.archive);
    }
    if (payload.archive && Array.isArray(payload.archive.months)) {
      sources.push(payload.archive.months);
    }
    if (payload.archive && Array.isArray(payload.archive.days)) {
      sources.push(payload.archive.days);
    }
    if (Array.isArray(payload.archives)) {
      sources.push(payload.archives);
    }
    if (Array.isArray(payload.months)) {
      sources.push(payload.months);
    }
    if (Array.isArray(payload.days)) {
      sources.push(payload.days);
    }
    if (payload.meta && Array.isArray(payload.meta.months)) {
      sources.push(payload.meta.months);
    }
    if (payload.meta && Array.isArray(payload.meta.days)) {
      sources.push(payload.meta.days);
    }
    if (payload.pagination && Array.isArray(payload.pagination.months)) {
      sources.push(payload.pagination.months);
    }
    if (payload.pagination && Array.isArray(payload.pagination.days)) {
      sources.push(payload.pagination.days);
    }
    for (var i = 0; i < sources.length; i++) {
      var list = sources[i];
      if (!Array.isArray(list)) {
        continue;
      }
      for (var j = 0; j < list.length; j++) {
        addArchiveEntry(list[j], queue);
      }
    }
    return limitArchiveQueue(queue);
  }

  function getArchiveSummary() {
    if (!archiveSummaryPromise) {
      archiveSummaryPromise = fetchJson('/data/archive/summary.json', { cache: 'no-store' })
        .catch(function (err) {
          console.warn('Archive summary load failed:', err);
          return null;
        });
    }
    return archiveSummaryPromise;
  }

  function findArchiveMonths(summary, slug) {
    var result = [];
    var normalizedSlug = normalizeSlug(slug);
    if (!summary || !normalizedSlug) {
      return result;
    }
    var seen = Object.create(null);

    function appendMonths(list) {
      if (!Array.isArray(list)) {
        return;
      }
      for (var i = 0; i < list.length; i++) {
        var entry = list[i];
        if (!entry) {
          continue;
        }
        var year = parseInt(entry.year, 10);
        var month = parseInt(entry.month, 10);
        if (!year || !month) {
          continue;
        }
        var key = year + '-' + month;
        if (seen[key]) {
          continue;
        }
        seen[key] = true;
        result.push({ year: year, month: month });
      }
    }

    if (Array.isArray(summary.parents)) {
      for (var i = 0; i < summary.parents.length; i++) {
        var parent = summary.parents[i];
        if (!parent) {
          continue;
        }
        if (matchesSlug(parent.slug || parent.parent, normalizedSlug)) {
          appendMonths(parent.months);
        }
        if (Array.isArray(parent.children)) {
          for (var j = 0; j < parent.children.length; j++) {
            var child = parent.children[j];
            if (!child) {
              continue;
            }
            var childSlug = child.slug || child.child;
            if (!childSlug && matchesSlug(parent.slug || parent.parent, normalizedSlug)) {
              childSlug = parent.parent + '/' + (child.child || '');
            }
            if (matchesSlug(childSlug, normalizedSlug)) {
              appendMonths(child.months);
            }
          }
        }
      }
    }

    if (!result.length && Array.isArray(summary.children)) {
      for (var k = 0; k < summary.children.length; k++) {
        var direct = summary.children[k];
        if (direct && matchesSlug(direct.slug || direct.child, normalizedSlug)) {
          appendMonths(direct.months);
        }
      }
    }

    return limitArchiveQueue(result);
  }

  function buildMenuConfig(payload) {
    var config = { items: [], tabletHeader: null };
    if (!payload || typeof payload !== 'object') {
      return config;
    }
    var menu = payload.menu || payload.navigation || null;
    if (Array.isArray(menu)) {
      config.items = menu.slice();
      if (payload.tabletHeader) {
        config.tabletHeader = payload.tabletHeader;
      }
    } else if (menu && typeof menu === 'object') {
      if (Array.isArray(menu.items)) {
        config.items = menu.items.slice();
      }
      if (menu.tabletHeader) {
        config.tabletHeader = menu.tabletHeader;
      }
    }
    if (!config.items.length) {
      if (Array.isArray(payload.items)) {
        config.items = payload.items.slice();
      } else if (Array.isArray(payload.categories)) {
        config.items = payload.categories.slice();
      }
    }
    return config;
  }

  function normalizeMenuChildren(source) {
    if (!source) {
      return [];
    }
    if (Array.isArray(source)) {
      return source;
    }
    if (typeof source === 'object') {
      var items = [];
      for (var key in source) {
        if (Object.prototype.hasOwnProperty.call(source, key)) {
          items.push(source[key]);
        }
      }
      return items;
    }
    return [];
  }

  function normalizeMenuItem(raw) {
    if (!raw || typeof raw !== 'object') {
      return null;
    }
    var item = {
      title: getString(raw.title || raw.name || raw.label || raw.slug || ''),
      slug: normalizeSlug(raw.slug || raw.id || ''),
      href: getString(raw.href || raw.url || raw.link || ''),
      target: getString(raw.target || ''),
      badge: getString(raw.badge || ''),
      icon: getString(raw.icon || ''),
      children: []
    };

    if (item.href) {
      item.href = resolve(item.href);
    } else if (item.slug) {
      if (baseHelper && typeof baseHelper.categoryUrl === 'function') {
        item.href = baseHelper.categoryUrl(item.slug);
      } else {
        item.href = resolve('/category.html?cat=' + encodeURIComponent(item.slug));
      }
    }

    var childrenSource = normalizeMenuChildren(raw.children || raw.items || raw.categories);
    for (var i = 0; i < childrenSource.length; i++) {
      var child = normalizeMenuItem(childrenSource[i]);
      if (child) {
        item.children.push(child);
      }
    }

    if (!item.children.length && Array.isArray(raw.megaColumns)) {
      for (var colIndex = 0; colIndex < raw.megaColumns.length; colIndex++) {
        var column = raw.megaColumns[colIndex];
        if (!column) {
          continue;
        }
        var links = normalizeMenuChildren(column.links);
        for (var linkIndex = 0; linkIndex < links.length; linkIndex++) {
          var colItem = normalizeMenuItem(links[linkIndex]);
          if (colItem) {
            item.children.push(colItem);
          }
        }
      }
    }

    return item;
  }

  function createMenuList(items, level) {
    if (!items || !items.length) {
      return null;
    }
    var ul = document.createElement('ul');
    if (level === 0) {
      ul.className = 'nav-list';
    } else {
      ul.className = 'nav-sublist dropdown-menu';
    }
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      if (!item) {
        continue;
      }
      var li = document.createElement('li');
      if (item.children && item.children.length) {
        if (level === 0) {
          li.className = 'dropdown magz-dropdown';
        } else {
          li.className = 'dropdown';
        }
      }
      var link;
      if (item.href) {
        link = document.createElement('a');
        link.href = item.href;
        if (item.target) {
          link.target = item.target;
        }
        if (item.icon) {
          var icon = document.createElement('i');
          icon.className = item.icon;
          link.appendChild(icon);
          link.appendChild(document.createTextNode(' '));
        }
        link.appendChild(document.createTextNode(item.title || ''));
        if (item.badge) {
          var badge = document.createElement('div');
          badge.className = 'badge';
          badge.textContent = item.badge;
          link.appendChild(badge);
        }
        if (item.children && item.children.length) {
          link.appendChild(document.createTextNode(' '));
          var caret = document.createElement('i');
          caret.className = 'ion-ios-arrow-right';
          caret.setAttribute('aria-hidden', 'true');
          link.appendChild(caret);
        }
        li.appendChild(link);
      } else {
        var span = document.createElement('span');
        span.textContent = item.title || '';
        li.appendChild(span);
      }
      if (item.children && item.children.length) {
        var childList = createMenuList(item.children, level + 1);
        if (childList) {
          li.appendChild(childList);
        }
      }
      ul.appendChild(li);
    }
    return ul;
  }

  function addTabletHeader(list, header) {
    if (!list || !header) {
      return;
    }
    var show = header.show;
    if (show === false) {
      return;
    }
    var title = getString(header.title) || 'Menu';
    var loginHref = getString(header.loginHref || header.login) || 'login.html';
    var registerHref = getString(header.registerHref || header.register) || 'register.html';

    var titleItem = document.createElement('li');
    titleItem.className = 'for-tablet nav-title';
    var titleLink = document.createElement('a');
    titleLink.href = '#';
    titleLink.textContent = title;
    titleItem.appendChild(titleLink);

    var loginItem = document.createElement('li');
    loginItem.className = 'for-tablet';
    var loginLink = document.createElement('a');
    loginLink.href = resolve(loginHref);
    loginLink.textContent = getString(header.loginLabel) || 'Login';
    loginItem.appendChild(loginLink);

    var registerItem = document.createElement('li');
    registerItem.className = 'for-tablet';
    var registerLink = document.createElement('a');
    registerLink.href = resolve(registerHref);
    registerLink.textContent = getString(header.registerLabel) || 'Register';
    registerItem.appendChild(registerLink);

    if (list.firstChild) {
      list.insertBefore(titleItem, list.firstChild);
      list.insertBefore(loginItem, titleItem.nextSibling);
      list.insertBefore(registerItem, loginItem.nextSibling);
    } else {
      list.appendChild(titleItem);
      list.appendChild(loginItem);
      list.appendChild(registerItem);
    }
  }

  function applyActiveState(list) {
    if (!list) {
      return;
    }
    var links = list.querySelectorAll('a[href]');
    if (!links || !links.length) {
      return;
    }
    var currentPath = normalizePath(window.location.pathname);
    var best = { score: -1, link: null };

    function scoreFor(href) {
      if (!href) {
        return -1;
      }
      var resolved;
      try {
        resolved = new URL(href, window.location.origin).pathname;
      } catch (err) {
        return -1;
      }
      var normalized = normalizePath(resolved);
      if (normalized === currentPath) {
        return normalized.length + 1000;
      }
      if (normalized !== '/' && currentPath.indexOf(normalized + '/') === 0) {
        return normalized.length;
      }
      return -1;
    }

    for (var i = 0; i < links.length; i++) {
      var link = links[i];
      var score = scoreFor(link.getAttribute('href'));
      if (score > best.score) {
        best.score = score;
        best.link = link;
      }
    }

    if (best.link) {
      var li = best.link.closest('li');
      while (li) {
        li.classList.add('active');
        li = li.parentElement ? li.parentElement.closest('li') : null;
      }
    }
  }

  function renderMenu(payload) {
    var containers = document.querySelectorAll('[data-category-menu]');
    if (!containers.length) {
      return;
    }
    var config = buildMenuConfig(payload);
    var normalizedItems = [];
    for (var i = 0; i < config.items.length; i++) {
      var normalized = normalizeMenuItem(config.items[i]);
      if (normalized) {
        normalizedItems.push(normalized);
      }
    }
    if (!normalizedItems.length) {
      return;
    }
    for (var j = 0; j < containers.length; j++) {
      var container = containers[j];
      while (container.firstChild) {
        container.removeChild(container.firstChild);
      }
      var list = createMenuList(normalizedItems, 0);
      if (list) {
        addTabletHeader(list, config.tabletHeader);
        container.appendChild(list);
        applyActiveState(list);
      }
    }
  }

  function initMenu() {
    if (!document.querySelector('[data-category-menu]')) {
      return;
    }
    fetchJson('/data/index.json', { cache: 'no-store' })
      .then(renderMenu)
      .catch(function (err) {
        console.warn('Category menu load failed:', err);
      });
  }

  function splitCategorySlug(value) {
    var normalized = normalizeSlug(value);
    if (!normalized) {
      return { category: '', subcategory: '' };
    }
    var parts = normalized.split('/');
    var category = parts.shift() || '';
    var subcategory = parts.join('/');
    return {
      category: category,
      subcategory: subcategory || ''
    };
  }

  function readCategorySlug(section) {
    var attr = '';
    if (section) {
      attr = section.getAttribute('data-category') || section.dataset.category || '';
    }
    var fromAttr = splitCategorySlug(attr);
    if (fromAttr.category) {
      return fromAttr.category;
    }
    var search = window.location.search || '';
    var params;
    try {
      params = new URLSearchParams(search);
    } catch (err) {
      return '';
    }
    var fromQuery = params.get('cat') || params.get('category') || params.get('slug');
    return splitCategorySlug(fromQuery).category;
  }

  function readSubcategorySlug(section) {
    var attr = '';
    if (section) {
      attr = section.getAttribute('data-subcategory') || section.dataset.subcategory || '';
    }
    var attrParts = splitCategorySlug(attr);
    var search = window.location.search || '';
    var params;
    try {
      params = new URLSearchParams(search);
    } catch (err) {
      return attrParts.subcategory || attrParts.category || '';
    }
    var fromQuery = params.get('sub') || params.get('subcategory');
    if (!fromQuery) {
      var fromCat = params.get('cat') || params.get('category') || params.get('slug');
      var catParts = splitCategorySlug(fromCat);
      fromQuery = catParts.subcategory;
    }
    var fromQueryParts = splitCategorySlug(fromQuery);
    return (
      fromQueryParts.subcategory ||
      fromQueryParts.category ||
      attrParts.subcategory ||
      attrParts.category ||
      ''
    );
  }

  function readSubcategorySlug(section) {
    var search = window.location.search || '';
    var params;
    try {
      params = new URLSearchParams(search);
    } catch (err) {
      return '';
    }
    var attr = '';
    if (section) {
      attr = section.getAttribute('data-subcategory') || section.dataset.subcategory || '';
    }
    var fromQuery = params.get('sub') || params.get('subcategory');
    return normalizeSlug(fromQuery || attr);
  }

  function resolveArticleUrl(post) {
    if (!post || typeof post !== 'object') {
      return '#';
    }
    var direct = getString(post.url || post.link || post.permalink);
    if (direct) {
      return resolve(direct);
    }
    var slug = getString(post.slug || post.id);
    if (slug) {
      if (baseHelper && typeof baseHelper.articleUrl === 'function') {
        return baseHelper.articleUrl(slug);
      }
      return resolve('/article.html?slug=' + encodeURIComponent(slug));
    }
    var guid = getString(post.guid || post.canonical || post.source);
    if (guid) {
      return guid;
    }
    return '#';
  }

  function resolveCategoryName(post) {
    if (!post || typeof post !== 'object') {
      return '';
    }
    var candidates = [
      post.category_label,
      post.categoryLabel,
      post.category_title,
      post.categoryTitle,
      post.category,
      post.section,
      post.section_name,
      post.subcategory
    ];
    for (var i = 0; i < candidates.length; i++) {
      var name = getString(candidates[i]).trim();
      if (name) {
        return name;
      }
    }
    return '';
  }

  function resolveCategorySlug(post) {
    if (!post || typeof post !== 'object') {
      return '';
    }
    var candidates = [
      post.category_slug,
      post.categorySlug,
      post.category_path,
      post.categoryPath,
      post.section_slug,
      post.subcategory_slug,
      post.subcategorySlug
    ];
    for (var i = 0; i < candidates.length; i++) {
      var slug = normalizeSlug(candidates[i]);
      if (slug) {
        return slug;
      }
    }
    var fallback = getString(post.category);
    if (fallback) {
      return normalizeSlug(fallback);
    }
    return '';
  }

  function buildCategoryUrl(slug) {
    var parts = splitCategorySlug(slug);
    if (!parts.category) {
      return '#';
    }
    if (baseHelper && typeof baseHelper.categoryUrl === 'function') {
      return baseHelper.categoryUrl(parts.subcategory ? parts.category + '/' + parts.subcategory : parts.category);
    }
    var url = '/category.html?cat=' + encodeURIComponent(parts.category);
    if (parts.subcategory) {
      url += '&sub=' + encodeURIComponent(parts.subcategory);
    }
    return resolve(url);
  }

  function formatDisplayDate(value) {
    if (!value) {
      return '';
    }
    var date;
    try {
      date = new Date(value);
    } catch (err) {
      date = null;
    }
    if (date && !isNaN(date.getTime())) {
      try {
        return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
      } catch (err2) {
        return date.getUTCFullYear() + '-' + padMonth(date.getUTCMonth() + 1) + '-' + padMonth(date.getUTCDate());
      }
    }
    return String(value);
  }

  function removeEmptyState(list) {
    var empties = list ? list.querySelectorAll('.empty-state') : [];
    for (var i = 0; i < empties.length; i++) {
      var node = empties[i];
      if (node && node.parentNode) {
        node.parentNode.removeChild(node);
      }
    }
  }

  function showEmptyState(list, text) {
    if (!list) {
      return;
    }
    var item = document.createElement('li');
    item.className = 'empty-state text-muted';
    item.textContent = text;
    list.appendChild(item);
  }

  function createPostNode(post) {
    if (!post) {
      return null;
    }
    var li = document.createElement('li');
    li.className = 'col-md-12 article-list';

    var article = document.createElement('article');
    article.className = 'article';

    var inner = document.createElement('div');
    inner.className = 'inner';

    var figure = document.createElement('figure');
    var cover = getString(post.cover || post.image || post.thumbnail);
    if (!cover) {
      figure.className = 'no-cover';
    }
    var figureLink = document.createElement('a');
    var articleUrl = resolveArticleUrl(post);
    figureLink.href = articleUrl;
    var img = document.createElement('img');
    img.src = cover ? resolve(cover) : DEFAULT_IMAGE;
    img.alt = getString(post.title) || 'Article cover';
    figureLink.appendChild(img);
    figure.appendChild(figureLink);
    inner.appendChild(figure);

    var details = document.createElement('div');
    details.className = 'details';

    var detailMeta = document.createElement('div');
    detailMeta.className = 'detail';

    var categoryName = resolveCategoryName(post);
    var categorySlug = resolveCategorySlug(post);
    if (categoryName) {
      var categoryDiv = document.createElement('div');
      categoryDiv.className = 'category';
      if (categorySlug) {
        var categoryLink = document.createElement('a');
        categoryLink.href = buildCategoryUrl(categorySlug);
        categoryLink.textContent = categoryName;
        categoryDiv.appendChild(categoryLink);
      } else {
        categoryDiv.textContent = categoryName;
      }
      detailMeta.appendChild(categoryDiv);
    }

    var timeDiv = document.createElement('div');
    timeDiv.className = 'time';
    timeDiv.textContent = formatDisplayDate(post.date || post.published_at || post.pubDate || post.updated_at);
    detailMeta.appendChild(timeDiv);
    details.appendChild(detailMeta);

    var heading = document.createElement('h1');
    var headingLink = document.createElement('a');
    headingLink.href = articleUrl;
    headingLink.textContent = getString(post.title) || 'Untitled';
    heading.appendChild(headingLink);
    details.appendChild(heading);

    var excerpt = getString(post.excerpt || post.summary || post.description).trim();
    if (excerpt) {
      var paragraph = document.createElement('p');
      paragraph.textContent = excerpt;
      details.appendChild(paragraph);
    }

    var footer = document.createElement('footer');
    var moreLink = document.createElement('a');
    moreLink.className = 'btn btn-primary more';
    moreLink.href = articleUrl;
    var moreInner = document.createElement('div');
    moreInner.textContent = 'More';
    var iconWrap = document.createElement('div');
    var icon = document.createElement('i');
    icon.className = 'ion-ios-arrow-thin-right';
    iconWrap.appendChild(icon);
    moreLink.appendChild(moreInner);
    moreLink.appendChild(iconWrap);
    footer.appendChild(moreLink);
    details.appendChild(footer);

    inner.appendChild(details);
    article.appendChild(inner);
    li.appendChild(article);
    return li;
  }

  function appendPosts(state, posts) {
    if (!state || !state.postList) {
      return 0;
    }
    if (!state.initialised) {
      state.postList.innerHTML = '';
      state.initialised = true;
    }
    removeEmptyState(state.postList);
    var fragment = document.createDocumentFragment();
    var added = 0;
    for (var i = 0; i < posts.length; i++) {
      var post = posts[i];
      if (!state.deduper.add(post)) {
        continue;
      }
      var node = createPostNode(post);
      if (node) {
        fragment.appendChild(node);
        added += 1;
      }
    }
    if (added) {
      state.postList.appendChild(fragment);
    }
    return added;
  }

  function setStatus(statusEl, message) {
    if (!statusEl) {
      return;
    }
    statusEl.textContent = message || '';
  }

  function updateLoadMoreButton(state) {
    if (!state || !state.button) {
      return;
    }
    var label = state.button.getAttribute('data-label');
    if (!label) {
      label = 'Load more';
      state.button.setAttribute('data-label', label);
    }
    var loadingLabel = state.button.getAttribute('data-loading-label') || 'Loading…';

    if (state.isLoading) {
      state.button.disabled = true;
      state.button.setAttribute('aria-busy', 'true');
      state.button.textContent = loadingLabel;
      return;
    }

    state.button.removeAttribute('aria-busy');
    state.button.textContent = label;
    if (!state.queue || !state.queue.length) {
      state.button.disabled = true;
      state.button.setAttribute('aria-disabled', 'true');
    } else {
      state.button.disabled = false;
      state.button.removeAttribute('aria-disabled');
    }
  }

  function handleCategoryPayload(state, payload) {
    var posts = extractPosts(payload);
    var added = appendPosts(state, posts);
    if (!added) {
      showEmptyState(state.postList, 'No posts found for this category');
      setStatus(state.statusEl, 'No posts found for this category');
    } else {
      setStatus(state.statusEl, 'Loaded ' + added + ' posts.');
    }
    var directQueue = extractArchiveQueue(payload);
    if (directQueue.length) {
      state.queue = directQueue;
      updateLoadMoreButton(state);
    } else if (state.button) {
      getArchiveSummary().then(function (summary) {
        if (!summary) {
          return;
        }
        var months = findArchiveMonths(summary, state.slug);
        if (months && months.length) {
          state.queue = months;
        }
        updateLoadMoreButton(state);
      });
    }
  }

  function fetchCategoryIndex(state) {
    if (!state.slug) {
      return Promise.reject(new Error('Missing category slug.'));
    }
    var segments = ['/data/hot', state.slug];
    if (state.subcategory) {
      segments.push(state.subcategory);
    }
    var path = segments.join('/') + '/index.json';
    return fetchJson(path, { cache: 'no-store' }).catch(function (err) {
      if (state.subcategory) {
        throw err;
      }
      return resolveHotFallbackPath(state.slug)
        .then(function (fallbackPath) {
          if (!fallbackPath || fallbackPath === path) {
            throw err;
          }
          console.warn('Falling back to hot shard', fallbackPath, 'for category', state.slug);
          return fetchJson(fallbackPath, { cache: 'no-store' });
        })
        .catch(function (fallbackErr) {
          if (fallbackErr && fallbackErr !== err) {
            throw fallbackErr;
          }
          throw err;
        });
    });
  }

  function fetchArchiveBatch(slug, entry) {
    var normalized = normalizeSlug(slug);
    if (!normalized) {
      return Promise.reject(new Error('Missing category slug.'));
    }
    if (!entry || typeof entry !== 'object') {
      return Promise.reject(new Error('Missing archive entry.'));
    }
    var year = parseInt(entry.year, 10);
    var month = parseInt(entry.month, 10);
    if (!year || !month) {
      return Promise.reject(new Error('Invalid archive entry.'));
    }
    var base = '/data/archive/' + normalized + '/' + year + '/' + padMonth(month);
    var fetchers = [];
    var day = entry.day != null ? parseInt(entry.day, 10) : NaN;
    if (!isNaN(day) && day >= 1 && day <= 31) {
      var daySegment = padMonth(day);
      var dayBase = base + '/' + daySegment;
      fetchers.push(function () {
        return fetchJson(dayBase + '.json', { cache: 'no-store' });
      });
      fetchers.push(function () {
        return fetchJson(dayBase + '/index.json', { cache: 'no-store' });
      });
    }
    fetchers.push(function () {
      return fetchJson(base + '.json', { cache: 'no-store' });
    });
    fetchers.push(function () {
      return fetchJson(base + '/index.json', { cache: 'no-store' });
    });

    function attempt(index, lastError) {
      if (index >= fetchers.length) {
        return Promise.reject(lastError || new Error('Archive batch fetch failed.'));
      }
      var fn = fetchers[index];
      var result;
      try {
        result = fn();
      } catch (err) {
        return attempt(index + 1, err);
      }
      return result.catch(function (err) {
        return attempt(index + 1, err);
      });
    }

    return attempt(0, null);
  }

  function handleLoadMore(state) {
    if (!state || state.isLoading) {
      return;
    }
    if (!state.queue || !state.queue.length) {
      setStatus(state.statusEl, 'No additional posts to load.');
      updateLoadMoreButton(state);
      return;
    }
    var next = state.queue.shift();
    if (!next) {
      updateLoadMoreButton(state);
      return;
    }
    state.isLoading = true;
    updateLoadMoreButton(state);
    var label = formatArchiveLabel(next);
    var fallbackLabel = typeof next.day === 'number' ? 'this date' : 'this month';
    var hadError = false;
    fetchArchiveBatch(state.slug, next)
      .then(function (payload) {
        var posts = extractPosts(payload);
        var added = appendPosts(state, posts);
        if (!added) {
          showEmptyState(state.postList, 'No archived posts available for ' + (label || fallbackLabel) + '.');
          setStatus(state.statusEl, 'No archived posts found for ' + (label || fallbackLabel) + '.');
        } else {
          setStatus(state.statusEl, 'Loaded ' + added + ' posts from ' + (label || 'the archive') + '.');
        }
      })
      .catch(function (err) {
        hadError = true;
        console.warn('Archive load failed:', err);
        setStatus(state.statusEl, 'Could not load more posts at this time.');
      })
      .then(function () {
        state.isLoading = false;
        updateLoadMoreButton(state);
        if (!hadError && (!state.queue || !state.queue.length)) {
          setStatus(state.statusEl, 'You have reached the end of the archive.');
        }
      });
  }

  function initCategoryFeed() {
    var section = document.querySelector('[data-category-feed]');
    if (!section) {
      return;
    }
    var slug = readCategorySlug(section);
    var subcategory = readSubcategorySlug(section);
    if (!slug) {
      setStatus(document.querySelector('[data-load-more-status]'), 'Missing category identifier.');
      return;
    }
    var postList = section.querySelector('[data-post-list]') || document.querySelector('[data-post-list]');
    var statusEl = section.querySelector('[data-load-more-status]') || document.querySelector('[data-load-more-status]');
    var button = section.querySelector('[data-load-more]') || document.querySelector('[data-load-more]');

    categoryState = {
      element: section,
      slug: slug,
      subcategory: subcategory,
      postList: postList,
      statusEl: statusEl,
      button: button,
      queue: [],
      isLoading: false,
      deduper: new Deduper(),
      initialised: false
    };

    if (categoryState.button) {
      updateLoadMoreButton(categoryState);
      categoryState.button.addEventListener('click', function (event) {
        event.preventDefault();
        handleLoadMore(categoryState);
      });
    }

    setStatus(categoryState.statusEl, 'Loading posts…');
    fetchCategoryIndex(categoryState)
      .then(function (payload) {
        handleCategoryPayload(categoryState, payload);
      })
      .catch(function (err) {
        console.warn('Category feed load failed:', err);
        showEmptyState(categoryState.postList, 'We could not load posts for this category.');
        setStatus(categoryState.statusEl, 'We could not load posts for this category.');
        if (categoryState.button) {
          categoryState.button.disabled = true;
          categoryState.button.setAttribute('aria-disabled', 'true');
        }
      });
  }

  ready(function () {
    initMenu();
    initCategoryFeed();
  });
})(typeof window !== 'undefined' ? window : this, typeof document !== 'undefined' ? document : null);
