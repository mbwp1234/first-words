"""Config flow: who the child is, who the parents are, and where files go."""
from __future__ import annotations

import os
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

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
    DEFAULT_PEOPLE,
    DEFAULT_STORAGE_NAME,
    DOMAIN,
    parse_people,
)


def _schema(d: dict[str, Any]) -> vol.Schema:
    bday = d.get(CONF_BIRTHDAY)
    return vol.Schema({
        vol.Required(CONF_CHILD, default=d.get(CONF_CHILD, "")): str,
        vol.Optional(CONF_BIRTHDAY, **({"default": bday} if bday else {})): selector.DateSelector(),
        vol.Required(CONF_PEOPLE, default=d.get(CONF_PEOPLE, DEFAULT_PEOPLE)):
            selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
        vol.Required(CONF_MOUNT, default=d.get(CONF_MOUNT, DEFAULT_MOUNT)): str,
        vol.Optional(CONF_FOLDER, default=d.get(CONF_FOLDER, DEFAULT_FOLDER)): str,
        vol.Optional(CONF_STORAGE_NAME, default=d.get(CONF_STORAGE_NAME, DEFAULT_STORAGE_NAME)): str,
        vol.Optional(CONF_OFFSITE, default=d.get(CONF_OFFSITE, "")): str,
    })


def _validate(data: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    mount = str(data.get(CONF_MOUNT, "")).rstrip("/")
    if not (mount.startswith("/media/") or mount.startswith("/share/")) or ".." in mount:
        errors[CONF_MOUNT] = "bad_mount"
    elif not os.path.ismount(mount):
        errors[CONF_MOUNT] = "not_mounted"
    if "/" in str(data.get(CONF_FOLDER, "")) or ".." in str(data.get(CONF_FOLDER, "")):
        errors[CONF_FOLDER] = "bad_folder"
    if not parse_people(data.get(CONF_PEOPLE, "")):
        errors[CONF_PEOPLE] = "no_people"
    return errors


class FirstWordsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_MOUNT] = user_input[CONF_MOUNT].rstrip("/")
            errors = await self.hass.async_add_executor_job(_validate, user_input)
            if not errors:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"{user_input[CONF_CHILD]}'s First Words", data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema(user_input or {}), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(entry: config_entries.ConfigEntry):
        return FirstWordsOptionsFlow()


class FirstWordsOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            user_input[CONF_MOUNT] = user_input[CONF_MOUNT].rstrip("/")
            errors = await self.hass.async_add_executor_job(_validate, user_input)
            if not errors:
                return self.async_create_entry(data=user_input)
        return self.async_show_form(step_id="init", data_schema=_schema(user_input or current), errors=errors)
