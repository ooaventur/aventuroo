# Manual verification for `readSubcategorySlug`

These steps confirm that the category feed keeps the expected subcategory slug when the page is loaded with different query string combinations.

## Automated helper

Run the lightweight Node.js helper to exercise the function with representative query strings:

```
node tests/manual/read-subcategory-slug.js
```

The script covers the following scenarios:

- `?cat=travel/europe` &rarr; derives the `europe` subcategory from the combined slug.
- `?cat=travel&sub=Outdoor%20Fun` &rarr; honours the explicit `sub` parameter (`outdoor-fun`).
- `?cat=travel/outdoor/hiking` &rarr; uses the deepest segment of the slug as the subcategory (`hiking`).
- `?cat=travel` with `data-subcategory="travel/Family Trips"` &rarr; falls back to the section attribute (`family-trips`).
- `?cat=travel` with `data-subcategory` defined via the `dataset` API &rarr; prefers the dataset value (`solo`).

All checks should report a ✓ result. Any ✗ output indicates a regression.

## Browser spot-check (optional)

1. Start the local site (for example with `npm run build` and serve the generated output).
2. Visit `/category.html?cat=travel/europe` and confirm that the feed requests `/data/categories/travel/europe/index.json`.
3. Visit `/category.html?cat=travel&sub=outdoor-fun` and confirm that the feed requests `/data/categories/travel/outdoor-fun/index.json`.

These spot checks ensure that the UI uses the same slug parsing logic as the helper.
