"""HTTP API for the panel. Every view requires a signed-in HA user."""
from __future__ import annotations

import json
import logging
import mimetypes
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import API_BASE, EVENT_ADDED, EVENT_DELETED, EVENT_UPDATED, SIGNAL_CHANGED
from .store import MAX_AUDIO_BYTES, MAX_CHUNK_BYTES, Conflict, FirstWordsError, StorageUnavailable

if TYPE_CHECKING:
    from . import FirstWordsRuntime

_LOGGER = logging.getLogger(__name__)


def _rt(request: web.Request) -> "FirstWordsRuntime":
    from . import get_runtime

    rt = get_runtime(request.app["hass"])
    if rt is None:
        raise StorageUnavailable("First Words isn't set up in Home Assistant.")
    return rt


def _err(err: Exception) -> web.Response:
    if isinstance(err, FirstWordsError):
        body: dict[str, Any] = {"error": str(err)}
        if isinstance(err, Conflict):
            body["received"] = err.received
        if isinstance(err, StorageUnavailable):
            body["storage"] = "unavailable"
        return web.json_response(body, status=err.status)
    _LOGGER.exception("First Words request failed")
    return web.json_response({"error": "Something went wrong on Home Assistant. Try again."}, status=500)


def _user_name(request: web.Request) -> str:
    user = request.get("hass_user")
    return (user.name if user and user.name else "") or "Someone"


def _changed(hass: HomeAssistant, event: str, word: dict[str, Any], request: web.Request) -> None:
    user = request.get("hass_user")
    hass.bus.async_fire(event, {
        "id": word.get("id"), "word": word.get("word"), "date": word.get("date"),
        "heard_by": word.get("heardBy"), "added_by": word.get("addedBy"),
        "user_id": user.id if user else None,
    })
    async_dispatcher_send(hass, SIGNAL_CHANGED)


class _TooBig(Exception):
    pass


async def _read_multipart(request: web.Request) -> tuple[dict[str, Any], bytes | None, str]:
    """Read `meta` (JSON) and an optional `audio` file, streaming with our own size cap."""
    meta: dict[str, Any] = {}
    audio: bytes | None = None
    ext = "wav"
    reader = await request.multipart()
    async for part in reader:
        if part.name == "meta":
            meta = json.loads(await part.text())
        elif part.name == "audio":
            if part.filename and "." in part.filename:
                ext = part.filename.rsplit(".", 1)[-1].lower()
            buf = bytearray()
            while chunk := await part.read_chunk(65536):
                buf.extend(chunk)
                if len(buf) > MAX_AUDIO_BYTES:
                    raise _TooBig
            audio = bytes(buf) if buf else None
    if not isinstance(meta, dict):
        raise ValueError("meta must be an object")
    return meta, audio, ext


class _View(HomeAssistantView):
    requires_auth = True


class WordsView(_View):
    url = f"{API_BASE}/words"
    name = "api:first_words:words"

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        try:
            rt = _rt(request)
            status = await hass.async_add_executor_job(rt.store.status)
            words = await hass.async_add_executor_job(rt.store.list_words) if status["mounted"] else []
        except Exception as err:  # noqa: BLE001
            return _err(err)
        return self.json({
            "words": words,
            "config": {"child": rt.child, "birthday": rt.birthday, "people": rt.people,
                       "storageName": rt.storage_name, "offsite": rt.offsite},
            "storage": status,
            "user": _user_name(request),
        })

    async def post(self, request: web.Request) -> web.Response:
        """multipart/form-data: `meta` (JSON) and an optional `audio` file."""
        hass = request.app["hass"]
        try:
            rt = _rt(request)
            meta, audio, ext = await _read_multipart(request)
            word, created = await hass.async_add_executor_job(
                rt.store.create, meta, _user_name(request), audio, ext)
        except _TooBig:
            return web.json_response({"error": "That clip is too long. Keep it under a minute."}, status=413)
        except (ValueError, json.JSONDecodeError):
            return web.json_response({"error": "Bad request."}, status=400)
        except Exception as err:  # noqa: BLE001
            return _err(err)
        if created:
            _changed(hass, EVENT_ADDED, word, request)
        return self.json(word, status_code=HTTPStatus.CREATED if created else HTTPStatus.OK)


class WordView(_View):
    url = API_BASE + "/words/{word_id}"
    name = "api:first_words:word"

    async def patch(self, request: web.Request, word_id: str) -> web.Response:
        hass = request.app["hass"]
        try:
            fields = await request.json()
            if not isinstance(fields, dict):
                raise ValueError
            word = await hass.async_add_executor_job(_rt(request).store.update, word_id, fields)
        except ValueError:
            return web.json_response({"error": "Bad request."}, status=400)
        except Exception as err:  # noqa: BLE001
            return _err(err)
        _changed(hass, EVENT_UPDATED, word, request)
        return self.json(word)

    async def delete(self, request: web.Request, word_id: str) -> web.Response:
        hass = request.app["hass"]
        try:
            store = _rt(request).store
            word = await hass.async_add_executor_job(store.get_word, word_id)
            trash = await hass.async_add_executor_job(store.delete, word_id)
        except Exception as err:  # noqa: BLE001
            return _err(err)
        _changed(hass, EVENT_DELETED, word, request)
        return self.json({"ok": True, "trash": trash})


