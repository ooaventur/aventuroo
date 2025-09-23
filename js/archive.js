(function () {
  'use strict';

  var loader = window.AventurOODataLoader || null;
  var basePath = window.AventurOOBasePath || {
    resolve: function (value) { return value; }
  };
  var SUMMARY_SOURCES = ['/data/archive/summary.json', 'data/archive/summary.json'];

  function ready(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      fn();
    }
  }

  function toArray(value) {
    if (!Array.isArray(value)) return [];
    return value.slice();
  }

  function clearElement(element) {
    if (!element) return;
    while (element.firstChild) {
      element.removeChild(element.firstChild);
    }
  }

  function padNumber(value, length) {
    var number = parseInt(value, 10);
    if (isNaN(number)) number = 0;
    var string = String(Math.abs(number));
    while (string.length < length) {
      string = '0' + string;
    }
    return string;
  }

  function sanitizeSegment(value) {
    if (value == null) return '';
    return String(value).trim().replace(/^\/+|\/+$/g, '');
  }

  function formatLabel(value) {
    var text = value == null ? '' : String(value).trim();
    if (!text) return '';
    return text
      .replace(/[-_]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
      .replace(/\b([a-z])/gi, function (_, chr) { return chr.toUpperCase(); });
  }

  function formatCount(value, singular, plural) {
    var number = parseInt(value, 10);
    if (!isFinite(number) || number <= 0) return '';
    var label = number === 1 ? singular : plural;
    return number + ' ' + label;
  }

  function formatParentSummary(info) {
    if (!info) return '';
    var parts = [];
    var itemSummary = formatCount(info.items, 'archived story', 'archived stories');
    if (itemSummary) parts.push(itemSummary);
    var pageSummary = formatCount(info.pages, 'page', 'pages');
    if (pageSummary) parts.push(pageSummary);
    return parts.join(' · ');
  }

  function formatChildSummary(info) {
    if (!info) return '';
    var parts = [];
    var itemSummary = formatCount(info.items, 'story', 'stories');
    if (itemSummary) parts.push(itemSummary);
    var pageSummary = formatCount(info.pages, 'page', 'pages');
    if (pageSummary) parts.push(pageSummary);
    return parts.join(' · ');
  }

  function formatMonthLabel(year, month) {
    var yearNum = parseInt(year, 10);
    var monthNum = parseInt(month, 10);
    if (!isFinite(yearNum) || !isFinite(monthNum)) {
      if (year && month) return year + '-' + padNumber(month, 2);
      return String(year || month || '');
    }
    var date = new Date(Date.UTC(yearNum, monthNum - 1, 1));
    if (!isNaN(date.getTime())) {
      try {
        return date.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
      } catch (err) {
        // ignore locale errors
      }
    }
    return yearNum + '-' + padNumber(monthNum, 2);
  }

  function compareMonthDesc(a, b) {
    var ay = parseInt(a && a.year, 10);
    var by = parseInt(b && b.year, 10);
    if (!isFinite(ay)) ay = 0;
    if (!isFinite(by)) by = 0;
    if (ay !== by) return by - ay;
    var am = parseInt(a && a.month, 10);
    var bm = parseInt(b && b.month, 10);
    if (!isFinite(am)) am = 0;
    if (!isFinite(bm)) bm = 0;
    return bm - am;
  }

  function buildArchiveUrl(parent, child, year, month) {
    var yearNum = parseInt(year, 10);
    var monthNum = parseInt(month, 10);
    if (!isFinite(yearNum) || !isFinite(monthNum)) {
      return '';
    }

    var parentSegment = sanitizeSegment(parent);
    if (!parentSegment) parentSegment = 'index';
    var childSegment = sanitizeSegment(child);
    if (!childSegment) childSegment = 'index';
    var yearSegment = padNumber(yearNum, 4);
    var monthSegment = padNumber(monthNum, 2);
    var path = '/archive/' + parentSegment + '/' + childSegment + '/' + yearSegment + '/' + monthSegment + '/';
    try {
      if (basePath && typeof basePath.resolve === 'function') {
        return basePath.resolve(path);
      }
    } catch (err) {
      // ignore resolution errors and fall back to raw path
    }
    return path;
  }

  function instantiateTemplate(template) {
    if (!template) return null;
    if (template.content && template.content.firstElementChild) {
      return template.content.firstElementChild.cloneNode(true);
    }
    return null;
  }

  function createMonthEntry(parentKey, childKey, monthInfo, template) {
    var element = instantiateTemplate(template);
    if (!element) {
      element = document.createElement('li');
      element.className = 'archive__month';
      var linkFallback = document.createElement('a');
      linkFallback.className = 'archive__month-link';
      element.appendChild(linkFallback);
      var metaFallback = document.createElement('span');
      metaFallback.className = 'archive__month-meta';
      element.appendChild(metaFallback);
    }

    var linkEl = element.querySelector('[data-archive-month-link]') || element.querySelector('a');
    var metaEl = element.querySelector('[data-archive-month-meta]');

    if (linkEl) {
      var label = formatMonthLabel(monthInfo && monthInfo.year, monthInfo && monthInfo.month);
      linkEl.textContent = label || '';
      var href = buildArchiveUrl(parentKey, childKey, monthInfo && monthInfo.year, monthInfo && monthInfo.month);
      if (href) {
        linkEl.setAttribute('href', href);
        linkEl.removeAttribute('aria-disabled');
      } else {
        linkEl.setAttribute('href', '#');
        linkEl.setAttribute('aria-disabled', 'true');
      }
    }

    if (metaEl) {
      var parts = [];
      var items = formatCount(monthInfo && monthInfo.items, 'story', 'stories');
      if (items) parts.push(items);
      var pages = formatCount(monthInfo && monthInfo.pages, 'page', 'pages');
      if (pages) parts.push(pages);
      metaEl.textContent = parts.join(' · ');
      if (!parts.length) {
        metaEl.setAttribute('hidden', 'hidden');
      } else {
        metaEl.removeAttribute('hidden');
      }
    }

    return element;
  }

  function createChildGroup(parentInfo, childInfo, template, monthTemplate) {
    var months = toArray(childInfo && childInfo.months).filter(function (month) {
      return month && month.year != null && month.month != null;
    });
    if (!months.length) return null;

    months.sort(compareMonthDesc);

    var element = instantiateTemplate(template);
    if (!element) {
      element = document.createElement('article');
      element.className = 'archive__group';
      var header = document.createElement('header');
      header.className = 'archive__group-header';
      var title = document.createElement('h3');
      title.className = 'archive__group-title';
      header.appendChild(title);
      var summary = document.createElement('p');
      summary.className = 'archive__group-summary';
      header.appendChild(summary);
      element.appendChild(header);
      var monthsList = document.createElement('ul');
      monthsList.className = 'archive__months';
      monthsList.setAttribute('data-archive-months', '');
      element.appendChild(monthsList);
    }

    var titleEl = element.querySelector('[data-archive-child-title]') || element.querySelector('.archive__group-title');
    var summaryEl = element.querySelector('[data-archive-child-summary]') || element.querySelector('.archive__group-summary');
    var monthsEl = element.querySelector('[data-archive-months]');

    var parentLabel = formatLabel(parentInfo && parentInfo.parent);
    var childLabel = formatLabel(childInfo && childInfo.child);
    if (!childLabel || (childInfo && childInfo.child === 'index')) {
      childLabel = parentLabel || 'Archive';
    }

    if (titleEl) {
      titleEl.textContent = childLabel;
    }

    var summaryText = formatChildSummary(childInfo);
    if (summaryEl) {
      if (summaryText) {
        summaryEl.textContent = summaryText;
        summaryEl.removeAttribute('hidden');
      } else {
        summaryEl.textContent = '';
        summaryEl.setAttribute('hidden', 'hidden');
      }
    }

    if (!monthsEl) {
      monthsEl = document.createElement('ul');
      monthsEl.className = 'archive__months';
      monthsEl.setAttribute('data-archive-months', '');
      element.appendChild(monthsEl);
    }
    clearElement(monthsEl);

    months.forEach(function (month) {
      var monthEntry = createMonthEntry(parentInfo && parentInfo.parent, childInfo && childInfo.child, month, monthTemplate);
      if (monthEntry) monthsEl.appendChild(monthEntry);
    });

    return element;
  }

  function createParentSection(parentInfo, template, childTemplate, monthTemplate) {
    var children = toArray(parentInfo && parentInfo.children)
      .map(function (child) {
        return createChildGroup(parentInfo, child, childTemplate, monthTemplate);
      })
      .filter(Boolean);

    if (!children.length) return null;

    var element = instantiateTemplate(template);
    if (!element) {
      element = document.createElement('section');
      element.className = 'archive__section';
      var header = document.createElement('header');
      header.className = 'archive__section-header';
      var title = document.createElement('h2');
      title.className = 'archive__section-title';
      header.appendChild(title);
      var summary = document.createElement('p');
      summary.className = 'archive__section-summary';
      header.appendChild(summary);
      element.appendChild(header);
      var body = document.createElement('div');
      body.className = 'archive__section-body';
      element.appendChild(body);
    }

    var titleEl = element.querySelector('[data-archive-parent-title]') || element.querySelector('.archive__section-title');
    var summaryEl = element.querySelector('[data-archive-parent-summary]') || element.querySelector('.archive__section-summary');
    var bodyEl = element.querySelector('[data-archive-parent-body]');
    if (!bodyEl) {
      bodyEl = document.createElement('div');
      bodyEl.className = 'archive__section-body';
      element.appendChild(bodyEl);
    }
    clearElement(bodyEl);

    var parentLabel = formatLabel(parentInfo && parentInfo.parent) || 'Archive';
    if (titleEl) {
      titleEl.textContent = parentLabel;
    }

    var summaryText = formatParentSummary(parentInfo);
    if (summaryEl) {
      if (summaryText) {
        summaryEl.textContent = summaryText;
        summaryEl.removeAttribute('hidden');
      } else {
        summaryEl.textContent = '';
        summaryEl.setAttribute('hidden', 'hidden');
      }
    }

    children.forEach(function (childElement) {
      bodyEl.appendChild(childElement);
    });

    var parentKey = sanitizeSegment(parentInfo && parentInfo.parent);
    if (parentKey) {
      element.setAttribute('data-archive-parent-key', parentKey);
    }

    return element;
  }

  function renderArchive(listEl, emptyEl, parentTemplate, childTemplate, monthTemplate, summary) {
    clearElement(listEl);

    var parents = toArray(summary && summary.parents)
      .map(function (parent) {
        return createParentSection(parent, parentTemplate, childTemplate, monthTemplate);
      })
      .filter(Boolean);

    if (!parents.length) {
      if (emptyEl) emptyEl.removeAttribute('hidden');
      listEl.setAttribute('data-archive-loaded', 'true');
      return;
    }

    parents.forEach(function (section) {
      listEl.appendChild(section);
    });

    if (emptyEl) emptyEl.setAttribute('hidden', 'hidden');
    listEl.setAttribute('data-archive-loaded', 'true');
  }

  function showEmpty(emptyEl) {
    if (emptyEl) emptyEl.removeAttribute('hidden');
  }

  function fetchSummary() {
    if (!loader || typeof loader.fetchSequential !== 'function') {
      return Promise.reject(new Error('Archive data loader is not available'));
    }
    return loader.fetchSequential(SUMMARY_SOURCES);
  }

  ready(function () {
    var listEl = document.querySelector('[data-archive-list]');
    if (!listEl) return;
    var container = listEl.closest('[data-archive-container]') || document;
    var emptyEl = container.querySelector('[data-archive-empty]');
    var parentTemplate = document.querySelector('template[data-archive-parent-template]');
    var childTemplate = document.querySelector('template[data-archive-child-template]');
    var monthTemplate = document.querySelector('template[data-archive-month-template]');

    fetchSummary()
      .then(function (summary) {
        if (!summary) {
          showEmpty(emptyEl);
          return;
        }
        renderArchive(listEl, emptyEl, parentTemplate, childTemplate, monthTemplate, summary);
      })
      .catch(function (err) {
        console.warn('archive summary load error', err);
        showEmpty(emptyEl);
      });
  });
})();
