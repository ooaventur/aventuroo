module.exports = function (eleventyConfig) {
  const passthroughPaths = [
    "css",
    "js",
    "images",
    "fonts",
    "scripts",
    "data",
    "assets",
    "autopost",
    "_redirects"
  ];

  passthroughPaths.forEach((path) => {
    eleventyConfig.addPassthroughCopy(path);
  });

  eleventyConfig.addFilter("toAbsoluteUrl", (url, base) => {
    if (!url) {
      return url;
    }

    try {
      return new URL(url, base).href;
    } catch (error) {
      return url;
    }
  });

  return {
    dir: {
      input: "src/site",
      includes: "_includes",
      data: "_data",
      output: "_site"
    }
  };
};
