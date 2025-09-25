const fs = require('fs');
const path = require('path');

const projectRoot = path.join(__dirname, '..', '..', '..');
const menuJsonPath = path.join(projectRoot, 'data', 'menu.json');
const taxonomyJsonPath = path.join(projectRoot, 'data', 'taxonomy.json');

const readJson = (filePath) => {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (error) {
    return null;
  }
};

const normalizeMenuItems = (items = []) => items.map((item) => ({
  label: item.title || item.label || '',
  path: item.href || (item.slug ? `/category/${item.slug}` : ''),
  children: Array.isArray(item.children) ? normalizeMenuItems(item.children) : []
}));

const buildMenuFromTaxonomy = (taxonomy) => {
  if (!taxonomy || !Array.isArray(taxonomy.categories)) {
    return null;
  }

  const nodes = new Map();
  taxonomy.categories.forEach((category) => {
    nodes.set(category.slug, {
      label: category.title || category.slug,
      path: `/category/${category.slug}`,
      children: []
    });
  });

  taxonomy.categories.forEach((category) => {
    if (typeof category.group === 'string') {
      const parent = nodes.get(category.group);
      const child = nodes.get(category.slug);
      if (parent && child) {
        parent.children.push(child);
      }
    }
  });

  const topLevel = taxonomy.categories.filter((category) => !category.group || Array.isArray(category.group));
  return topLevel.map((category) => nodes.get(category.slug)).filter(Boolean);
};

module.exports = () => {
  const menuData = readJson(menuJsonPath);
  if (menuData && Array.isArray(menuData.items)) {
    return { menu: normalizeMenuItems(menuData.items) };
  }

  const taxonomyData = readJson(taxonomyJsonPath);
  const taxonomyMenu = buildMenuFromTaxonomy(taxonomyData);
  if (taxonomyMenu) {
    return { menu: taxonomyMenu };
  }

  return { menu: [] };
};
