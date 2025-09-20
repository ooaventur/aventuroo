(function () {
  var basePath = window.AventurOOBasePath || {
    resolve: function (value) { return value; },
    resolveAll: function (values) { return Array.isArray(values) ? values.slice() : []; },
    articleUrl: function (slug) { return slug ? '/article.html?slug=' + encodeURIComponent(slug) : '#'; },
    categoryUrl: function (slug) {
      if (!slug) return '#';
      return '/category.html?cat=' + encodeURIComponent(slug);
    },
    sectionUrl: function (slug) {
      if (!slug) return '#';
      var normalized = String(slug).trim().replace(/^\/+|\/+$/g, '');
      return normalized ? '/' + normalized + '/' : '#';
    }
  };

  var DEFAULT_IMAGE = basePath.resolve ? basePath.resolve('/images/logo.png') : '/images/logo.png';
  var HOME_URL = basePath.resolve ? basePath.resolve('/') : '/';
  var POSTS_SOURCES = ['/data/posts.json', 'data/posts.json'];

  var TAXONOMY_SOURCES = ['/data/taxonomy.json', 'data/taxonomy.json'];












  function fetchSequential(urls) {
    if (!window.AventurOODataLoader || typeof window.AventurOODataLoader.fetchSequential !== 'function') {
      return Promise.reject(new Error('Data loader is not available'));
    }
    return window.AventurOODataLoader.fetchSequential(urls);
  }

  function slugify(s) {
    return (s || '')
      .toString()
      .trim()
      .toLowerCase()
      .replace(/\.html?$/i, '')      // heq .html / .htm
      .replace(/&/g, 'and')
      .replace(/[_\W]+/g, '-')       // gjithçka jo-alfanumerike ose _ -> -
      .replace(/^-+|-+$/g, '');
  }
  function resolvePostCategorySlugs(post) {
    if (!post) return [];

    var slugs = [];
    var seen = Object.create(null);













    function appendSlug(value) {
      if (value == null) return;
      var trimmed = String(value).trim();
      if (!trimmed) return;
      var normalized = slugify(trimmed);
      if (!normalized || seen[normalized]) return;
      seen[normalized] = true;
      slugs.push(normalized);
    }

    var rawSlug = post.category_slug;
    if (rawSlug != null && String(rawSlug).trim()) {
      appendSlug(rawSlug);

      var rawSegments = String(rawSlug).split('/');
      if (rawSegments.length > 1) {
        var lastRawSegment = rawSegments[rawSegments.length - 1];
        appendSlug(lastRawSegment);
      }
    }

    var subcategory = post.subcategory;
    appendSlug(subcategory);

    if (subcategory != null && String(subcategory).indexOf('/') !== -1) {
      var subSegments = String(subcategory).split('/');
      var lastSubSegment = subSegments[subSegments.length - 1];
      appendSlug(lastSubSegment);
    }

    var category = post.category;
    appendSlug(category);
    if (category != null && String(category).indexOf('/') !== -1) {
      var categorySegments = String(category).split('/');
      var lastCategorySegment = categorySegments[categorySegments.length - 1];
      appendSlug(lastCategorySegment);
    }

    return slugs;
  }

  function resolvePostCategorySlug(post, preferredSlug) {
    var slugs = resolvePostCategorySlugs(post);
    if (!slugs.length) return '';

    var preferred = preferredSlug ? slugify(preferredSlug) : '';
    if (preferred) {
      for (var i = 0; i < slugs.length; i++) {
        if (slugs[i] === preferred) {
          return slugs[i];
        }
      }
    }

    return slugs[0];
  }


  var LABEL_PRIORITY_SUBCATEGORY = 1;
  var LABEL_PRIORITY_SLUG = 2;
  var LABEL_PRIORITY_CATEGORY = 3;
  var LABEL_PRIORITY_FALLBACK = 99;

  function resolvePostCategoryLabelInfo(post) {
    if (!post) {
      return { label: '', priority: LABEL_PRIORITY_FALLBACK };
    }

    var subcategory = post.subcategory;
    if (subcategory != null && String(subcategory).trim()) {
      return {
        label: String(subcategory).trim(),
        priority: LABEL_PRIORITY_SUBCATEGORY
      };
    }

    var rawSlug = post.category_slug;
    if (rawSlug != null && String(rawSlug).trim()) {
      var slugValue = String(rawSlug).trim();
      var normalized = slugify(slugValue);
      var formatted = normalized
        ? resolveCategoryLabelFromSlug(normalized, slugValue)
        : slugValue;
      return {
        label: formatted,
        priority: LABEL_PRIORITY_SLUG
      };
    }

    var category = post.category;
    if (category != null && String(category).trim()) {
      var categoryValue = String(category).trim();
      var normalizedCategory = slugify(categoryValue);
      var formattedCategory = normalizedCategory
        ? resolveCategoryLabelFromSlug(normalizedCategory, categoryValue)
        : categoryValue;
      return {
        label: formattedCategory,
        priority: LABEL_PRIORITY_CATEGORY
      };
    }

    return { label: '', priority: LABEL_PRIORITY_FALLBACK };
  }

  function resolvePostCategoryLabel(post) {
    return resolvePostCategoryLabelInfo(post).label;
  }


  function titleize(slug) {
    return (slug || '')
      .split('-')
      .map(function (w) { return w.charAt(0).toUpperCase() + w.slice(1); })
      .join(' ');
  }
  var CATEGORY_TITLE_LOOKUP = Object.create(null);















  function populateCategoryLookup(data) {
    if (!data || typeof data !== 'object') return;
    var categories = Array.isArray(data.categories) ? data.categories : [];
    categories.forEach(function (entry) {
      if (!entry || typeof entry !== 'object') return;
      var slug = slugify(entry.slug);
      if (!slug) return;
      var title = entry.title != null ? String(entry.title).trim() : '';
      if (!title) {
        title = titleize(slug);
      }
      CATEGORY_TITLE_LOOKUP[slug] = title;






















    });
  }

  function resolveCategoryLabelFromSlug(slug, rawLabel) {
    var normalizedSlug = slugify(slug);
    var trimmed = rawLabel == null ? '' : String(rawLabel).trim();

    if (!normalizedSlug) {
      return trimmed;
    }

    var lookupTitle = CATEGORY_TITLE_LOOKUP[normalizedSlug];
    if (lookupTitle) {
      return lookupTitle;
    }

    if (!trimmed) {
      return titleize(normalizedSlug);
    }

    var slugFromLabel = slugify(trimmed);
    if (slugFromLabel === normalizedSlug) {
      var pretty = titleize(normalizedSlug);
      var lowerTrimmed = trimmed.toLowerCase();
      if (
        lowerTrimmed === normalizedSlug ||
        trimmed === pretty ||
        lowerTrimmed === pretty.toLowerCase()
      ) {
        return pretty;
      }
    }

    return trimmed;
  }

  var HTML_ESCAPE = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  };

  function escapeHtml(value) {
    return (value == null ? '' : String(value)).replace(/[&<>"']/g, function (ch) {
      return HTML_ESCAPE[ch];
    });
  }

  function getPostTimestamp(post) {
    if (!post) return 0;
    var candidates = [post.date, post.updated_at, post.published_at, post.created_at];
    for (var i = 0; i < candidates.length; i++) {
      var value = candidates[i];
      if (!value) continue;
      var time = Date.parse(value);
      if (!isNaN(time)) return time;
    }
    return 0;
  }

  function formatDateString(dateValue) {
    if (!dateValue) return '';
    var raw = String(dateValue);
    var parts = raw.split('T');
    return parts[0] || raw;
  }

  function buildArticleUrl(post) {
    if (!post || !post.slug) return '#';
    var slug = encodeURIComponent(post.slug);
    if (basePath.articleUrl) {
      return basePath.articleUrl(post.slug);
    }
    return slug ? '/article.html?slug=' + slug : '#';
  }

  function buildCategoryUrl(slug) {
    if (!slug) return '#';
    if (basePath.categoryUrl) {
      return basePath.categoryUrl(slug);
    }
    return '/category.html?cat=' + encodeURIComponent(slug);
  }

  var url = new URL(window.location.href);

  function getCatSub() {
    var catParam = url.searchParams.get('cat');
    var subParam = url.searchParams.get('sub');

    var cat = slugify(catParam);
    var alias = slugify(subParam);
    var label = '';

    if (alias) {
      cat = alias;
      label = subParam || '';
    } else if (catParam) {
      label = catParam;
    }

    if (!cat) {
      var pathName = window.location && window.location.pathname
        ? window.location.pathname
        : '';
      var trimmedPath = pathName.replace(/\/+$/, '');
      var segments = trimmedPath.split('/');
      for (var i = segments.length - 1; i >= 0; i--) {
        var segment = segments[i];
        if (!segment) continue;

        var decoded = segment;
        try {
          decoded = decodeURIComponent(segment);
        } catch (err) {
          // ignore decode errors and fall back to the raw segment
        }

        var cleaned = decoded.replace(/\.html?$/i, '');
        if (!cleaned || /^index$/i.test(cleaned)) continue;

        var derived = slugify(cleaned);
        if (derived) {
          cat = derived;
          label = cleaned;
          break;
        }
      }
    }

    // opsionale: lexo edhe data-attr në <body data-cat="..." data-sub="...">
    var body = document.body;
    if (!cat && body.dataset.cat) {
      cat = slugify(body.dataset.cat);
      label = body.dataset.cat;
    }
    if (!cat && body.dataset.sub) {
      cat = slugify(body.dataset.sub);
      label = body.dataset.sub;
    }

    if (label) {
      label = String(label)
        .replace(/[_-]+/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
    }
    label = resolveCategoryLabelFromSlug(cat, label);

    return { cat: cat, label: label };
  }

  function patchHeader(ctx) {
    var cat = ctx && ctx.cat ? ctx.cat : '';
    var label = '';
    if (ctx && ctx.label) {
      label = String(ctx.label).trim();
    }
    var resolvedLabel = resolveCategoryLabelFromSlug(cat, label);
    if (ctx && resolvedLabel !== label) {
      ctx.label = resolvedLabel;
    }
    label = resolvedLabel;

    var bc = document.querySelector('.breadcrumb');
    if (bc) {
      var parts = ['<li><a href="' + HOME_URL + '">Home</a></li>'];
      if (cat) {
        var catUrl = buildCategoryUrl(cat);
        parts.push('<li class="active"><a href="' + escapeHtml(catUrl) + '">' + escapeHtml(label) + '</a></li>');
      }
      bc.innerHTML = parts.join('');
    }
    var h1 = document.querySelector('.page-title');
    if (h1) {
      h1.textContent = cat ? 'Category: ' + label : 'Category';
    }
    var subt = document.querySelector('.page-subtitle');
    if (subt) {
      subt.innerHTML = cat
        ? 'Showing all posts with category <i>' + escapeHtml(label) + '</i>'
        : 'Showing all posts.';
    }
  }

  function renderPost(p) {
    var dateTxt = (p.date || '').split('T')[0];
    var art = document.createElement('article');
    art.className = 'col-md-12 article-list';
    var articleUrl = buildArticleUrl(p);
    var hasCover = p.cover && String(p.cover).trim();
    var coverSrc = hasCover ? (basePath.resolve ? basePath.resolve(p.cover) : p.cover) : DEFAULT_IMAGE;
    var coverAlt = (p.title ? String(p.title) : 'AventurOO') + ' cover image';
    var figureClass = hasCover ? '' : ' class="no-cover"';
    var figureHtml =
      '<figure' + figureClass + '>' +
        '<a href="' + articleUrl + '">' +
          '<img src="' + escapeHtml(coverSrc) + '" alt="' + escapeHtml(coverAlt) + '">' +
        '</a>' +
      '</figure>';
    var categoryName = resolvePostCategoryLabel(p);
    var preferredSlug = ctx && ctx.cat ? ctx.cat : '';
    var categorySlug = resolvePostCategorySlug(p, preferredSlug);
    var categoryLink = categorySlug ? buildCategoryUrl(categorySlug) : '#';
    var categoryHtml = categoryName
      ? '<div class="category"><a href="' + escapeHtml(categoryLink) + '">' + escapeHtml(categoryName) + '</a></div>'
      : '';
    art.innerHTML =
      '<div class="inner">' +
        figureHtml +
        '<div class="details">' +
          '<div class="detail">' +
            categoryHtml +
            '<div class="time">' + (dateTxt || '') + '</div>' +
          '</div>' +
          '<h1><a href="' + articleUrl + '">' +
            (p.title || '') + '</a></h1>' +
          '<p>' + (p.excerpt || '') + '</p>' +
          '<footer>' +
            '<a class="btn btn-primary more" href="' + articleUrl + '">' +
              '<div>More</div><div><i class="ion-ios-arrow-thin-right"></i></div>' +
            '</a>' +
          '</footer>' +
        '</div>' +
      '</div>';
    return art;
  }

  function renderList(posts) {
    var box = document.getElementById('post-list');
    if (!box) return;
    box.innerHTML = '';
    if (!posts.length) {
      box.innerHTML = '<p class="lead">No posts yet for this category.</p>';
      return;
    }
    posts.forEach(function (p) { box.appendChild(renderPost(p)); });
  }


  function createSidebarArticle(post, variant) {
    var article = document.createElement('article');
    var articleUrl = buildArticleUrl(post);
    var title = escapeHtml(post && post.title ? post.title : '');
    var rawLabel = resolvePostCategoryLabel(post);
    var category = escapeHtml(rawLabel);
    var preferredSlug = ctx && ctx.cat ? ctx.cat : '';
    var categorySlug = resolvePostCategorySlug(post, preferredSlug);
    var categoryHref = categorySlug ? buildCategoryUrl(categorySlug) : '#';
    var categoryAnchor = category
      ? '<div class="category"><a href="' + escapeHtml(categoryHref) + '">' + category + '</a></div>'
      : '';
    var excerpt = escapeHtml(post && post.excerpt ? post.excerpt : '');
    var dateTxt = escapeHtml(formatDateString(post && post.date));
    var hasCover = post && post.cover;
    var coverSrc = hasCover ? (basePath.resolve ? basePath.resolve(post.cover) : post.cover) : DEFAULT_IMAGE;
    var cover = escapeHtml(coverSrc);
    var figureClass = hasCover ? '' : ' class="no-cover"';
    if (variant === 'full') {
      article.className = 'article-fw';
      article.innerHTML =
        '<div class="inner">' +
          '<figure' + figureClass + '>' +
            '<a href="' + articleUrl + '">' +
              '<img src="' + cover + '" alt="' + title + '">' +
            '</a>' +
          '</figure>' +
          '<div class="details">' +
            '<div class="detail">' +
              categoryAnchor +
              '<div class="time">' + dateTxt + '</div>' +
            '</div>' +
            '<h1><a href="' + articleUrl + '">' + title + '</a></h1>' +
            '<p>' + excerpt + '</p>' +
          '</div>' +
        '</div>';
    } else {
      article.className = 'article-mini';
      article.innerHTML =
        '<div class="inner">' +
          '<figure' + figureClass + '>' +
            '<a href="' + articleUrl + '">' +
              '<img src="' + cover + '" alt="' + title + '">' +
            '</a>' +
          '</figure>' +
          '<div class="padding">' +
            '<h1><a href="' + articleUrl + '">' + title + '</a></h1>' +
            '<div class="detail">' +
              categoryAnchor +
              '<div class="time">' + dateTxt + '</div>' +
            '</div>' +
          '</div>' +
        '</div>';
    }

    return article;
  }

  function createLineDivider() {
    var line = document.createElement('div');
    line.className = 'line';
    return line;
  }

  function appendFallbackMessage(container, text) {
    if (!container) return;
    var message = document.createElement('p');
    message.className = 'text-muted sidebar-fallback';
    message.textContent = text;
    container.appendChild(message);
  }

  function renderRecentSidebar(posts) {
    var container = document.getElementById('sidebar-recent-posts');
    if (!container) return;
    container.innerHTML = '';

    if (!posts.length) {
      appendFallbackMessage(container, 'No recent posts available.');
      return;
    }

    var first = posts[0];
    if (first) {
      container.appendChild(createSidebarArticle(first, 'full'));
    }

    var minis = posts.slice(1, 3);
    if (minis.length) {
      container.appendChild(createLineDivider());
      minis.forEach(function (post) {
        container.appendChild(createSidebarArticle(post, 'mini'));
      });
    }

    if (posts.length < 3) {
      appendFallbackMessage(container, 'Only ' + posts.length + ' recent post' + (posts.length === 1 ? '' : 's') + ' available.');
    }
  }

  function renderMiniSidebar(posts) {
    var container = document.getElementById('sidebar-mini-articles');
    if (!container) return;
    container.innerHTML = '';

    if (!posts.length) {
      appendFallbackMessage(container, 'No additional stories available.');
      return;
    }

    posts.forEach(function (post) {
      container.appendChild(createSidebarArticle(post, 'mini'));
    });

    if (posts.length < 10) {
      appendFallbackMessage(container, 'No more stories available.');
    }
  }

  var ctx = getCatSub();
  patchHeader(ctx);

  var taxonomyPromise = fetchSequential(TAXONOMY_SOURCES)
    .then(function (taxonomy) {
      populateCategoryLookup(taxonomy);
    })
    .catch(function (err) {
      console.warn('taxonomy load error', err);
    })
    .then(function () {
      var updatedLabel = resolveCategoryLabelFromSlug(ctx.cat, ctx.label);
      if (updatedLabel !== ctx.label) {
        ctx.label = updatedLabel;
        patchHeader(ctx);
      }
    });

  taxonomyPromise
    .then(function () {
      return fetchSequential(POSTS_SOURCES);
    })
    .then(function (all) {
      all = Array.isArray(all) ? all : [];
      var allSorted = all.slice().sort(function (a, b) {
        return getPostTimestamp(b) - getPostTimestamp(a);
      });
      var filtered = ctx.cat
        ? all.filter(function (p) {
          var slugs = resolvePostCategorySlugs(p);
          return slugs.indexOf(ctx.cat) !== -1;
        })
        : all.slice();

      if (ctx.cat && filtered.length) {
        var bestLabelInfo = null;
        for (var i = 0; i < filtered.length; i++) {
          var info = resolvePostCategoryLabelInfo(filtered[i]);
          if (!info.label) continue;
          if (!bestLabelInfo || info.priority < bestLabelInfo.priority) {
            bestLabelInfo = info;
          }
          if (bestLabelInfo && bestLabelInfo.priority === LABEL_PRIORITY_SUBCATEGORY) {
            break;
          }
        }

        if (bestLabelInfo && bestLabelInfo.label) {
          var currentLabel = ctx.label ? String(ctx.label).trim() : '';
          if (!currentLabel || slugify(currentLabel) === ctx.cat) {
            ctx.label = bestLabelInfo.label;
            patchHeader(ctx);
          }
        }
      }

      var sortedByDate = filtered.slice().sort(function (a, b) {
        return getPostTimestamp(b) - getPostTimestamp(a);
      });

      renderRecentSidebar(allSorted.slice(0, 3));
      var additionalPosts = allSorted.slice(3, 13);
      renderMiniSidebar(additionalPosts);

      var PER_PAGE = 12;
      var pageParam = parseInt(url.searchParams.get('page'), 10);
      var page = !isNaN(pageParam) && pageParam > 0 ? pageParam : 1;
      var totalPages = Math.ceil(filtered.length / PER_PAGE);
      if (totalPages > 0 && page > totalPages) page = totalPages;

      var start = (page - 1) * PER_PAGE;
      var pagedPosts = filtered.slice(start, start + PER_PAGE);
      renderList(pagedPosts);

      if (typeof renderPagination === 'function') {
        var baseQuery = ctx.cat ? '?cat=' + encodeURIComponent(ctx.cat) : '';
        renderPagination('pagination', filtered.length, PER_PAGE, page, baseQuery);
      }

      var infoBox = document.getElementById('pagination-info');
      if (infoBox) {
        var displayPage = totalPages === 0 ? 0 : page;
        infoBox.textContent = 'Showing ' + pagedPosts.length + ' results of ' + filtered.length + ' — Page ' + displayPage + ' of ' + totalPages;
      }
    })
    .catch(function (err) {
      console.error('posts load error', err);
    });
})();
