"""Bound a JSON result to a byte budget, and say exactly what was cut.

Sizes are measured as ASCII-escaped JSON, which is never smaller than the UTF-8 form a
transport sends, so a bounded result stays within its budget either way.
"""

import copy
import json


def encoded_size(value):
    return len(json.dumps(value))


def _nodes(value, path=""):
    """Yield ``(container, key, path)`` for every string and list below ``value``."""
    items = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, list) else ()
    for key, child in items:
        child_path = f"{path}.{key}" if isinstance(value, dict) else f"{path}[{key}]"
        child_path = child_path.lstrip(".")
        if isinstance(child, (str, list)):
            yield value, key, child_path
        if isinstance(child, (dict, list)):
            yield from _nodes(child, child_path)


def _fit(sequence, budget):
    """The longest prefix of ``sequence`` whose encoded size is within ``budget``."""
    low, high = 0, len(sequence)
    while low < high:
        middle = (low + high + 1) // 2
        if encoded_size(sequence[:middle]) <= budget:
            low = middle
        else:
            high = middle - 1
    return sequence[:low]


def bound(value, limit):
    """Return ``(value, cuts, total_bytes)`` with ``value`` at most ``limit`` bytes.

    Each cut is ``{"field", "original_chars", "kept_chars"}`` for text or
    ``{"field", "original_items", "kept_items"}`` for a list. Text is cut before whole
    list items are dropped, whenever cutting the largest text alone is enough.
    """
    total = encoded_size(value)
    if total <= limit:
        return value, [], total
    value = copy.deepcopy(value)
    cuts = {}
    while (size := encoded_size(value)) > limit:
        sized = [(encoded_size(container[key]), container, key, path) for container, key, path in _nodes(value)]
        sized = [entry for entry in sized if entry[0] > 2]  # "" and [] cannot shrink further
        if not sized:
            break
        excess = size - limit
        texts = [entry for entry in sized if isinstance(entry[1][entry[2]], str)]
        largest_text = max(texts, key=lambda entry: entry[0], default=None)
        chosen = largest_text if largest_text and largest_text[0] - 2 >= excess else max(sized, key=lambda e: e[0])
        node_size, container, key, path = chosen
        original = container[key]
        container[key] = _fit(original, max(2, node_size - excess))
        if isinstance(original, str):
            cut = cuts.setdefault(path, {"field": path, "original_chars": len(original)})
            cut["kept_chars"] = len(container[key])
        else:
            cut = cuts.setdefault(path, {"field": path, "original_items": len(original)})
            cut["kept_items"] = len(container[key])
    return value, list(cuts.values()), total
