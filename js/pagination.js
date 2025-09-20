(function (root) {
  function cleanBase(base) {
    if (typeof base !== 'string') return '';
    var cleaned = base.trim();
    if (!cleaned) return '';
    cleaned = cleaned.replace(/([?&])page=\d+/gi, function (match, sep) {
      return sep === '?' ? '?' : '';
    });
    cleaned = cleaned.replace(/\?&/, '?');
    cleaned = cleaned.replace(/&&+/g, '&');
    cleaned = cleaned.replace(/([?&])$/, '');
    return cleaned;
  }

  function buildUrl(base, page) {
    var target = base;
    if (!target) {
      var loc = root && root.location ? root.location.pathname : '';
      target = loc || '?';
    }

    if (target === '?') {
      return '?page=' + page;
    }

    var separator;
    if (target.indexOf('?') === -1) {
      separator = '?';
    } else {
      separator = target.charAt(target.length - 1) === '?' ? '' : '&';
    }

    return target + separator + 'page=' + page;
  }

  function appendItem(container, page, label, options) {
    options = options || {};
    var li = document.createElement('li');
    if (options.className) li.className = options.className;

    if (options.disabled) {
      li.className = li.className ? li.className + ' disabled' : 'disabled';
      var span = document.createElement('span');
      span.innerHTML = label;
      li.appendChild(span);
      container.appendChild(li);
      return;
    }

    var a = document.createElement('a');
    a.innerHTML = label;
    a.href = buildUrl(options.base, page);
    li.appendChild(a);

    if (options.active) {
      li.className = li.className ? li.className + ' active' : 'active';
    }

    container.appendChild(li);
  }

  function appendEllipsis(container) {
    var li = document.createElement('li');
    li.className = 'disabled ellipsis';
    var span = document.createElement('span');
    span.innerHTML = '&hellip;';
    li.appendChild(span);
    container.appendChild(li);
  }

  function renderPagination(containerId, totalItems, perPage, currentPage, baseUrl) {
    var list = document.getElementById(containerId);
    if (!list) return;

    totalItems = parseInt(totalItems, 10) || 0;
    perPage = parseInt(perPage, 10) || 1;
    currentPage = parseInt(currentPage, 10) || 1;

    var totalPages = Math.ceil(totalItems / perPage);
    list.innerHTML = '';

    if (totalPages <= 1) {
      list.style.display = 'none';
      return;
    }

    list.style.display = '';

    var cleanedBase = cleanBase(baseUrl || '');
    var prevPage = currentPage > 1 ? currentPage - 1 : 1;
    appendItem(list, prevPage, '<i class="ion-ios-arrow-left"></i>', {
      className: 'prev',
      disabled: currentPage === 1,
      base: cleanedBase
    });

    if (totalPages <= 13) {
      for (var i = 1; i <= totalPages; i++) {
        appendItem(list, i, String(i), {
          active: i === currentPage,
          base: cleanedBase
        });
      }
    } else {
      appendItem(list, 1, '1', {
        active: currentPage === 1,
        base: cleanedBase
      });

      var start = Math.max(2, currentPage - 1);
      var end = Math.min(totalPages - 1, currentPage + 1);

      if (start > 2) appendEllipsis(list);

      for (var j = start; j <= end; j++) {
        appendItem(list, j, String(j), {
          active: j === currentPage,
          base: cleanedBase
        });
      }

      if (end < totalPages - 1) appendEllipsis(list);

      appendItem(list, totalPages, String(totalPages), {
        active: currentPage === totalPages,
        base: cleanedBase
      });
    }

    var nextPage = currentPage < totalPages ? currentPage + 1 : totalPages;
    appendItem(list, nextPage, '<i class="ion-ios-arrow-right"></i>', {
      className: 'next',
      disabled: currentPage === totalPages,
      base: cleanedBase
    });
  }

  root.renderPagination = renderPagination;
})(typeof window !== 'undefined' ? window : this);
