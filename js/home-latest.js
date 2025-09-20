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

  var POSTS_SOURCES = ['/data/posts.json', 'data/posts.json'];
  var BANNERS_SOURCES = ['data/banners.json', '/data/banners.json'];
  var MAX_ARTICLES = 12;
  var BANNER_FREQUENCY = 4;
  var DEFAULT_IMAGE = basePath.resolve ? basePath.resolve('/images/logo.png') : '/images/logo.png';
  var DEFAULT_BANNER_IMAGE = basePath.resolve ? basePath.resolve('/images/ads.png') : '/images/ads.png';

  function loadJson(urls) {
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

  function truncate(value, maxLength) {
    if (value == null) return '';
    var str = String(value).trim();
    if (str.length <= maxLength) return str;
    return str.slice(0, Math.max(0, maxLength - 1)).trimEnd() + '…';
  }

  function formatDate(dateValue) {
    if (!dateValue) return '';
    var parsed = new Date(dateValue);
    if (!isNaN(parsed.getTime())) {
      var months = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
      ];
      return months[parsed.getMonth()] + ' ' + parsed.getDate() + ', ' + parsed.getFullYear();
    }
    var fallback = Date.parse(dateValue);
    if (!isNaN(fallback)) {
      return new Date(fallback).toDateString();
    }
    return String(dateValue);
  }

  function articleUrl(post) {
    if (!post) return '#';
    if (post.url) {
      return basePath.resolve ? basePath.resolve(post.url) : post.url;
    }
    var slug = slugify(post.slug || post.title || '');
    return slug ? basePath.articleUrl ? basePath.articleUrl(slug) : '/article.html?slug=' + encodeURIComponent(slug) : '#';
  }

  function categoryUrl(category) {
    var slug = slugify(category);
    if (!slug) return '#';
    if (basePath.categoryUrl) {
      return basePath.categoryUrl(slug);
    }
    return '/category.html?cat=' + encodeURIComponent(slug);
  }

  function pickArticles(posts, limit) {
    var sorted = posts
      .filter(function (item) { return item && (item.slug || item.title); })
      .slice()
      .sort(function (a, b) {
        return parseDateValue(b.date) - parseDateValue(a.date);
      });

    var groups = {};
    var order = [];

    sorted.forEach(function (post) {
      var category = post.category || 'News';
      var key = slugify(category) || category.toLowerCase();
      if (!groups[key]) {
        groups[key] = { name: category, items: [] };
        order.push(key);
      }
      groups[key].items.push(post);
    });

    var selected = [];
    var pointer = 0;
    while (selected.length < limit && order.length) {
      if (pointer >= order.length) pointer = 0;
      var key = order[pointer];
      var bucket = groups[key];
      if (!bucket || !bucket.items.length) {
        order.splice(pointer, 1);
        continue;
      }
      selected.push(bucket.items.shift());
      pointer += 1;
    }

    return selected;
  }

  function parseDateValue(value) {
    if (!value) return 0;
    var parsed = new Date(value);
    if (!isNaN(parsed.getTime())) return parsed.getTime();
    var fallback = Date.parse(value);
    return isNaN(fallback) ? 0 : fallback;
  }

  function createArticleElement(post) {
    if (!post) return null;
    var title = escapeHtml(post.title || 'Untitled');
    var rawExcerpt = post.excerpt ? truncate(post.excerpt, 140) : '';
    var excerpt = rawExcerpt ? escapeHtml(rawExcerpt) : '';
    var category = post.category ? escapeHtml(post.category) : '';
    var date = escapeHtml(formatDate(post.date));
    var coverSrc = post.cover ? (basePath.resolve ? basePath.resolve(post.cover) : post.cover) : DEFAULT_IMAGE;
    var cover = escapeHtml(coverSrc);
    var link = escapeHtml(articleUrl(post));
    var categoryLink = category ? escapeHtml(categoryUrl(post.category)) : '#';
    var figureClass = post.cover ? '' : ' class="no-cover"';
    var article = document.createElement('article');
    article.className = 'article article-mini latest-news-item';
    article.innerHTML =
      '<div class="inner">' +
        '<figure' + figureClass + '>' +
          '<a href="' + link + '">' +
            '<img src="' + cover + '" alt="' + title + '">' +
          '</a>' +
        '</figure>' +
        '<div class="padding">' +
          '<div class="detail">' +
            (date ? '<div class="time">' + date + '</div>' : '') +
            (category ? '<div class="category"><a href="' + categoryLink + '">' + category + '</a></div>' : '') +
          '</div>' +
          '<h2><a href="' + link + '">' + title + '</a></h2>' +
          (excerpt ? '<p>' + excerpt + '</p>' : '') +
        '</div>' +
      '</div>';
    return article;
  }

  function createBannerElement(banner, index) {
    var href = banner.href ? (basePath.resolve ? basePath.resolve(banner.href) : banner.href) : '#';
    var image = banner.image ? (basePath.resolve ? basePath.resolve(banner.image) : banner.image) : DEFAULT_BANNER_IMAGE;
    var image = banner.image ? String(banner.image) : DEFAULT_BANNER_IMAGE;
    var alt = banner.alt ? String(banner.alt) : 'Advertisement';
    var bannerWrapper = document.createElement('div');
    bannerWrapper.className = 'banner latest-news-banner';
    bannerWrapper.innerHTML =
      '<a href="' + escapeHtml(href) + '" target="_blank" rel="noopener noreferrer">' +
        '<img src="' + escapeHtml(image) + '" alt="' + escapeHtml(alt) + '">' +
      '</a>';
    return bannerWrapper;
  }

  function wrapColumn(element) {
    var column = document.createElement('div');
    column.className = 'col-xs-12 latest-news-col';
    column.appendChild(element);
    return column;
  }

  function hideBlock(block) {
    if (block) {
      block.style.display = 'none';
    }
  }

  function queryFirst(selectors) {
    for (var i = 0; i < selectors.length; i += 1) {
      var element = document.querySelector(selectors[i]);
      if (element) return element;
    }
    return null;
  }

  function findLatestNewsBlock(container) {
    var element = container;
    while (element && element.nodeType === 1) {
      if (element.getAttribute && element.getAttribute('data-latest-news-block') !== null) {
        return element;
      }
      var className = element.className || '';
      if (
        (element.classList && element.classList.contains('latest-news-block')) ||
        (' ' + className + ' ').indexOf(' latest-news-block ') !== -1
      ) {
        return element;
      }
      element = element.parentElement;
    }
    return queryFirst(['[data-latest-news-block]', '.latest-news-block', '#latest-news-block']);
  }

  function init() {
    var container = queryFirst(['[data-latest-news-grid]', '.latest-news-grid', '#latest-news-grid']);
    if (!container) return;
    var block = findLatestNewsBlock(container);


    Promise.all([
      loadJson(POSTS_SOURCES).catch(function (error) {
        console.error('Failed to load posts.json', error);
        return null;
      }),
      loadJson(BANNERS_SOURCES).catch(function (error) {
        console.warn('Failed to load banners.json', error);
        return [];
      })
    ]).then(function (results) {
      var posts = Array.isArray(results[0]) ? results[0] : null;
      var banners = Array.isArray(results[1]) ? results[1] : [];

      if (!posts || !posts.length) {
        hideBlock(block);
        return;
      }

      var selected = pickArticles(posts, MAX_ARTICLES);
      if (!selected.length) {
        hideBlock(block);
        return;
      }

      container.innerHTML = '';
      var fragment = document.createDocumentFragment();
      var bannerIndex = 0;

      selected.forEach(function (post, index) {
        var articleEl = createArticleElement(post);
        if (articleEl) {
          fragment.appendChild(wrapColumn(articleEl));
        }
        if ((index + 1) % BANNER_FREQUENCY === 0 && banners.length) {
          var bannerData = banners[bannerIndex % banners.length];
          var bannerEl = createBannerElement(bannerData, bannerIndex);
          if (bannerEl) {
            fragment.appendChild(wrapColumn(bannerEl));
            bannerIndex += 1;
          }
        }
      });

      if (!fragment.childNodes.length) {
        hideBlock(block);
        return;
      }

      container.appendChild(fragment);
    }).catch(function (error) {
      console.error('Failed to initialize latest news', error);
      hideBlock(block);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
