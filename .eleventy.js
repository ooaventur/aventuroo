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
    "_redirects",
    "_health"
  ];

  passthroughPaths.forEach((path) => {
    eleventyConfig.addPassthroughCopy(path);
  });

  eleventyConfig.addPassthroughCopy({ "src/site/_headers": "_headers" });

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

  eleventyConfig.addFilter("padNumber", (value, length = 2) => {
    const size = Number.isFinite(length) && length > 0 ? Math.floor(length) : 2;
    const number = Number.parseInt(value, 10);
    if (Number.isFinite(number)) {
      return String(Math.abs(number)).padStart(size, "0");
    }
    const stringValue = value == null ? "" : String(value);
    if (stringValue.length >= size) {
      return stringValue;
    }
    return stringValue.padStart(size, "0");
  });

  const ARCHIVE_ACRONYMS = new Set([
    "AI",
    "AR",
    "ETF",
    "EV",
    "EVS",
    "IPO",
    "NFT",
    "TV",
    "UK",
    "US",
    "UAE",
    "VPN",
    "VR"
  ]);

  eleventyConfig.addFilter("formatArchiveLabel", (value) => {
    if (value == null) {
      return "";
    }

    const normalized = String(value)
      .replace(/[-_]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();

    if (!normalized) {
      return "";
    }

    return normalized.split(" ").map((word) => {
      if (!word) {
        return "";
      }

      const alpha = word.replace(/[^a-zA-Z]/g, "");
      if (alpha && ARCHIVE_ACRONYMS.has(alpha.toUpperCase())) {
        return alpha.toUpperCase();
      }

      return word.charAt(0).toUpperCase() + word.slice(1);
    }).join(" ");
  });

  eleventyConfig.addFilter("formatArchiveMonth", (monthValue, yearValue) => {
    const monthNumber = Number.parseInt(monthValue, 10);
    const yearNumber = Number.parseInt(yearValue, 10);

    if (Number.isFinite(monthNumber) && Number.isFinite(yearNumber)) {
      const date = new Date(Date.UTC(yearNumber, monthNumber - 1, 1));
      if (!Number.isNaN(date.valueOf())) {
        try {
          return date.toLocaleDateString("en-US", { month: "long", year: "numeric" });
        } catch (error) {
          // Ignore locale errors and fall through to fallback formatting.
        }
      }
      return `${yearNumber}-${String(monthNumber).padStart(2, "0")}`;
    }

    if (yearValue && monthValue) {
      return `${yearValue}-${String(monthValue).padStart(2, "0")}`;
    }

    return String(yearValue || monthValue || "");
  });

  eleventyConfig.addFilter("formatArchiveDate", (value) => {
    if (!value) {
      return "";
    }

    const date = new Date(value);
    if (!Number.isNaN(date.valueOf())) {
      try {
        return date.toLocaleDateString("en-US", {
          year: "numeric",
          month: "long",
          day: "numeric"
        });
      } catch (error) {
        // Ignore locale errors and fall through to fallback formatting.
      }
    }

    if (typeof value === "string" && value.match(/^\d{4}-\d{2}-\d{2}$/)) {
      const parts = value.split("-");
      return `${parts[0]}-${parts[1]}-${parts[2]}`;
    }

    return String(value);
  });

  eleventyConfig.addFilter("archiveHost", (urlValue) => {
    if (!urlValue) {
      return "";
    }

    try {
      const url = new URL(urlValue, "https://example.com");
      return url.hostname.replace(/^www\./i, "");
    } catch (error) {
      return "";
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
