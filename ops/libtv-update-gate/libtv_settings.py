"""What the pinned LibTV program downloads from LibTV at run time, and how a change in it is put into words.

The 1.1.3 program's embedded settings name eleven channels; its code reads only two of them (182, the model list,
and 188, the image shortcut scenes). The gate also watches 186 (camera controls) and 190 (voices), which the
issue named and which cost one free request each. None of this needs a login.
"""

from __future__ import annotations

CHANNELS = {"182": "models", "188": "shortcut scenes", "186": "camera controls", "190": "voices"}
MODEL_FIELDS = ("vip", "pricingRule")   # the two model fields that change what a run costs or who may run it
IDENTITY_KEYS = ("scene", "key", "modelKey", "voice_id", "id", "name")
SHOWN = 8


def _ids(items: list[str]) -> str:
    shown = ", ".join(items[:SHOWN])
    return shown + (f", +{len(items) - SHOWN} more" if len(items) > SHOWN else "")


def _models(payload: dict) -> dict[str, dict]:
    out = {}
    for modality, items in payload.items():
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and "modelKey" in item:
                    out[f"{modality}/{item['modelKey']}"] = item
    return out


def _summarize_models(label: str, old: dict, new: dict) -> list[str]:
    before, after = _models(old), _models(new)
    lines = [f'{label}: added {k} "{after[k].get("modelName", "")}"' for k in after if k not in before]
    lines += [f'{label}: removed {k} "{before[k].get("modelName", "")}"' for k in before if k not in after]
    other = 0
    for key in before.keys() & after.keys():
        for field in MODEL_FIELDS:
            if before[key].get(field) != after[key].get(field):
                lines.append(f"{label}: {key} {field} {before[key].get(field)!r} -> {after[key].get(field)!r}")
        rest = lambda m: {k: v for k, v in m.items() if k not in MODEL_FIELDS}  # noqa: E731
        if rest(before[key]) != rest(after[key]):
            other += 1
    if other:
        lines.append(f"{label}: other fields changed on {other} models (icons, descriptions, times; not itemised)")
    return lines


def _identity(item: object) -> str | None:
    if isinstance(item, dict):
        for key in IDENTITY_KEYS:
            if key in item:
                return str(item[key])
    return None


def _summarize_generic(label: str, old: dict, new: dict) -> list[str]:
    lines = []
    for key in sorted(set(old) | set(new)):
        a, b = old.get(key), new.get(key)
        if a == b:
            continue
        if key not in old or key not in new:
            lines.append(f"{label}: {key} {'added' if key not in old else 'removed'}")
        elif isinstance(a, list) and isinstance(b, list) and all(_identity(i) is not None for i in a + b):
            ia, ib = {_identity(i): i for i in a}, {_identity(i): i for i in b}
            added = [k for k in ib if k not in ia]
            removed = [k for k in ia if k not in ib]
            changed = [k for k in ia.keys() & ib.keys() if ia[k] != ib[k]]
            lines.append(
                f"{label}: {key}: {len(added)} added ({_ids(added)}), {len(removed)} removed ({_ids(removed)}), "
                f"{len(changed)} changed"
            )
        else:
            lines.append(f"{label}: {key} changed")
    return lines


def summarize(channel_id: str, old: dict, new: dict) -> list[str]:
    """The lines that say what changed between two snapshots of one channel; empty when nothing did."""
    label = CHANNELS[channel_id]
    if old == new:
        return []
    if isinstance(old, list) or isinstance(new, list):   # the voices channel is a bare list: read it as {"items": [...]}
        old, new = {"items": old if isinstance(old, list) else []}, {"items": new if isinstance(new, list) else []}
    if channel_id == "182" and isinstance(old, dict) and isinstance(new, dict):
        return _summarize_models(label, old, new)
    return _summarize_generic(label, old, new)
