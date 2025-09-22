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

  var LEGACY_POSTS_SOURCES = ['/data/posts.json', 'data/posts.json'];
  var TAG_LIMIT = 10;
  var HOT_NEWS_LIMIT = 6;
  var FALLBACK_MESSAGE = 'We\'re sorry, but the latest stories are unavailable right now. Please try again soon.';
  var DEFAULT_CATEGORY_SLUG = 'top-stories';
  var DEFAULT_CATEGORY_LABEL = 'Top Stories';
  var DEFAULT_IMAGE = basePath.resolve ? basePath.resolve('/images/logo.png') : '/images/logo.png';
  var HOT_SHARD_ROOT = '/data/hot';
  var DEFAULT_SCOPE = { parent: 'news', child: 'top-stories' };
  var HOT_POSTS_CACHE = Object.create(null);

  function fetchSequential(urls, options) {
    if (!window.AventurOODataLoader || typeof window.AventurOODataLoader.fetchSequential !== 'function') {
      return Promise.reject(new Error('Data loader is not available'));
    }
    return window.AventurOODataLoader.fetchSequential(urls, options);
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

  function normalizePostsPayload(payload) {
    if (!payload) return [];
    if (Array.isArray(payload)) return payload.slice();
    if (typeof payload !== 'object') return [];
    if (Array.isArray(payload.items)) return payload.items.slice();
    if (Array.isArray(payload.posts)) return payload.posts.slice();
    if (Array.isArray(payload.data)) return payload.data.slice();
    if (Array.isArray(payload.results)) return payload.results.slice();
    return [];
  }

  function sortPosts(posts) {
    if (!Array.isArray(posts)) return [];
    return posts.slice().sort(function (a, b) {
      return getPostTimestamp(b) - getPostTimestamp(a);
    });
  }

  function resolvePostKey(post) {
    if (!post || typeof post !== 'object') return '';
    if (post.slug) return slugify(post.slug);
    if (post.url) return String(post.url).trim().toLowerCase();
    if (post.source) return String(post.source).trim().toLowerCase();
    if (post.title) return slugify(post.title);
    return '';
  }

  function dedupePosts(posts) {
    if (!Array.isArray(posts)) return [];
    var seen = Object.create(null);
    var list = [];
    for (var i = 0; i < posts.length; i++) {
      var post = posts[i];
      var key = resolvePostKey(post);
      if (key && seen[key]) continue;
      if (key) seen[key] = true;
      list.push(post);
    }
    return list;
  }

  function buildShardUrls(parent, child) {
    var normalizedParent = slugify(parent) || 'index';
    var normalizedChild = child != null && child !== '' ? slugify(child) : '';
    if (!normalizedChild) normalizedChild = 'index';
    var prefix = HOT_SHARD_ROOT.replace(/\/+$/, '');
    var basePath = prefix ? prefix + '/' + normalizedParent : normalizedParent;
    var childIndexSegment = normalizedChild === 'index' ? 'index' : normalizedChild + '/index';
    var rawCandidates = [
      basePath + '/' + childIndexSegment + '.json',
      basePath + '/' + normalizedChild + '.json'
    ];
    var urls = [];
    for (var i = 0; i < rawCandidates.length; i++) {
      var raw = rawCandidates[i];
      if (!raw) continue;
      var relative = raw.replace(/^\/+/, '');
      if (!relative) continue;
      urls.push(relative);
      urls.push('/' + relative);
    }
    var seen = Object.create(null);
    var deduped = [];
    for (var j = 0; j < urls.length; j++) {
      var candidate = urls[j];
      if (typeof candidate !== 'string') continue;
      var trimmed = candidate.trim();
      if (!trimmed || seen[trimmed]) continue;
      seen[trimmed] = true;
      deduped.push(trimmed);
    }
    return deduped;
  }

  function fetchHotShard(parent, child) {
    var scopeKey = (parent || 'index') + '::' + (child || 'index');
    if (HOT_POSTS_CACHE[scopeKey]) {
      return HOT_POSTS_CACHE[scopeKey];
    }
    var candidates = buildShardUrls(parent, child);
    HOT_POSTS_CACHE[scopeKey] = fetchSequential(candidates)
      .then(function (payload) {
        return dedupePosts(sortPosts(normalizePostsPayload(payload)));
      })
      .catch(function (err) {
        delete HOT_POSTS_CACHE[scopeKey];
        throw err;
      });
    return HOT_POSTS_CACHE[scopeKey];
  }

  function getPostParentSlug(post) {
    if (!post || typeof post !== 'object') return '';
    var raw = post.category_slug;
    if (raw && typeof raw === 'string') {
      var parts = raw.split('/');
      if (parts.length > 1) {
        var parent = slugify(parts[0]);
        if (parent) return parent;
      }
      var normalizedAll = slugify(raw);
      if (normalizedAll && normalizedAll.indexOf('-') !== -1) {
        var maybeParent = normalizedAll.split('-')[0];
        if (maybeParent) return maybeParent;
      }
    }
    if (post.category) {
      var normalized = slugify(post.category);
      if (normalized) return normalized;
    }
    return '';
  }

  function getPostChildSlug(post) {
    if (!post || typeof post !== 'object') return '';
    var raw = post.category_slug;
    if (raw && typeof raw === 'string') {
      var parts = raw.split('/');
      if (parts.length > 1) {
        var child = slugify(parts[parts.length - 1]);
        if (child) return child;
      }
    }
    if (post.subcategory) {
      var normalized = slugify(post.subcategory);
      if (normalized) return normalized;
    }
    return '';
  }

  function matchesScope(post, scope) {
    if (!post) return false;
    var parent = scope && scope.parent ? scope.parent : 'index';
    var child = scope && scope.child ? scope.child : 'index';
    if (parent === 'index' && child === 'index') return true;
    if (child !== 'index') {
      var childSlug = getPostChildSlug(post);
      if (childSlug && childSlug === child) return true;
      return false;
    }
    if (!parent || parent === 'index') return true;
    var parentSlug = getPostParentSlug(post);
    return parentSlug ? parentSlug === parent : false;
  }

  function filterPostsByScope(posts, scope) {
    if (!Array.isArray(posts)) return [];
    return posts.filter(function (post) { return matchesScope(post, scope); });
  }

  function resolveScopeHint(elements) {
    var parent = '';
    var child = '';
    for (var i = 0; i < elements.length; i++) {
      var element = elements[i];
      if (!element || !element.getAttribute) continue;
      if (!parent) {
        var p = element.getAttribute('data-hot-parent');
        if (p) parent = slugify(p);
      }
      if (!child) {
        var c = element.getAttribute('data-hot-child');
        if (c) child = slugify(c);
      }
      if (!child) {
        var combined = element.getAttribute('data-hot-scope');
        if (combined) {
          var trimmed = combined.trim().replace(/^\/+|\/+$/g, '');
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
    if (!parent) parent = '';
    if (!child) child = '';
    if (parent && !child) child = 'index';
    if (!parent && child) parent = 'index';
    if (!parent) parent = DEFAULT_SCOPE.parent;
    if (!child) child = DEFAULT_SCOPE.child;
    return { parent: parent, child: child };
  }

  function loadPostsForScope(scope) {
    return fetchHotShard(scope.parent, scope.child)
      .catch(function (err) {
        console.warn('hot news shard error', err);
        return fetchSequential(LEGACY_POSTS_SOURCES)
          .then(function (payload) {
            var posts = dedupePosts(sortPosts(normalizePostsPayload(payload)));
            return filterPostsByScope(posts, scope);
          });
      });
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

    var scope = resolveScopeHint([slider, tagsList, document.body]);

    loadPostsForScope(scope)
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
