import sys
import pathlib

import pytest

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from autopost.utils import slugify

SLUGIFY_FUNCS = [slugify]

@pytest.mark.parametrize("slugify_func", SLUGIFY_FUNCS)
def test_slugify_non_english(slugify_func):
    assert slugify_func("Fëmijë të mrekullueshëm") == "femije-te-mrekullueshem"
    assert slugify_func("Český Krumlov") == "cesky-krumlov"
    assert slugify_func("¡Hola señor!") == "hola-senor"
