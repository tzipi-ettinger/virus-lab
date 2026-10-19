"""The closed list of senders (senders.yaml) and mapping free text onto it (SPEC 5.5).

The rule for *which* institution is the sender (the payer, not the logo) lives in
the extraction prompt. Here we only map the text the model read to one name on
the list, or keep it as written and flag it.

Owner: B
"""

from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

from app.rules.issues import make_issue
from app.rules.text import fold_text
from app.schemas.api import Issue

SENDERS_FILE = Path(__file__).with_name("senders.yaml")


@dataclass(frozen=True)
class Sender:
    name: str
    aliases: tuple[str, ...]

    def keys(self) -> list[str]:
        return [fold_text(text) for text in (self.name, *self.aliases)]


@cache
def load_senders(path: Path = SENDERS_FILE) -> tuple[Sender, ...]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return tuple(
        Sender(name=item["name"], aliases=tuple(item.get("aliases") or ()))
        for item in data["senders"]
    )


def sender_names() -> list[str]:
    return [sender.name for sender in load_senders()]


def match_sender(text: str, senders: tuple[Sender, ...]) -> str | None:
    """The sender whose name or alias equals the text, or the only one found in it as words.

    Two different senders in one text ("מכבי העמק") is ambiguous: no match. A key
    found only inside a longer key that was also found does not count ("אסותא אשדוד"
    inside "אסותא אשדוד כלניות").
    """
    folded = fold_text(text)
    if not folded:
        return None
    padded = f" {folded} "
    hits = []
    for sender in senders:
        for key in sender.keys():
            if key == folded:
                return sender.name
            if key and f" {key} " in padded:
                hits.append((sender.name, key))
    found = {
        name
        for name, key in hits
        if not any(other != key and f" {key} " in f" {other} " for _, other in hits)
    }
    return found.pop() if len(found) == 1 else None


def normalize_sender(raw: str | None) -> tuple[str | None, list[Issue]]:
    """The list name, or the text as written + SENDER_UNKNOWN (SPEC 5.5)."""
    text = " ".join((raw or "").split())
    if not text:
        return None, []
    name = match_sender(text, load_senders())
    if name is None:
        return text, [make_issue("SENDER_UNKNOWN")]
    return name, []
