(function (global) {
  'use strict';

  var raw = '';
  if (typeof global.__AVENTUROO_BASE_PATH__ === 'string') {
    raw = global.__AVENTUROO_BASE_PATH__;
  }

  function normalizeBasePath(value) {
    if (!value) return '';
    var trimmed = String(value).trim();
    if (!trimmed || trimmed === '/') {
      return '';
    }
    if (!trimmed.startsWith('/')) {
      trimmed = '/' + trimmed;
    }
    return trimmed.replace(/\/+$/, '');
  }

  function isExternal(url) {
    return /^(?:[a-z][a-z0-9+.-]*:)?\/\//i.test(url);
  }

  function isSpecialScheme(url) {
    return /^(?:mailto:|tel:|sms:|javascript:|data:)/i.test(url);
  }

  var basePath = normalizeBasePath(raw);

  function resolve(path) {
    if (typeof path !== 'string') {
      return path;
    }

    var trimmed = path.trim();
    if (!trimmed) {
      return basePath || '/';
    }

    if (trimmed === '#') {
      return '#';
    }

    if (trimmed[0] === '?') {
      return trimmed;
    }

    if (isExternal(trimmed) || isSpecialScheme(trimmed)) {
      return trimmed;
    }

    var normalized = trimmed;
    if (normalized[0] !== '/') {
      normalized = '/' + normalized.replace(/^\/+/, '');
    }

    if (!basePath) {
      return normalized;
    }

    if (normalized === '/') {
      return basePath + '/';
    }

    return basePath + normalized;
  }

  function resolveAll(values) {
    if (!Array.isArray(values)) {
      return [];
    }

    var seen = Object.create(null);
    var result = [];

    for (var i = 0; i < values.length; i++) {
      var value = resolve(values[i]);
      if (typeof value !== 'string' || !value) {
        continue;
      }
      if (seen[value]) {
        continue;
      }
      seen[value] = true;
      result.push(value);
    }

    return result;
  }

  function articleUrl(slug) {
    if (!slug) {
      return '#';
    }
    return resolve('/article.html?slug=' + encodeURIComponent(slug));
  }

  function categoryUrl(slug) {
    if (!slug) {
      return '#';
    }

    return resolve('/category.html?cat=' + slug);
  }

  function sectionUrl(slug) {
    if (!slug) {
      return '#';
    }
    var normalized = String(slug).trim().replace(/^\/+|\/+$/g, '');
    if (!normalized) {
      return '#';
    }
    return resolve('/' + normalized + '/');
  }

  global.AventurOOBasePath = {
    basePath: basePath,
    resolve: resolve,
    resolveAll: resolveAll,
    articleUrl: articleUrl,
    categoryUrl: categoryUrl,
    sectionUrl: sectionUrl
  };
})(typeof window !== 'undefined' ? window : this);
