"""Shared v49 patch definitions used by the ARM regression checks."""
import json
from pathlib import Path

def _decode(value):
    if isinstance(value, str) and value.startswith("0x"):
        return int(value, 16)
    if isinstance(value, list):
        return tuple(_decode(item) for item in value)
    if isinstance(value, dict):
        return {key: _decode(item) for key, item in value.items()}
    return value

_profile = json.loads(Path(__file__).with_name("profiles").joinpath("v49.json").read_text(encoding="utf-8"))
for _name, _value in _profile["constants"].items():
    globals()[_name] = _decode(_value)

def branch(at, target, link=False):
    delta = target - at - 8
    assert delta % 4 == 0 and -(1 << 25) <= delta < (1 << 25)
    return (0xEB000000 if link else 0xEA000000) | ((delta // 4) & 0xFFFFFF)
