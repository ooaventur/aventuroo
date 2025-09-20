(function (global) {
  'use strict';

  var POSTS_SOURCES = ['/data/posts.json', 'data/posts.json'];
  var MAX_ITEMS = 4;
  var DEFAULT_IMAGE = '/images/logo.png';
  var CONTAINER_SELECTOR = '[data-footer-latest]';
  var FALLBACK_SELECTOR = '[data-footer-latest-fallback]';
  var SEE_ALL_SELECTOR = '[data-footer-latest-seeall]';

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

  function getBasePath() {
    return global.AventurOOBasePath || null;
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

  function parseDate(value) {
    if (!value) {
      return 0;
    }
    var parsed = new Date(value);
    if (!isNaN(parsed.getTime())) {
      return parsed.getTime();
    }
    var fallback = Date.parse(value);
    return isNaN(fallback) ? 0 : fallback;
  }

  function normalizePosts(data) {
    if (Array.isArray(data)) {
      return data;
    }
    if (data && Array.isArray(data.posts)) {
      return data.posts;
    }
    return [];
  }

  function selectLatest(posts, limit) {
    return posts
      .filter(function (post) { return post && (post.slug || post.title); })
      .sort(function (a, b) {
        return parseDate(b.date) - parseDate(a.date);
      })
      .slice(0, limit);
  }

  function buildArticle(post, basePath) {
    if (!post) {
      return null;
    }

    var slug = slugify(post.slug || post.title || '');
    if (!slug) {
      return null;
    }

    var title = post.title ? String(post.title).trim() : 'Untitled';
    if (!title) {
      title = 'Untitled';
    }

    var link = basePath && typeof basePath.articleUrl === 'function'
      ? basePath.articleUrl(slug)
      : '/article.html?slug=' + encodeURIComponent(slug);

    var resolvedDefaultImage = basePath && typeof basePath.resolve === 'function'
      ? basePath.resolve(DEFAULT_IMAGE)
      : DEFAULT_IMAGE;

    var cover = post.cover ? String(post.cover) : '';
    var image = cover
      ? (basePath && typeof basePath.resolve === 'function' ? basePath.resolve(cover) : cover)
      : resolvedDefaultImage;

    var article = document.createElement('article');
    article.className = 'article-mini';
    article.innerHTML = '' +
      '<div class="inner">' +
        '<figure>' +
          '<a href="' + escapeHtml(link) + '">' +
            '<img src="' + escapeHtml(image) + '" alt="' + escapeHtml(title) + '">' +
          '</a>' +
        '</figure>' +
        '<div class="padding">' +
          '<h1><a href="' + escapeHtml(link) + '">' + escapeHtml(title) + '</a></h1>' +
        '</div>' +
      '</div>';

    return article;
  }

  function clearElement(element) {
    if (!element) {
      return;
    }
    while (element.firstChild) {
      element.removeChild(element.firstChild);
    }
  }

  function hideElement(element) {
    if (element) {
      element.style.display = 'none';
    }
  }

  function showElement(element) {
    if (element) {
      element.style.display = '';
    }
  }

  function showFallback(container, fallback, seeAll) {
    if (container) {
      clearElement(container);
      hideElement(container);
    }
    if (fallback) {
      fallback.hidden = false;
    }
    if (seeAll) {
      hideElement(seeAll);
    }
  }

  function hideFallback(container, fallback, seeAll) {
    if (container) {
      showElement(container);
    }
    if (fallback) {
      fallback.hidden = true;
    }
    if (seeAll) {
      showElement(seeAll);
    }
  }

  function renderPosts(container, posts, basePath) {
    if (!container || !posts || !posts.length) {
      return false;
    }

    var fragment = document.createDocumentFragment();
    var count = 0;

    for (var i = 0; i < posts.length; i += 1) {
      var node = buildArticle(posts[i], basePath);
      if (node) {
        fragment.appendChild(node);
        count += 1;
      }
    }

    if (!count) {
      return false;
    }

    clearElement(container);
    container.appendChild(fragment);
    return true;
  }

  function init() {
    var container = document.querySelector(CONTAINER_SELECTOR);
    if (!container) {
      return;
    }

    var fallback = document.querySelector(FALLBACK_SELECTOR);
    var seeAll = document.querySelector(SEE_ALL_SELECTOR);
    var basePath = getBasePath();
    var loader = getLoader();

    if (!loader) {
      showFallback(container, fallback, seeAll);
      return;
    }

    container.setAttribute('aria-busy', 'true');

    loader.fetchSequential(POSTS_SOURCES)
      .then(function (data) {
        var posts = selectLatest(normalizePosts(data), MAX_ITEMS);
        if (!posts.length || !renderPosts(container, posts, basePath)) {
          showFallback(container, fallback, seeAll);
          return;
        }
        hideFallback(container, fallback, seeAll);
      })
      .catch(function () {
        showFallback(container, fallback, seeAll);
      })
      .then(function () {
        container.removeAttribute('aria-busy');
      });
  }

  ready(init);
})(typeof window !== 'undefined' ? window : this);
