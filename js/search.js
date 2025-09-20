(function () {
  'use strict';

  var basePath = window.AventurOOBasePath || {
    resolve: function (value) { return value; },
    articleUrl: function (slug) {
      return slug ? '/article.html?slug=' + encodeURIComponent(slug) : '#';
    },
    categoryUrl: function (slug) {
      return slug ? '/category.html?cat=' + encodeURIComponent(slug) : '#';
    }
  };

  var POSTS_SOURCES = ['/data/posts.json', 'data/posts.json'];
  var DEFAULT_IMAGE = basePath.resolve ? basePath.resolve('/images/logo.png') : '/images/logo.png';

  function getQuery() {
    var params = new URLSearchParams(window.location.search);
    return params.get('q') || '';
  }

  function loadPosts() {
    if (!window.AventurOODataLoader || typeof window.AventurOODataLoader.fetchSequential !== 'function') {
      return Promise.reject(new Error('Data loader is not available'));
    }
    return window.AventurOODataLoader.fetchSequential(POSTS_SOURCES);
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

  function stripHtml(value) {
    if (value == null) return '';
    return String(value).replace(/<[^>]*>/g, ' ');
  }

  function removeDiacritics(value) {
    if (typeof value.normalize === 'function') {
      return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    }
    return value;
  }

  function normalizeText(value) {
    if (value == null) return '';
    var stringValue = removeDiacritics(String(value));
    return stringValue
      .toLowerCase()
      .replace(/\s+/g, ' ')
      .trim();
  }

  function tokenize(value) {
    var normalized = normalizeText(value);
    return normalized ? normalized.split(' ') : [];
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

  function resolveArticleUrl(post) {
    if (!post) return '#';
    var slug = post.slug || slugify(post.title || '');
    if (!slug) return '#';
    return typeof basePath.articleUrl === 'function' ? basePath.articleUrl(slug) : '#';
  }

  function resolveImage(post) {
    if (post && post.cover) {
      return basePath.resolve ? basePath.resolve(post.cover) : post.cover;
    }
    return DEFAULT_IMAGE;
  }

  function resolveCategoryLink(post) {
    if (!post) return '#';
    var rawSlug = post.category_slug || post.category;
    var slug = typeof rawSlug === 'string' ? rawSlug.trim().replace(/^\/+|\/+$/g, '') : '';
    if (!slug) {
      slug = slugify(post.category || '');
    }
    if (!slug) return '#';
    return typeof basePath.categoryUrl === 'function' ? basePath.categoryUrl(slug) : '#';
  }

  function buildSearchText(post) {
    var parts = [];
    if (!post) return '';
    if (post.title) parts.push(post.title);
    if (post.excerpt) parts.push(post.excerpt);
    if (post.category) parts.push(post.category);
    if (post.subcategory) parts.push(post.subcategory);
    if (post.body) parts.push(stripHtml(post.body));
    return normalizeText(parts.join(' '));
  }

  function matchesQuery(post, queryTokens) {
    if (!queryTokens.length) return true;
    var haystack = buildSearchText(post);
    if (!haystack) return false;
    for (var i = 0; i < queryTokens.length; i += 1) {
      if (haystack.indexOf(queryTokens[i]) === -1) {
        return false;
      }
    }
    return true;
  }

  function createArticle(post) {
    if (!post) return null;

    var titleText = post.title ? stripHtml(post.title) : '';
    var title = escapeHtml(titleText || 'Untitled');
    var link = escapeHtml(resolveArticleUrl(post));
    var image = escapeHtml(resolveImage(post));
    var category = post.category ? escapeHtml(post.category) : '';
    var categoryLink = category ? escapeHtml(resolveCategoryLink(post)) : '#';
    var date = post.date ? escapeHtml(formatDate(post.date)) : '';
    var excerptText = post.excerpt ? stripHtml(post.excerpt) : '';
    var excerpt = excerptText ? escapeHtml(excerptText) : '';

    var articleEl = document.createElement('article');
    articleEl.className = 'col-md-12 article-list';
    articleEl.innerHTML =
      '<div class="inner">' +
        '<figure><a href="' + link + '"><img src="' + image + '" alt="' + title + '"></a></figure>' +
        '<div class="details">' +
          '<div class="detail">' +
            (category ? '<div class="category"><a href="' + categoryLink + '">' + category + '</a></div>' : '') +
            (date ? '<time>' + date + '</time>' : '') +
          '</div>' +
          '<h1><a href="' + link + '">' + title + '</a></h1>' +
          (excerpt ? '<p>' + excerpt + '</p>' : '') +
          '<footer><a class="btn btn-primary more" href="' + link + '"><div>More</div><div><i class="ion-ios-arrow-thin-right"></i></div></a></footer>' +
        '</div>' +
      '</div>';
    return articleEl;
  }

  function renderEmptyState(container, message) {
    if (!container) return;
    var wrapper = document.createElement('div');
    wrapper.className = 'col-md-12 no-search-results';
    var inner = document.createElement('div');
    inner.className = 'inner';
    var paragraph = document.createElement('p');
    paragraph.textContent = message || 'No matching results found.';
    inner.appendChild(paragraph);
    wrapper.appendChild(inner);
    container.appendChild(wrapper);
  }

  document.addEventListener('DOMContentLoaded', function () {
    var query = getQuery();
    var input = document.querySelector('input[name="q"]');
    if (input) {
      input.value = query;
    }

    var resultInfo = document.querySelector('.search-result');
    var resultsContainer = document.getElementById('search-results');

    loadPosts()
      .then(function (posts) {
        var tokens = tokenize(query);
        var filtered = Array.isArray(posts) ? posts.filter(function (post) {
          return matchesQuery(post, tokens);
        }) : [];

        if (resultInfo) {
          if (tokens.length) {
            resultInfo.textContent = 'Search results for "' + query + '" (' + filtered.length + ' found).';
          } else {
            resultInfo.textContent = 'Showing all posts (' + filtered.length + ').';
          }
        }

        if (resultsContainer) {
          resultsContainer.innerHTML = '';
          if (filtered.length) {
            filtered.forEach(function (post) {
              var article = createArticle(post);
              if (article) {
                resultsContainer.appendChild(article);
              }
            });
          } else if (tokens.length) {
            renderEmptyState(resultsContainer, 'No results found for "' + query + '".');
          } else {
            renderEmptyState(resultsContainer, 'No articles available to display.');
          }
        }
      })
      .catch(function () {
        if (resultInfo) {
          resultInfo.textContent = 'Failed to load search results.';
        }
        if (resultsContainer) {
          resultsContainer.innerHTML = '';
          renderEmptyState(resultsContainer, 'Unable to load search data.');
        }
      });
  });
})();
