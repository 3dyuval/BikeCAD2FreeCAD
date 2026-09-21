"""BCad file parser.

Reads a .bcad (Java Properties XML) file into a key-value store with
typed accessors.
"""

import xml.etree.ElementTree as ET
from pathlib import Path


class BcadParser:
    """Parse a .bcad (Java Properties XML) file into a key-value store."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.data: dict[str, str] = {}
        self._parse()

    def _parse(self):
        tree = ET.parse(self.path)
        root = tree.getroot()
        for entry in root.findall("entry"):
            key = entry.get("key", "")
            value = entry.text or ""
            self.data[key] = value

    def get_str(self, key: str, default: str = "") -> str:
        return self.data.get(key, default)

    def get_float(self, key: str, default: float = 0.0) -> float:
        raw = self.data.get(key)
        if raw is None:
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    def get_int(self, key: str, default: int = 0) -> int:
        raw = self.data.get(key)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        raw = self.data.get(key)
        if raw is None:
            return default
        return raw.strip().lower() == "true"

    def has(self, key: str) -> bool:
        return key in self.data

    def keys_matching(self, substring: str) -> list[str]:
        """Return all keys containing the given substring (case-insensitive)."""
        sub = substring.lower()
        return [k for k in self.data if sub in k.lower()]