class _FileView(_View):
    kind = "audio"

    async def get(self, request: web.Request, word_id: str) -> web.StreamResponse:
        hass = request.app["hass"]
        try:
            path = await hass.async_add_executor_job(_rt(request).store.file_path, word_id, self.kind)
        except Exception as err:  # noqa: BLE001
            return _err(err)
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix.lower() == ".m4a":
            ctype = "audio/mp4"
        return web.FileResponse(path, headers={"Content-Type": ctype, "Cache-Control": "private, no-cache"})


class AudioView(_FileView):
    url = API_BASE + "/audio/{word_id}"
    name = "api:first_words:audio"
    kind = "audio"

    async def post(self, request: web.Request, word_id: str) -> web.Response:
        """Attach a clip to an existing word. multipart: `meta` (clipStart/clipEnd) + `audio`."""
        hass = request.app["hass"]
        try:
            meta, audio, ext = await _read_multipart(request)
            if audio is None:
                return web.json_response({"error": "There's no recording to save."}, status=400)
            word = await hass.async_add_executor_job(
                _rt(request).store.attach_audio, word_id, audio, ext, meta.get("clipStart"), meta.get("clipEnd"))
        except _TooBig:
            return web.json_response({"error": "That clip is too long. Keep it under a minute."}, status=413)
        except (ValueError, AttributeError):
            return web.json_response({"error": "Bad request."}, status=400)
        except Exception as err:  # noqa: BLE001
            return _err(err)
        _changed(hass, EVENT_UPDATED, word, request)
        return self.json(word)


class VideoView(_FileView):
    url = API_BASE + "/video/{word_id}"
    name = "api:first_words:video"
    kind = "video"


class VideoStartView(_View):
    url = API_BASE + "/video/{word_id}/start"
    name = "api:first_words:video_start"

    async def post(self, request: web.Request, word_id: str) -> web.Response:
        hass = request.app["hass"]
        try:
            body = await request.json()
            token = await hass.async_add_executor_job(
                _rt(request).store.video_start, word_id, body.get("name", ""), body.get("mime", ""), body.get("size"))
        except (ValueError, AttributeError):
            return web.json_response({"error": "Bad request."}, status=400)
        except Exception as err:  # noqa: BLE001
            return _err(err)
        return self.json({"token": token, "chunk": 4 * 1024 * 1024})


class UploadView(_View):
    """PUT one raw chunk at ?offset=N; GET says how much has arrived (to resume)."""

    url = API_BASE + "/upload/{token}"
    name = "api:first_words:upload"

    async def get(self, request: web.Request, token: str) -> web.Response:
        hass = request.app["hass"]
        try:
            received = await hass.async_add_executor_job(_rt(request).store.video_received, token)
        except Exception as err:  # noqa: BLE001
            return _err(err)
        return self.json({"received": received})

    async def put(self, request: web.Request, token: str) -> web.Response:
        hass = request.app["hass"]
        try:
            offset = int(request.query.get("offset", "-1"))
            if request.content_length and request.content_length > MAX_CHUNK_BYTES:
                return web.json_response({"error": "Chunk too large."}, status=413)
            chunk = await request.read()
            received = await hass.async_add_executor_job(_rt(request).store.video_chunk, token, offset, chunk)
        except ValueError:
            return web.json_response({"error": "Bad offset."}, status=400)
        except Exception as err:  # noqa: BLE001
            return _err(err)
        return self.json({"received": received})


class UploadFinishView(_View):
    url = API_BASE + "/upload/{token}/finish"
    name = "api:first_words:upload_finish"

    async def post(self, request: web.Request, token: str) -> web.Response:
        hass = request.app["hass"]
        try:
            word = await hass.async_add_executor_job(_rt(request).store.video_finish, token)
        except Exception as err:  # noqa: BLE001
            return _err(err)
        _changed(hass, EVENT_UPDATED, word, request)
        return self.json({"word": word})


class ExportView(_View):
    """POST /export or /keepsake makes the file on the share; GET /exports/<name> serves it."""

    url = API_BASE + "/make/{kind}"
    name = "api:first_words:make"

    async def post(self, request: web.Request, kind: str) -> web.Response:
        hass = request.app["hass"]
        try:
            store = _rt(request).store
            if kind == "export":
                name = await hass.async_add_executor_job(store.export_zip)
            elif kind == "keepsake":
                name = await hass.async_add_executor_job(store.keepsake)
            else:
                return web.json_response({"error": "Unknown."}, status=404)
        except Exception as err:  # noqa: BLE001
            return _err(err)
        return self.json({"name": name, "path": f"{store.root}/exports/{name}",
                          "url": f"{API_BASE}/exports/{name}"})


class ExportFileView(_View):
    url = API_BASE + "/exports/{name}"
    name = "api:first_words:export_file"

    async def get(self, request: web.Request, name: str) -> web.StreamResponse:
        hass = request.app["hass"]
        try:
            path = await hass.async_add_executor_job(_rt(request).store.export_file, name)
        except Exception as err:  # noqa: BLE001
            return _err(err)
        headers = {"Cache-Control": "private, no-cache"}
        if path.suffix == ".zip":
            headers["Content-Disposition"] = f'attachment; filename="{path.name}"'
        else:
            headers["Content-Type"] = "text/html; charset=utf-8"
        return web.FileResponse(path, headers=headers)


def async_register_views(hass: HomeAssistant) -> None:
    for view in (WordsView, WordView, AudioView, VideoView, VideoStartView, UploadView,
                 UploadFinishView, ExportView, ExportFileView):
        hass.http.register_view(view())
