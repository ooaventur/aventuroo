const assert = require('assert');

function slugifySegment(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function normalizeSlug(value) {
  if (value == null) {
    return '';
  }
  var str = String(value).trim();
  if (!str) {
    return '';
  }
  var lowered = str.toLowerCase();
  if (lowered.indexOf('/') !== -1) {
    var segments = lowered.split('/');
    var cleaned = [];
    for (var i = 0; i < segments.length; i++) {
      var part = slugifySegment(segments[i]);
      if (part) {
        cleaned.push(part);
      }
    }
    return cleaned.join('/');
  }
  if (/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(lowered)) {
    return lowered;
  }
  return slugifySegment(lowered);
}

function splitCategorySlug(value) {
  var normalized = normalizeSlug(value);
  if (!normalized) {
    return { category: '', subcategory: '' };
  }
  var parts = normalized.split('/');
  var category = parts.shift() || '';
  var subcategory = parts.join('/');
  return {
    category: category,
    subcategory: subcategory || ''
  };
}

function readSubcategorySlug(section, search) {
  var attr = '';
  if (section) {
    attr =
      (typeof section.getAttribute === 'function'
        ? section.getAttribute('data-subcategory')
        : '') ||
      (section.dataset ? section.dataset.subcategory : '') ||
      '';
  }
  var attrParts = splitCategorySlug(attr);
  var params;
  try {
    params = new URLSearchParams(search || '');
  } catch (err) {
    return attrParts.subcategory || attrParts.category || '';
  }
  var fromQuery = params.get('sub') || params.get('subcategory');
  if (!fromQuery) {
    var fromCat = params.get('cat') || params.get('category') || params.get('slug');
    var catParts = splitCategorySlug(fromCat);
    fromQuery = catParts.subcategory;
  }
  var fromQueryParts = splitCategorySlug(fromQuery);
  return (
    fromQueryParts.subcategory ||
    fromQueryParts.category ||
    attrParts.subcategory ||
    attrParts.category ||
    ''
  );
}

function createSection(options) {
  options = options || {};
  var attrValues = {
    'data-subcategory': options.attrSubcategory || ''
  };
  var dataset = Object.assign({}, options.dataset || {});
  return {
    dataset: dataset,
    getAttribute: function (name) {
      if (Object.prototype.hasOwnProperty.call(attrValues, name)) {
        return attrValues[name];
      }
      return '';
    }
  };
}

function runCase(description, search, sectionOptions, expected) {
  var section = createSection(sectionOptions);
  var actual = readSubcategorySlug(section, search);
  try {
    assert.strictEqual(actual, expected);
    console.log('✓ ' + description);
  } catch (err) {
    console.error('✗ ' + description + '\n  expected: ' + expected + '\n  actual:   ' + actual);
    throw err;
  }
}

function main() {
  runCase('reads subcategory from cat parameter', '?cat=travel/europe', null, 'europe');
  runCase(
    'uses explicit sub parameter when provided',
    '?cat=travel&sub=Outdoor%20Fun',
    null,
    'outdoor-fun'
  );
  runCase('keeps deepest segment for nested cat slug', '?cat=travel/outdoor/hiking', null, 'hiking');
  runCase(
    'falls back to section attribute when query lacks subcategory',
    '?cat=travel',
    { attrSubcategory: 'travel/Family Trips' },
    'family-trips'
  );
  runCase(
    'prefers dataset subcategory over attr when provided',
    '?cat=travel',
    { dataset: { subcategory: 'Travel/Solo' } },
    'solo'
  );
}

if (require.main === module) {
  try {
    main();
  } catch (err) {
    process.exitCode = 1;
  }
}
