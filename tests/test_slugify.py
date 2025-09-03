import sys
import pathlib

import pytest

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1] / "autopost"))

import pull_travel, pull_lifestyle, pull_culture, pull_stories, rss_to_html

SLUGIFY_FUNCS = [
    pull_travel.slugify,
    pull_lifestyle.slugify,
    pull_culture.slugify,
    pull_stories.slugify,
    rss_to_html.slugify,
]

@pytest.mark.parametrize("slugify_func", SLUGIFY_FUNCS)
def test_slugify_non_english(slugify_func):
    assert slugify_func("Fëmijë të mrekullueshëm") == "femije-te-mrekullueshem"
    assert slugify_func("Český Krumlov") == "cesky-krumlov"
    assert slugify_func("¡Hola señor!") == "hola-senor"
