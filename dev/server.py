"""Dev server: the REAL api.py + store.py behind tiny Home Assistant stubs.

    python dev/server.py [--port 8765] [--data /tmp/fw-dev] [--unmounted]

Serves the panel harness at / and the API at /api/first_words/*. Used by
dev/ui_test.py; also handy for clicking around in a desktop browser.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import sys
import types
from pathlib import Path

from aiohttp import web

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "custom_components" / "first_words"


def _stub_homeassistant() -> None:
    ha = types.ModuleType("homeassistant")
    comps = types.ModuleType("homeassistant.components")
    http = types.ModuleType("homeassistant.components.http")
    core = types.ModuleType("homeassistant.core")
    helpers = types.ModuleType("homeassistant.helpers")
    disp = types.ModuleType("homeassistant.helpers.dispatcher")

    class HomeAssistantView:
        requires_auth = True

        def json(self, result, status_code=200, headers=None):
            return web.json_response(result, status=int(status_code), headers=headers)

    http.HomeAssistantView = HomeAssistantView
    core.HomeAssistant = object
    disp.async_dispatcher_send = lambda hass, *a: hass.signals.append(a)
    for name, mod in {"homeassistant": ha, "homeassistant.components": comps,
                      "homeassistant.components.http": http, "homeassistant.core": core,
                      "homeassistant.helpers": helpers, "homeassistant.helpers.dispatcher": disp}.items():
        sys.modules[name] = mod


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"first_words.{name}", PKG / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeHass:
    def __init__(self) -> None:
        self.events: list = []
        self.signals: list = []
        self.bus = types.SimpleNamespace(async_fire=lambda ev, data: self.events.append((ev, data)))

    async def async_add_executor_job(self, fn, *args):
        return await asyncio.get_running_loop().run_in_executor(None, fn, *args)


def build_app(data_dir: str, mounted: bool = True, user: str = "Alex") -> web.Application:
    _stub_homeassistant()
    pkg = types.ModuleType("first_words")
    pkg.__path__ = [str(PKG)]
    sys.modules["first_words"] = pkg
    _load("const")
    store_mod = _load("store")
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    mount = data_dir if mounted else str(Path(data_dir) / "not-mounted")
    store = store_mod.WordStore(store_mod.StoreConfig(
        mount_path=mount, folder="First Words", child="Robin", birthday="2025-09-01", require_mount=False))
    rt = types.SimpleNamespace(store=store, child="Robin", birthday="2025-09-01",
                               storage_name="Test NAS", offsite="copied offsite every night",
                               people=[{"name": "Alex", "label": "Mama"}, {"name": "Sam", "label": "Dada"}])
    pkg.get_runtime = lambda hass: rt
    if not os.environ.get("FW_FFMPEG"):
        try:
            import imageio_ffmpeg
            os.environ["FW_FFMPEG"] = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            pass
    _load("video")
    api = _load("api")

    hass = FakeHass()
    state = {"user": user, "fail": 0}

    @web.middleware
    async def auth(request, handler):
        if request.path.startswith("/api/") and state["fail"]:
            state["fail"] -= 1
            raise web.HTTPServiceUnavailable(text="simulated outage")
        request["hass_user"] = types.SimpleNamespace(name=state["user"], id="u1")
        return await handler(request)

    app = web.Application(middlewares=[auth], client_max_size=16 * 1024 * 1024)
    app["hass"] = hass
    for view_cls in (api.WordsView, api.WordView, api.AudioView, api.VideoView, api.VideoTrimView, api.VideoStartView,
                     api.UploadView, api.UploadFinishView, api.ExportView, api.ExportFileView):
        view = view_cls()
        for method in ("get", "post", "patch", "put", "delete"):
            if hasattr(view, method):
                # HA's view wrapper passes URL parameters as keyword arguments.
                h = getattr(view, method)
                app.router.add_route(method.upper(), view.url,
                                     lambda req, h=h: h(req, **req.match_info))

    async def dev_state(request):
        body = await request.json() if request.can_read_body else {}
        state.update({k: v for k, v in body.items() if k in ("user", "fail")})
        return web.json_response({"events": [e[0] for e in hass.events], "signals": len(hass.signals),
                                  "root": str(store.root), **state})

    app.router.add_route("*", "/dev/state", dev_state)
    app.router.add_get("/", lambda r: web.FileResponse(Path(__file__).parent / "harness.html"))
    app.router.add_get("/first_words_panel", lambda r: web.FileResponse(PKG / "frontend" / "first-words-panel.js"))
    return app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--data", default="/tmp/fw-dev")
    ap.add_argument("--unmounted", action="store_true")
    a = ap.parse_args()
    web.run_app(build_app(a.data, mounted=not a.unmounted), host="127.0.0.1", port=a.port)
