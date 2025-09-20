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
  var BEST_OF_WEEK_SOURCES = ['data/best-of-week.json', '/data/best-of-week.json'];
  var DEFAULT_IMAGE = basePath.resolve ? basePath.resolve('/images/logo.png') : '/images/logo.png';

  function slugify(str) {
    return (str || '')
      .toString()
      .trim()
      .toLowerCase()
      .replace(/\.html?$/i, '')
      .replace(/&/g, 'and')
      .replace(/[_\W]+/g, '-')
      .replace(/^-+|-+$/g, '');
  }

  function escapeHtml(str) {
    return (str == null ? '' : String(str))
      .replace(/[&<>"']/g, function (ch) {
        return {
          '&': '&amp;',
          '<': '&lt;',
          '>': '&gt;',
          '"': '&quot;',
          "'": '&#39;'
        }[ch];
      });
  }

  function formatDate(dateValue) {
    if (!dateValue) return '';
    var raw = String(dateValue);
    var parsed = new Date(raw);
    if (!isNaN(parsed.getTime())) {
      var months = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
      ];
      var month = months[parsed.getMonth()];
      var day = parsed.getDate();
      var year = parsed.getFullYear();
      return month + ' ' + day + ', ' + year;
    }
    var parts = raw.split('T');
    return parts[0] || raw;
  }

  function buildArticleUrl(post) {
    if (!post) return '#';
    if (post.url) {
      return basePath.resolve ? basePath.resolve(post.url) : post.url;
    }
    var slug = post.slug ? encodeURIComponent(post.slug) : '';
    return slug ? (basePath.articleUrl ? basePath.articleUrl(post.slug) : '/article.html?slug=' + slug) : '#';
  }
  function normalizeEntries(raw) {
    if (!raw) return [];
    var list;
    if (Array.isArray(raw)) {
      list = raw;
    } else if (Array.isArray(raw.items)) {
      list = raw.items;
    } else if (Array.isArray(raw.slugs)) {
      list = raw.slugs;
    } else if (raw.slug || raw.url) {
      list = [raw];
    } else {
      return [];
    }
    return list
      .map(function (entry) {
        if (!entry) return null;
        if (typeof entry === 'string') {
          var slug = slugify(entry);
          return slug ? { slug: slug } : null;
        }
        if (typeof entry === 'object') {
          var normalized = {};
          if (entry.slug) normalized.slug = slugify(entry.slug);
          if (entry.url) normalized.url = entry.url;
          if (entry.title) normalized.title = entry.title;
          if (entry.excerpt) normalized.excerpt = entry.excerpt;
          if (entry.cover) normalized.cover = entry.cover;
          if (entry.category) normalized.category = entry.category;
          if (entry.date) normalized.date = entry.date;
          return normalized.slug || normalized.url ? normalized : null;
        }
        return null;
      })
      .filter(function (entry) { return entry && (entry.slug || entry.url); });
  }

  function mergePostWithMeta(post, meta) {
    if (!post && !meta) return null;
    var data = {
      slug: post && post.slug ? post.slug : meta && meta.slug ? meta.slug : '',
      title: post && post.title ? post.title : '',
      excerpt: post && post.excerpt ? post.excerpt : '',
      cover: post && post.cover ? post.cover : '',
      category: post && post.category ? post.category : '',
      date: post && post.date ? post.date : '',
      url: post ? buildArticleUrl(post) : '#'
    };
    if (meta) {
      if (meta.title) data.title = meta.title;
      if (meta.excerpt) data.excerpt = meta.excerpt;
      if (meta.cover) data.cover = meta.cover;
      if (meta.category) data.category = meta.category;
      if (meta.date) data.date = meta.date;
      if (meta.url) data.url = basePath.resolve ? basePath.resolve(meta.url) : meta.url;
    }
    return data;
  }

  function categoryUrl(category) {
    if (!category) return '#';
    var slug = slugify(category);
    if (!slug) return '#';
    if (basePath.categoryUrl) {
      return basePath.categoryUrl(slug);
    }
    return '/category.html?cat=' + encodeURIComponent(slug);
  }

  function createArticle(data) {
    if (!data) return null;
    var title = escapeHtml(data.title || '');
    var excerpt = escapeHtml(data.excerpt || '');
    var category = escapeHtml(data.category || '');
    var date = escapeHtml(formatDate(data.date));
    var coverSrc = data.cover ? (basePath.resolve ? basePath.resolve(data.cover) : data.cover) : DEFAULT_IMAGE;
    var cover = escapeHtml(coverSrc);
    var link = escapeHtml((data.url ? data.url : buildArticleUrl(data))); // data.url already resolved
    var categoryLink = category ? escapeHtml(categoryUrl(data.category)) : '#';
    var figureClass = data.cover ? '' : ' class="no-cover"';
    var alt = title || 'AventurOO';

    var article = document.createElement('article');
    article.className = 'article';
    article.innerHTML =
      '<div class="inner">' +
        '<figure' + figureClass + '>' +
          '<a href="' + link + '">' +
            '<img src="' + cover + '" alt="' + alt + '">' +
          '</a>' +
        '</figure>' +
        '<div class="padding">' +
          '<div class="detail">' +
            '<div class="time">' + date + '</div>' +
            (category ? '<div class="category"><a href="' + categoryLink + '">' + category + '</a></div>' : '') +
          '</div>' +
          '<h2><a href="' + link + '">' + title + '</a></h2>' +
          '<p>' + excerpt + '</p>' +
        '</div>' +
      '</div>';
    return article;
  }

  function loadJson(urls) {
    if (!window.AventurOODataLoader || typeof window.AventurOODataLoader.fetchSequential !== 'function') {
      return Promise.reject(new Error('Data loader is not available'));
    }
    return window.AventurOODataLoader.fetchSequential(urls);
  }

  function init() {
    var wrapper = document.querySelector('.best-of-the-week');
    if (!wrapper) return;
    var carousel = wrapper.querySelector('.owl-carousel');
    if (!carousel) return;

    Promise.all([
      loadJson(POSTS_SOURCES).catch(function (err) {
        console.error('Failed to load posts.json', err);
        return [];
      }),
      loadJson(BEST_OF_WEEK_SOURCES).catch(function (err) {
        console.error('Failed to load best-of-week.json', err);
        return [];
      })
    ]).then(function (results) {
      var posts = Array.isArray(results[0]) ? results[0] : [];
      var botwRaw = results[1];
      var entries = normalizeEntries(botwRaw);
      if (!entries.length) {
        wrapper.style.display = 'none';
        return;
      }

      var postMap = posts.reduce(function (acc, post) {
        if (!post || !post.slug) return acc;
        var key = slugify(post.slug);
        if (!key) return acc;
        acc[key] = post;
        return acc;
      }, {});

      carousel.innerHTML = '';
      var fragment = document.createDocumentFragment();
      entries.forEach(function (entry) {
        var key = entry.slug ? slugify(entry.slug) : '';
        var post = key ? postMap[key] : null;
        var merged = mergePostWithMeta(post, entry);
        if (!merged || (!merged.title && !merged.excerpt)) return;
        var article = createArticle(merged);
        if (article) fragment.appendChild(article);
      });

      if (!fragment.childNodes.length) {
        wrapper.style.display = 'none';
        return;
      }

      carousel.appendChild(fragment);

      if (typeof window.initBestOfTheWeekCarousel === 'function') {
        window.initBestOfTheWeekCarousel();
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
