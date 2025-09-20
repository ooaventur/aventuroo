(function (global) {
  'use strict';

  var SUMMARY_SOURCES = ['/data/archive/summary.json', 'data/archive/summary.json'];
  var ROOT_SELECTOR = '[data-archive-root]';
  var LIST_SELECTOR = '[data-archive-list]';
  var LOADING_SELECTOR = '[data-archive-loading]';
  var EMPTY_SELECTOR = '[data-archive-empty]';

  var SPECIAL_WORDS = {
    ai: 'AI',
    tv: 'TV',
    uk: 'UK',
    usa: 'USA',
    us: 'US',
    eu: 'EU',
    faq: 'FAQ',
    vpn: 'VPN',
    ios: 'iOS',
    iphone: 'iPhone',
    android: 'Android',
    vr: 'VR'
  };

  var MONTH_NAMES = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];

  function ready(callback) {
    if (typeof callback !== 'function') {
      return;
    }
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', callback);
    } else {
      callback();
    }
  }

  function getLoader() {
    var loader = global.AventurOODataLoader;
    if (!loader || typeof loader.fetchSequential !== 'function') {
      return null;
    }
    return loader;
  }

  function getBaseHelper() {
    return global.AventurOOBasePath || null;
  }

  function clearElement(element) {
    if (!element) {
      return;
    }
    while (element.firstChild) {
      element.removeChild(element.firstChild);
    }
  }

  function toggle(element, shouldShow) {
    if (!element) {
      return;
    }
    element.hidden = !shouldShow;
  }

  function normalizeArray(value) {
    return Array.isArray(value) ? value.slice() : [];
  }

  function toNumber(value) {
    var number = Number(value);
    return isFinite(number) ? number : 0;
  }

  function toInt(value) {
    var number = parseInt(value, 10);
    return isFinite(number) ? number : 0;
  }

  function padNumber(value, length) {
    var number = toInt(value);
    var negative = number < 0;
    var text = String(Math.abs(number));
    while (text.length < length) {
      text = '0' + text;
    }
    return negative ? '-' + text : text;
  }

  function formatWord(word) {
    if (!word) {
      return '';
    }
    var lower = String(word).toLowerCase();
    if (SPECIAL_WORDS[lower]) {
      return SPECIAL_WORDS[lower];
    }
    return lower.charAt(0).toUpperCase() + lower.slice(1);
  }

  function normalizeSegment(value) {
    if (value == null) {
      return '';
    }
    var text = String(value).trim();
    if (!text || text === 'index') {
      return '';
    }
    return text.replace(/^\/+|\/+$/g, '');
  }

  function slugToTitle(slug) {
    var normalized = normalizeSegment(slug);
    if (!normalized) {
      return 'Archive';
    }
    var parts = normalized.split('/');
    var last = parts[parts.length - 1] || normalized;
    var tokens = last.split(/[-_]+/).filter(Boolean);
    if (!tokens.length) {
      return formatWord(last);
    }
    return tokens.map(formatWord).join(' ');
  }

  function formatCount(count, singular, plural) {
    var value = Math.round(Math.abs(toNumber(count)));
    if (value === 1) {
      return '1 ' + (singular || 'item');
    }
    var word = plural || (singular ? singular + 's' : 'items');
    return value + ' ' + word;
  }

  function formatMonthLabel(year, month) {
    var y = toInt(year);
    var m = toInt(month);
    if (m >= 1 && m <= 12) {
      return MONTH_NAMES[m - 1] + ' ' + y;
    }
    if (!y && !m) {
      return '';
    }
    return (y || '0000') + '-' + padNumber(m, 2);
  }

  function resolveUrl(path, baseHelper) {
    if (!path) {
      return '#';
    }
    if (baseHelper && typeof baseHelper.resolve === 'function') {
      return baseHelper.resolve(path);
    }
    return path;
  }

  function buildChildHref(parentSlug, childSlug, baseHelper) {
    var parent = normalizeSegment(parentSlug);
    var child = normalizeSegment(childSlug);
    var query = '';
    if (parent) {
      query = '?cat=' + encodeURIComponent(parent);
      if (child && child !== parent) {
        query += '&sub=' + encodeURIComponent(child);
      }
    } else if (child) {
      query = '?cat=' + encodeURIComponent(child);
    }
    return resolveUrl('/category.html' + query, baseHelper);
  }

  function buildArchivePath(slugPath, year, month, baseHelper) {
    var cleaned = normalizeSegment(slugPath);
    var path = '/archive/';
    if (cleaned) {
      path += cleaned.replace(/\/+$/g, '') + '/';
    }
    path += padNumber(year, 4) + '/' + padNumber(month, 2) + '/';
    return resolveUrl(path, baseHelper);
  }

  function createMonthItem(info, slugPath, baseHelper, childLabel) {
    if (!info) {
      return null;
    }
    var year = toInt(info.year);
    var month = toInt(info.month);
    if (!year || !month) {
      return null;
    }
    var item = document.createElement('li');
    item.className = 'archive__month';
    var link = document.createElement('a');
    link.setAttribute('data-archive-month-link', '');
    link.href = buildArchivePath(slugPath, year, month, baseHelper);
    var label = formatMonthLabel(year, month);
    var stories = toInt(info.items);
    var text = label;
    if (stories > 0) {
      text += ' · ' + formatCount(stories, 'story', 'stories');
    }
    link.textContent = text;
    if (label) {
      link.title = 'View ' + (childLabel || 'archive') + ' stories from ' + label;
    }
    item.appendChild(link);
    return item;
  }

  function createChildSection(child, parentSlug, baseHelper) {
    if (!child) {
      return null;
    }
    var months = normalizeArray(child.months)
      .map(function (entry) { return entry || {}; })
      .filter(function (entry) { return entry.year != null && entry.month != null; })
      .sort(function (a, b) {
        var aKey = toInt(a.year) * 100 + toInt(a.month);
        var bKey = toInt(b.year) * 100 + toInt(b.month);
        return bKey - aKey;
      });
    if (!months.length) {
      return null;
    }

    var section = document.createElement('section');
    section.className = 'archive__child';

    var heading = document.createElement('h3');
    heading.className = 'archive__child-title';
    var link = document.createElement('a');
    link.setAttribute('data-archive-child-link', '');
    var label = slugToTitle(child.child || child.slug || parentSlug);
    link.textContent = label;
    link.href = buildChildHref(parentSlug, child.child || child.slug, baseHelper);
    heading.appendChild(link);
    section.appendChild(heading);

    var summary = document.createElement('p');
    summary.className = 'archive__child-summary text-muted';
    summary.setAttribute('data-archive-child-summary', '');
    var itemsCount = toInt(child.items);
    var monthsCount = months.length;
    var summaryParts = [];
    if (itemsCount > 0) {
      summaryParts.push(formatCount(itemsCount, 'archived story', 'archived stories'));
    }
    if (monthsCount > 0) {
      summaryParts.push(monthsCount === 1 ? 'across 1 month' : 'across ' + monthsCount + ' months');
    }
    summary.textContent = summaryParts.join(' · ');
    section.appendChild(summary);

    var list = document.createElement('ul');
    list.className = 'archive__months';
    list.setAttribute('data-archive-months', '');

    var slugPath = child.slug;
    if (!slugPath) {
      var parentSegment = normalizeSegment(parentSlug);
      var childSegment = normalizeSegment(child.child);
      slugPath = parentSegment;
      if (childSegment) {
        slugPath = slugPath ? parentSegment + '/' + childSegment : childSegment;
      }
    }

    var appended = 0;
    for (var i = 0; i < months.length; i += 1) {
      var monthItem = createMonthItem(months[i], slugPath, baseHelper, label);
      if (monthItem) {
        list.appendChild(monthItem);
        appended += 1;
      }
    }

    if (!appended) {
      return null;
    }

    section.appendChild(list);
    return section;
  }

  function createParentSection(parent, baseHelper) {
    if (!parent) {
      return null;
    }
    var section = document.createElement('article');
    section.className = 'archive__section';

    var header = document.createElement('header');
    header.className = 'archive__section-header';

    var title = document.createElement('h2');
    title.className = 'archive__section-title';
    title.setAttribute('data-archive-section-title', '');
    title.textContent = slugToTitle(parent.parent);
    header.appendChild(title);

    var summary = document.createElement('p');
    summary.className = 'archive__section-summary text-muted';
    summary.setAttribute('data-archive-section-summary', '');

    var childrenContainer = document.createElement('div');
    childrenContainer.className = 'archive__children';
    childrenContainer.setAttribute('data-archive-children', '');

    var children = normalizeArray(parent.children);
    var childCount = 0;
    for (var i = 0; i < children.length; i += 1) {
      var childSection = createChildSection(children[i], parent.parent, baseHelper);
      if (childSection) {
        childrenContainer.appendChild(childSection);
        childCount += 1;
      }
    }

    if (!childCount) {
      return null;
    }

    var summaryParts = [];
    var itemsCount = toInt(parent.items);
    if (itemsCount > 0) {
      summaryParts.push(formatCount(itemsCount, 'archived story', 'archived stories'));
    }
    summaryParts.push(childCount === 1 ? '1 subsection' : childCount + ' subsections');
    summary.textContent = summaryParts.join(' · ');

    header.appendChild(summary);
    section.appendChild(header);
    section.appendChild(childrenContainer);
    return section;
  }

  function showEmpty(context) {
    toggle(context.loading, false);
    if (context.list) {
      clearElement(context.list);
      context.list.hidden = true;
    }
    toggle(context.empty, true);
  }

  function showContent(context, nodes) {
    toggle(context.loading, false);
    toggle(context.empty, false);
    if (!context.list) {
      return;
    }
    clearElement(context.list);
    var fragment = document.createDocumentFragment();
    for (var i = 0; i < nodes.length; i += 1) {
      fragment.appendChild(nodes[i]);
    }
    context.list.appendChild(fragment);
    context.list.hidden = false;
  }

  function renderSummary(summary, context, baseHelper) {
    var parents = normalizeArray(summary && summary.parents);
    if (!parents.length) {
      showEmpty(context);
      return;
    }
    var nodes = [];
    for (var i = 0; i < parents.length; i += 1) {
      var section = createParentSection(parents[i], baseHelper);
      if (section) {
        nodes.push(section);
      }
    }
    if (!nodes.length) {
      showEmpty(context);
      return;
    }
    showContent(context, nodes);
  }

  ready(function () {
    var root = document.querySelector(ROOT_SELECTOR);
    if (!root) {
      return;
    }

    var context = {
      root: root,
      list: root.querySelector(LIST_SELECTOR),
      loading: root.querySelector(LOADING_SELECTOR),
      empty: root.querySelector(EMPTY_SELECTOR)
    };

    var baseHelper = getBaseHelper();

    if (context.loading) {
      context.loading.hidden = false;
    }
    if (context.empty) {
      context.empty.hidden = true;
    }
    if (context.list) {
      context.list.hidden = true;
    }

    var loader = getLoader();
    if (!loader) {
      showEmpty(context);
      return;
    }

    loader.fetchSequential(SUMMARY_SOURCES)
      .then(function (data) {
        try {
          renderSummary(data, context, baseHelper);
        } catch (err) {
          console.warn('archive summary render error', err);
          showEmpty(context);
        }
      })
      .catch(function (error) {
        console.warn('archive summary load error', error);
        showEmpty(context);
      });
  });
})(typeof window !== 'undefined' ? window : this);
