// Load common head and footer partials
(async function loadPartials() {
  async function fetchText(path) {
    const response = await fetch(path);
    if (!response.ok) {
      throw new Error(`Failed to load ${path}: ${response.status}`);
    }
    return await response.text();
  }

  try {
    const [headHTML, footerHTML] = await Promise.all([
      fetchText('partials/head.html'),
      fetchText('partials/footer.html'),
    ]);
    document.head.insertAdjacentHTML('beforeend', headHTML);
    document.body.insertAdjacentHTML('beforeend', footerHTML);
  } catch (err) {
    console.error('Error loading partials', err);
  }
})();
