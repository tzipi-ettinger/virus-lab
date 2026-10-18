"""Fold Hebrew text for matching and search: one spelling for what a person sees as the same.

Owner: B
"""

import unicodedata

# Removed without a space: רמב״ם, רמב"ם and רמבם all fold to the same thing.
_QUOTES = str.maketrans("", "", "'\"`׳״‘’“”")


def fold_text(text: str) -> str:
    """Drop niqqud and quotes, other punctuation becomes a space, collapse spaces, casefold."""
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    without_quotes = without_marks.translate(_QUOTES)
    spaced = "".join(char if char.isalnum() else " " for char in without_quotes)
    return " ".join(spaced.split()).casefold()
