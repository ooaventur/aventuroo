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
  var TAG_LIMIT = 10;
  var HOT_NEWS_LIMIT = 6;
  var FALLBACK_MESSAGE = 'We\'re sorry, but the latest stories are unavailable right now. Please try again soon.';
  var DEFAULT_CATEGORY_SLUG = 'top-stories';
  var DEFAULT_CATEGORY_LABEL = 'Top Stories';
  var DEFAULT_IMAGE = basePath.resolve ? basePath.resolve('/images/logo.png') : '/images/logo.png';

  function fetchSequential(urls) {
    if (!window.AventurOODataLoader || typeof window.AventurOODataLoader.fetchSequential !== 'function') {
      return Promise.reject(new Error('Data loader is not available'));
    }
    return window.AventurOODataLoader.fetchSequential(urls);
  }

  function normalizeTag(tag) {
    if (tag == null) return null;
    if (Array.isArray(tag)) {
      if (!tag.length) return null;
      return normalizeTag(tag[0]);
    }
    var raw = String(tag).trim();
    if (!raw) return null;
    var slug = raw
      .toLowerCase()
      .replace(/&/g, 'and')
      .replace(/[_\s]+/g, '-')
      .replace(/[^a-z0-9-]/g, '')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '');
    if (!slug) return null;
    var label = raw
      .replace(/[_-]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
      .split(' ')
      .map(function (word) {
        return word ? word.charAt(0).toUpperCase() + word.slice(1).toLowerCase() : '';
      })
      .join(' ');
    return {
      slug: slug,
      label: label || raw
    };
  }

  function getPostTimestamp(post) {
    if (!post || typeof post !== 'object') return 0;
    var fields = ['date', 'updated_at', 'published_at', 'created_at'];
    for (var i = 0; i < fields.length; i++) {
      var value = post[fields[i]];
      if (!value) continue;
      var parsed = Date.parse(value);
      if (!isNaN(parsed)) {
        return parsed;
      }
    }
    return 0;
  }

  function formatDate(timestamp) {
    if (!timestamp) return '';
    var date = new Date(timestamp);
    if (isNaN(date.getTime())) return '';
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
  }

  function pickCover(post) {
    if (!post || typeof post !== 'object') return DEFAULT_IMAGE;
    var sources = [post.cover, post.image, post.thumbnail];
    for (var i = 0; i < sources.length; i++) {
      var value = sources[i];
      if (typeof value !== 'string') continue;
      var trimmed = value.trim();
      if (trimmed) {
        return basePath.resolve ? basePath.resolve(trimmed) : trimmed;
      }
    }
    return DEFAULT_IMAGE;
  }

  function createHotNewsArticle(post) {
    if (!post || !post.slug || !post.title) return null;
    var timestamp = getPostTimestamp(post);
    var categoryInfo = normalizeTag(post.category);
    if (!categoryInfo) {
      categoryInfo = {
        slug: DEFAULT_CATEGORY_SLUG,
        label: DEFAULT_CATEGORY_LABEL
      };
    }
    var figure = document.createElement('figure');
    var coverSrc = pickCover(post);
    if (coverSrc === DEFAULT_IMAGE) {
      figure.classList.add('no-cover');
    }
    var figureLink = document.createElement('a');
    figureLink.href = basePath.articleUrl ? basePath.articleUrl(post.slug) : '/article.html?slug=' + encodeURIComponent(post.slug);
    var img = document.createElement('img');
    img.src = coverSrc;
    img.alt = post.title;
    img.loading = 'lazy';
    figureLink.appendChild(img);
    figure.appendChild(figureLink);

    var padding = document.createElement('div');
    padding.className = 'padding';

    var titleHeading = document.createElement('h1');
    var titleLink = document.createElement('a');
    titleLink.href = basePath.articleUrl ? basePath.articleUrl(post.slug) : '/article.html?slug=' + encodeURIComponent(post.slug);
    titleLink.textContent = post.title;
    titleHeading.appendChild(titleLink);
    padding.appendChild(titleHeading);

    var detail = document.createElement('div');
    detail.className = 'detail';

    var categoryDiv = document.createElement('div');
    categoryDiv.className = 'category';
    var categoryLink = document.createElement('a');
    categoryLink.href = basePath.categoryUrl ? basePath.categoryUrl(categoryInfo.slug) : '/category.html?cat=' + encodeURIComponent(categoryInfo.slug);
    categoryLink.textContent = categoryInfo.label;
    categoryDiv.appendChild(categoryLink);
    detail.appendChild(categoryDiv);

    var formattedDate = formatDate(timestamp);
    if (formattedDate) {
      var timeDiv = document.createElement('div');
      timeDiv.className = 'time';
      timeDiv.textContent = formattedDate;
      detail.appendChild(timeDiv);
    }

    padding.appendChild(detail);

    var inner = document.createElement('div');
    inner.className = 'inner';
    inner.appendChild(figure);
    inner.appendChild(padding);

    var article = document.createElement('article');
    article.className = 'article-mini';
    article.appendChild(inner);

    return article;
  }

  function renderHotNews(posts, container) {
    container.innerHTML = '';
    var sorted = posts
      .slice()
      .sort(function (a, b) {
        return getPostTimestamp(b) - getPostTimestamp(a);
      });
    var count = 0;
    for (var i = 0; i < sorted.length && count < HOT_NEWS_LIMIT; i++) {
      var article = createHotNewsArticle(sorted[i]);
      if (article) {
        container.appendChild(article);
        count++;
      }
    }
    return count;
  }

  function renderTrendingTags(posts, list) {
    list.innerHTML = '';
    var frequencies = {};
    posts.forEach(function (post) {
      if (!post) return;
      var tags = [];
      if (Array.isArray(post.category)) {
        tags = tags.concat(post.category);
      } else if (post.category != null) {
        tags.push(post.category);
      }

      var seen = {};
      for (var i = 0; i < tags.length; i++) {
        var normalized = normalizeTag(tags[i]);
        if (!normalized || seen[normalized.slug]) continue;
        seen[normalized.slug] = true;
        if (!frequencies[normalized.slug]) {
          frequencies[normalized.slug] = {
            slug: normalized.slug,
            label: normalized.label,
            count: 0
          };
        }
        frequencies[normalized.slug].count++;
      }
    });
    var items = Object.keys(frequencies)
      .map(function (slug) {
        return frequencies[slug];
      })
      .sort(function (a, b) {
        if (b.count === a.count) {
          return a.label.localeCompare(b.label);
        }
        return b.count - a.count;
      })
      .slice(0, TAG_LIMIT);

    if (!items.length) {
      return 0;
    }

    var fragment = document.createDocumentFragment();
    items.forEach(function (item) {
      var li = document.createElement('li');
      var link = document.createElement('a');
      link.href = basePath.categoryUrl
        ? basePath.categoryUrl(item.slug)
        : '/category.html?cat=' + encodeURIComponent(item.slug);
      link.textContent = item.label;
      li.appendChild(link);
      fragment.appendChild(li);
    });
    list.appendChild(fragment);
    return items.length;
  }

  function showTagsFallback(list, message) {
    if (!list) return;
    list.innerHTML = '';
    var li = document.createElement('li');
    li.className = 'empty';
    li.textContent = message;
    list.appendChild(li);
  }

  function showHotNewsFallback(container, message) {
    if (!container) return;
    container.innerHTML = '';
    var div = document.createElement('div');
    div.className = 'hot-news-empty';
    div.textContent = message;
    container.appendChild(div);
  }

  function initialize() {
    var tagsList = document.getElementById('trending-tags-list');
    var slider = document.getElementById('hot-news-slider');
    if (!tagsList || !slider) return;

    fetchSequential(POSTS_SOURCES)
      .then(function (posts) {
        if (!Array.isArray(posts) || !posts.length) {
          showTagsFallback(tagsList, 'No trending topics available at the moment.');
          showHotNewsFallback(slider, 'No hot news items available right now.');
          return;
        }
        var tagsCount = renderTrendingTags(posts, tagsList);
        if (!tagsCount) {
          showTagsFallback(tagsList, 'No trending topics available at the moment.');
        }
        var articleCount = renderHotNews(posts, slider);
        if (!articleCount) {
          showHotNewsFallback(slider, 'No hot news items available right now.');
          return;
        }
        if (typeof window.refreshVerticalSlider === 'function') {
          window.refreshVerticalSlider();
        }
      })
      .catch(function () {
        showTagsFallback(tagsList, FALLBACK_MESSAGE);
        showHotNewsFallback(slider, FALLBACK_MESSAGE);
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize);
  } else {
    initialize();
  }
})();
