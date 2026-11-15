"""First Words: save a child's first words as plain files on a network share."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import voluptuous as vol

from homeassistant.components.frontend import async_register_built_in_panel, async_remove_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .api import async_register_views
from .const import (
    CONF_BIRTHDAY,
    CONF_CHILD,
    CONF_FOLDER,
    CONF_MOUNT,
    CONF_OFFSITE,
    CONF_PEOPLE,
    CONF_STORAGE_NAME,
    DEFAULT_FOLDER,
    DEFAULT_MOUNT,
    DEFAULT_STORAGE_NAME,
    DOMAIN,
    PANEL_ELEMENT,
    PANEL_ICON,
    PANEL_JS_URL,
    PANEL_TITLE,
    PANEL_URL_PATH,
    SERVICE_EXPORT_ZIP,
    SERVICE_IMPORT_JSON,
    SERVICE_KEEPSAKE,
    SIGNAL_CHANGED,
    parse_people,
)
from .store import FirstWordsError, StoreConfig, WordStore

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]
FRONTEND_DIR = Path(__file__).parent / "frontend"
PANEL_FILE = FRONTEND_DIR / "first-words-panel.js"

# aiohttp routes can't be removed, so static paths and views are registered
# once per HA process, not once per config entry.
_ROUTES_REGISTERED = False


@dataclass
class FirstWordsRuntime:
    store: WordStore
    child: str
    birthday: str
    people: list[dict[str, str]]
    storage_name: str = DEFAULT_STORAGE_NAME
    offsite: str = ""


def get_runtime(hass: HomeAssistant) -> FirstWordsRuntime | None:
    return hass.data.get(DOMAIN)


def _settings(entry: ConfigEntry) -> dict:
    return {**entry.data, **entry.options}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    global _ROUTES_REGISTERED
    s = _settings(entry)
    child = s.get(CONF_CHILD) or "Baby"
    birthday = s.get(CONF_BIRTHDAY) or ""
    store = WordStore(
        StoreConfig(
            mount_path=s.get(CONF_MOUNT) or DEFAULT_MOUNT,
            folder=s.get(CONF_FOLDER, DEFAULT_FOLDER),
            child=child,
            birthday=birthday,
        ),
        today=lambda: dt_util.now().date(),
    )
    hass.data[DOMAIN] = FirstWordsRuntime(
        store, child, birthday, parse_people(s.get(CONF_PEOPLE, "")),
        storage_name=s.get(CONF_STORAGE_NAME) or DEFAULT_STORAGE_NAME,
        offsite=s.get(CONF_OFFSITE) or "",
    )

    status = await hass.async_add_executor_job(store.status)
    if not status["mounted"]:
        # Not fatal: the panel still loads and explains, and every write refuses.
        _LOGGER.warning("First Words storage is not mounted at %s; saving is disabled until it is", status["path"])

    if not _ROUTES_REGISTERED:
        async_register_views(hass)
        await hass.http.async_register_static_paths([StaticPathConfig(PANEL_JS_URL, str(PANEL_FILE), False)])
        _ROUTES_REGISTERED = True

    # Cache-bust with the file's mtime so a HACS update can't be served stale.
    stamp = await hass.async_add_executor_job(lambda: int(PANEL_FILE.stat().st_mtime))
    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        frontend_url_path=PANEL_URL_PATH,
        config={"_panel_custom": {"name": PANEL_ELEMENT, "js_url": f"{PANEL_JS_URL}?v={stamp}"}},
        require_admin=False,
        update=True,
    )

    _register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data.pop(DOMAIN, None)
        async_remove_panel(hass, PANEL_URL_PATH)
        for svc in (SERVICE_EXPORT_ZIP, SERVICE_KEEPSAKE, SERVICE_IMPORT_JSON):
            hass.services.async_remove(DOMAIN, svc)
    return ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_EXPORT_ZIP):
        return

    def _store() -> WordStore:
        rt = get_runtime(hass)
        if rt is None:
            raise HomeAssistantError("First Words is not set up.")
        return rt.store

    async def export_zip(call: ServiceCall) -> ServiceResponse:
        try:
            name = await hass.async_add_executor_job(_store().export_zip)
        except FirstWordsError as err:
            raise HomeAssistantError(str(err)) from err
        return {"file": f"{_store().root}/exports/{name}"}

    async def keepsake(call: ServiceCall) -> ServiceResponse:
        try:
            name = await hass.async_add_executor_job(_store().keepsake)
        except FirstWordsError as err:
            raise HomeAssistantError(str(err)) from err
        return {"file": f"{_store().root}/exports/{name}"}

    async def import_json(call: ServiceCall) -> ServiceResponse:
        try:
            counts = await hass.async_add_executor_job(
                _store().import_json, call.data["source"], call.data.get("clips", ""))
        except FirstWordsError as err:
            raise HomeAssistantError(str(err)) from err
        except (OSError, ValueError) as err:
            raise HomeAssistantError(f"Import failed: {err}") from err
        async_dispatcher_send(hass, SIGNAL_CHANGED)
        return counts

    hass.services.async_register(DOMAIN, SERVICE_EXPORT_ZIP, export_zip, supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, SERVICE_KEEPSAKE, keepsake, supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(
        DOMAIN, SERVICE_IMPORT_JSON, import_json,
        schema=vol.Schema({vol.Required("source"): cv.string, vol.Optional("clips", default=""): cv.string}),
        supports_response=SupportsResponse.OPTIONAL,
    )
