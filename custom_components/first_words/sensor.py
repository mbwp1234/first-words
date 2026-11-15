"""sensor.<child>_words: how many words, plus the newest one."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_CHANGED
from .store import FirstWordsError

SCAN_INTERVAL = timedelta(minutes=5)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    add([WordsSensor(hass, entry)], True)


class WordsSensor(SensorEntity):
    _attr_icon = "mdi:account-voice"
    _attr_native_unit_of_measurement = "words"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_should_poll = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        rt = hass.data[DOMAIN]
        self._rt = rt
        self._attr_name = f"{rt.child} words"
        self._attr_unique_id = f"{entry.entry_id}_words"
        self._attrs: dict[str, Any] = {}

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_CHANGED, self._on_changed))

    @callback
    def _on_changed(self) -> None:
        # Must be a @callback: a plain function is run in the executor, and
        # scheduling a state update from there is refused by HA.
        self.async_schedule_update_ha_state(True)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._attrs

    async def async_update(self) -> None:
        store = self._rt.store
        try:
            words = await self.hass.async_add_executor_job(store.list_words)
        except FirstWordsError as err:
            # A missing reading is not zero words: go unavailable, say why.
            self._attr_available = False
            self._attrs = {"storage": "unavailable", "reason": str(err), "path": str(store.root)}
            return
        self._attr_available = True
        self._attr_native_value = len(words)
        newest = words[0] if words else {}
        first = words[-1] if words else {}
        self._attrs = {
            "storage": "mounted", "path": str(store.root),
            "newest_word": newest.get("word"), "newest_date": newest.get("date"),
            "heard_by": newest.get("heardBy"), "added_by": newest.get("addedBy"),
            "first_word": first.get("word"), "first_date": first.get("date"),
            "with_audio": sum(1 for w in words if w.get("audioFile")),
            "with_video": sum(1 for w in words if w.get("videoFile")),
        }
