"""Constants for First Words."""
from __future__ import annotations

DOMAIN = "first_words"

CONF_CHILD = "child_name"
CONF_BIRTHDAY = "birthday"
CONF_PEOPLE = "people"
CONF_MOUNT = "mount_path"
CONF_FOLDER = "folder"
CONF_STORAGE_NAME = "storage_name"
CONF_OFFSITE = "offsite_note"

DEFAULT_MOUNT = "/media/FirstWords"
DEFAULT_FOLDER = "First Words"
DEFAULT_STORAGE_NAME = "the NAS"
DEFAULT_PEOPLE = "Parent One: Mama\nParent Two: Dada"

PANEL_URL_PATH = "first-words"
PANEL_ELEMENT = "first-words-panel"
PANEL_JS_URL = "/first_words_panel"
PANEL_TITLE = "First Words"
PANEL_ICON = "mdi:account-voice"

API_BASE = "/api/first_words"

SIGNAL_CHANGED = "first_words_changed"
EVENT_ADDED = "first_words_added"
EVENT_UPDATED = "first_words_updated"
EVENT_DELETED = "first_words_deleted"

SERVICE_EXPORT_ZIP = "export_zip"
SERVICE_KEEPSAKE = "make_keepsake"
SERVICE_IMPORT_JSON = "import_json"


def both_label(people: list[dict[str, str]]) -> str:
    """'Mama & Dada' (or 'A, B & C'); empty with fewer than two people. Same rule as the panel."""
    labels = [p["label"] for p in people]
    if len(labels) < 2:
        return ""
    return labels[0] + " & " + labels[1] if len(labels) == 2 else ", ".join(labels[:-1]) + " & " + labels[-1]


def parse_people(text: str) -> list[dict[str, str]]:
    """'Alex: Mama' lines -> [{name, label}]. A bare name is its own label."""
    out: list[dict[str, str]] = []
    for line in str(text or "").replace(",", "\n").splitlines():
        if not line.strip():
            continue
        name, _, label = line.partition(":")
        name, label = name.strip(), label.strip() or name.strip()
        if name:
            out.append({"name": name[:40], "label": label[:40]})
    return out
