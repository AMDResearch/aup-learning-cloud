import json
import html
from sphinx.util import logging

def normalize_key(key):
    return key.replace(" ", "_").lower().strip()

def _parse_show_when_tokens(show_when_str, separator="="):
    """Parse show-when string (key=value; space or + between pairs) into dict key -> list of values."""
    pairs = {}
    for token in show_when_str.replace("+", " ").split():
        token = token.strip()
        if not token or separator not in token:
            continue
        key, value = token.split(separator, 1)
        if key and value:
            pairs.setdefault(key, []).append(value.strip())
    return pairs

def kv_to_data_attr(name, kv_str, separator="="):
    """
    Convert key=value pairs (space or + between pairs) to a data attribute.
    Example: "key=value other=x" or "key=value+other=x" -> data-name='{"key":["value"],"other":["x"]}'
    """
    pairs = _parse_show_when_tokens(kv_str, separator)
    return f'data-{name}="{html.escape(json.dumps(pairs))}"' if pairs else ""


# Default state used when rendering HTML so conditional blocks are hidden by default
# until JS runs. Must match the first option of each "root" selector (e.g. family=radeon-pro, gpu=ai-r9700).
SELECTOR_DEFAULT_STATE = {
    "family": "radeon-pro",
    "gpu": "ai-r9700",
    "deploy": "single",
    "os": "24.04",
}

def state_matches_show_when(show_when_str, state=None):
    """Return True if state satisfies the show-when condition (for server-side hidden class)."""
    if not show_when_str:
        return True
    conditions = _parse_show_when_tokens(show_when_str)
    if not conditions:
        return True
    state = state or SELECTOR_DEFAULT_STATE
    for key, allowed in conditions.items():
        actual = state.get(key)
        if actual is None:
            return False
        if actual not in allowed:
            return False
    return True


logger = logging.getLogger(__name__)
