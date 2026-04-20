"""
backend/app/fusion/tag_registry.py

Maps MAC addresses to friendly tag IDs (e.g. TRAKN-A3F2).

- Auto-registers any new MAC on first sight.
- IDs are short (4 uppercase hex chars) so they fit on a sticker.
- In-memory only for now — persists for the lifetime of the server process.
"""

import hashlib
import time


def _generate_id(mac: str) -> str:
    """
    Deterministic 4-char uppercase alphanumeric suffix derived from the MAC.
    Stable across backend restarts so parent-app saved tag_ids keep working.
    """
    digest = hashlib.sha1(mac.encode("utf-8")).hexdigest().upper()
    # Use hex chars (0-9,A-F) — still fits on a sticker and avoids ambiguity
    # between I/1 and O/0.
    return "TRAKN-" + digest[:4]


class TagRegistry:
    def __init__(self):
        # mac → tag record
        self._by_mac:    dict[str, dict] = {}
        # tag_id → tag record  (same dict objects, two indexes)
        self._by_tag_id: dict[str, dict] = {}

    def register(self, mac: str) -> str:
        """
        Return the tag_id for this MAC, creating one if it does not exist yet.
        Thread-safe enough for single-process asyncio use.
        """
        if mac in self._by_mac:
            return self._by_mac[mac]["tag_id"]

        tag_id = _generate_id(mac)

        record = {
            "tag_id":          tag_id,
            "mac":             mac,
            "name":            None,        # set later via PATCH /api/v1/tags/{id}
            "registered_at":   time.time(),
            "last_seen":       time.time(),
        }
        self._by_mac[mac]        = record
        self._by_tag_id[tag_id]  = record
        return tag_id

    def touch(self, mac: str) -> None:
        """Update last_seen timestamp for a known MAC."""
        if mac in self._by_mac:
            self._by_mac[mac]["last_seen"] = time.time()

    def tag_id_for(self, mac: str) -> str | None:
        rec = self._by_mac.get(mac)
        return rec["tag_id"] if rec else None

    def mac_for(self, tag_id: str) -> str | None:
        rec = self._by_tag_id.get(tag_id)
        return rec["mac"] if rec else None

    def get(self, tag_id: str) -> dict | None:
        return self._by_tag_id.get(tag_id)

    def all(self) -> list[dict]:
        return list(self._by_tag_id.values())

    def set_name(self, tag_id: str, name: str) -> bool:
        """Rename a tag. Returns False if tag_id not found."""
        rec = self._by_tag_id.get(tag_id)
        if rec is None:
            return False
        rec["name"] = name
        return True


# Module-level singleton shared across gateway, websocket, and tags API
registry = TagRegistry()
