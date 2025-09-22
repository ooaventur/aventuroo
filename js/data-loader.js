(function (global) {
  'use strict';

  var fetch = global.fetch;
  var DEFAULT_FETCH_OPTIONS = { cache: 'default' };

  function applyBasePath(url) {
    if (!url) return '';
    var helper = global.AventurOOBasePath;
    if (!helper || typeof helper.resolve !== 'function') {
      return url;
    }
    return helper.resolve(url);
  }

  function normalizeUrls(urls) {
    if (!Array.isArray(urls)) return [];
    var seen = Object.create(null);
    var list = [];

    urls
      .map(function (url) { return typeof url === 'string' ? url.trim() : ''; })
      .forEach(function (url) {
        if (!url) return;
        var resolved = applyBasePath(url);
        if (!resolved || seen[resolved]) return;
        seen[resolved] = true;
        list.push(resolved);
      });

    return list;
  }
  function isJsonResponse(response) {
    if (!response || !response.headers || typeof response.headers.get !== 'function') {
      return false;
    }
    var contentType = response.headers.get('content-type');
    if (!contentType) return false;
    return contentType.toLowerCase().indexOf('json') !== -1;
  }

  function buildFetchSettings(overrides) {
    var base = Object.assign({}, DEFAULT_FETCH_OPTIONS);
    if (!overrides || typeof overrides !== 'object') {
      return base;
    }
    return Object.assign(base, overrides);
  }

  function fetchSequential(urls, options) {
    if (typeof fetch !== 'function') {
      return Promise.reject(new Error('Fetch API is not available'));
    }

    var list = normalizeUrls(urls);
    if (!list.length) {
      return Promise.reject(new Error('No matching resource found'));
    }

    var settings = buildFetchSettings(options);

    return new Promise(function (resolve, reject) {
      var index = 0;
      var done = false;

      function finish(result, isError) {
        if (done) return;
        done = true;
        if (isError) reject(result); else resolve(result);
      }

      function tryNext() {
        if (done) return;
        if (index >= list.length) {
          finish(new Error('No matching resource found'), true);
          return;
        }

        var currentUrl = list[index++];

        fetch(currentUrl, settings)
          .then(function (response) {
            if (!response || !response.ok || !isJsonResponse(response)) {
              tryNext();
              return;
            }
            return response.json()
              .then(function (json) {
                finish(json, false);
              })
              .catch(function () {
                tryNext();
              });
          })
          .catch(function () {
            tryNext();
          });
      }

      tryNext();
    });
  }

  var loader = global.AventurOODataLoader || {};
  loader.fetchSequential = fetchSequential;
  global.AventurOODataLoader = loader;
})(typeof window !== 'undefined' ? window : this);
