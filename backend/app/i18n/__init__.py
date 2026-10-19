"""Texts the user sees, by key, from one YAML file per language (he.yaml for now).

Code holds only keys, so wording changes in one place and a new language is a
new file. A missing key raises KeyError, so a test fails before a user sees it.

Owner: B
"""

from functools import cache
from pathlib import Path

import yaml

I18N_DIR = Path(__file__).parent
DEFAULT_LANGUAGE = "he"


@cache
def load_texts(language: str = DEFAULT_LANGUAGE) -> dict:
    return yaml.safe_load((I18N_DIR / f"{language}.yaml").read_text(encoding="utf-8"))


def text_for(key: str, language: str = DEFAULT_LANGUAGE) -> str:
    """A dotted key: issues.DATE_INVALID is the text under issues: DATE_INVALID: in the file."""
    node = load_texts(language)
    for part in key.split("."):
        node = node[part]
    if not isinstance(node, str):
        raise KeyError(key)
    return node
