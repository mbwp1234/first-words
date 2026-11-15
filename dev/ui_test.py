"""Drive the panel in headless Chromium at 390x844 against dev/server.py.

    python dev/ui_test.py            (starts its own server on a temp dir)

Adapted from the Apps Script harness (t.py): list, play, video upload, overview
drag, end-handle drag, preview, save, edit, delete, keepsake/zip, plus the new
offline queue and the not-mounted banner. Exits non-zero on any failed check.
"""
from __future__ import annotations

import io
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import wave
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)
FAILS: list[str] = []


def check(label: str, cond) -> None:
    if callable(cond):  # never trust an argument that might be an uncalled function
        cond = cond()
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        FAILS.append(label)


def tone_wav(seconds=1.0, sr=8000, freq=440) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * i / sr)))
                               for i in range(int(seconds * sr))))
    return buf.getvalue()


def make_video(path: Path) -> None:
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    # Lossless noise on purpose: ~9 MB that won't compress, so the upload needs several 4 MB chunks.
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "nullsrc=s=160x120:r=15,geq=random(1)*255:128:128",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=20", "-t", "20", "-c:v", "libx264",
                    "-qp", "0", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)
    assert path.stat().st_size > 8 * 1024 * 1024, f"test video only {path.stat().st_size} bytes"


def start_server(data: str, port: int, mounted=True):
    sys.path.insert(0, str(HERE))
    import asyncio
    from aiohttp import web
    import server as dev

    app = dev.build_app(data, mounted=mounted)
    loop = asyncio.new_event_loop()
    runner = web.AppRunner(app)

    def run():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(runner.setup())
        loop.run_until_complete(web.TCPSite(runner, "127.0.0.1", port).start())
        loop.run_forever()

    threading.Thread(target=run, daemon=True).start()
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/dev/state")
            return
        except Exception:
            time.sleep(0.1)
    raise SystemExit("dev server did not start")


def post_word(base: str, meta: dict, audio: bytes | None) -> dict:
    boundary = "----fw"
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="meta"\r\n\r\n{json.dumps(meta)}\r\n'.encode()]
    if audio:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="clip.wav"\r\n'
                     f"Content-Type: audio/wav\r\n\r\n".encode() + audio + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(base + "/api/first_words/words", data=b"".join(parts), method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    return json.loads(urllib.request.urlopen(req).read())


def dev_state(base: str, **kw) -> dict:
    req = urllib.request.Request(base + "/dev/state", data=json.dumps(kw).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="fw-ui-"))
    port = 8790
    base = f"http://127.0.0.1:{port}"
    start_server(str(tmp), port)
    root = tmp / "First Words"
    video = tmp / "clip.mp4"
    make_video(video)
    memo = tmp / "memo.wav"
    memo.write_bytes(tone_wav(4.0, 16000, 300))

    a1 = post_word(base, {"id": "a1", "word": "mama", "sounded": "mamama", "date": "2026-09-02",
                          "heardBy": "Mama", "notes": "Bath time", "clipStart": 0, "clipEnd": 1}, tone_wav())
    post_word(base, {"id": "a2", "word": "dada", "date": "2026-09-18", "heardBy": "Dada"}, None)

    errs: list[str] = []
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        pg = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, has_touch=True)
        pg.on("console", lambda m: m.type == "error" and "status of 503" not in m.text and errs.append(m.text))
        pg.on("pageerror", lambda e: errs.append("PAGEERROR " + str(e)))
        pg.goto(base + "/")
        pg.wait_for_function("() => { const e = document.querySelector('first-words-panel'); "
                             "return e && e.shadowRoot && /words? so far/.test(e.shadowRoot.getElementById('list-sub').textContent); }",
                             timeout=10000)
        print("list")
        check("list sub shows 2 words", "2 words so far" in pg.inner_text("#list-sub"))
        check("title is the child's name", pg.inner_text("#list-title") == "Robin")
        check("CTA uses the child's name", pg.inner_text("#cta-label") == "Robin said something new")
        check("first-word badge on the oldest", pg.locator(".chip.first").count() == 1)
        bottom = pg.locator("#v-list .bottombar").bounding_box()
        check("bottom bar pinned to the viewport bottom", abs(bottom["y"] + bottom["height"] - 844) < 2)
        pg.screenshot(path=str(OUT / "s1_list.png"))

        pg.click('[data-play="a1"]'); pg.wait_for_timeout(500)
        check("list play turns into pause", pg.get_attribute('[data-play="a1"]', "aria-label") == "Pause")
        pg.click('[data-play="a1"]')

        print("add from video")
        pg.click('#v-list [data-go="add"]'); pg.wait_for_timeout(200)
        check("who-heard defaults to the signed-in parent (Alex -> Mama)",
              pg.get_attribute('[data-heard="Mama"]', "aria-pressed") == "true")
        pg.set_input_files("#file-in", str(video))
        pg.wait_for_selector("#c-trim:not([hidden])", timeout=20000); pg.wait_for_timeout(500)
        check("overview strip visible for a 20 s video", not pg.eval_on_selector("#ov", "e=>e.hidden"))
        before = pg.inner_text("#sel-len")
        ov = pg.locator("#ov").bounding_box()
        pg.mouse.move(ov["x"] + 20, ov["y"] + 18); pg.mouse.down()
        pg.mouse.move(ov["x"] + 150, ov["y"] + 18, steps=8); pg.mouse.up(); pg.wait_for_timeout(400)
        after = pg.inner_text("#sel-len")
        vt = float(pg.eval_on_selector("#vid", "v=>v.currentTime"))
        check(f"overview drag moves the selection ({before} -> {after})", before != after)
        check(f"video scrubs with it (t={vt:.2f})", vt > 1)
        he = pg.locator("#h-end").bounding_box()
        pg.mouse.move(he["x"] + 22, he["y"] + 40); pg.mouse.down()
        pg.mouse.move(he["x"] + 80, he["y"] + 40, steps=6); pg.mouse.up(); pg.wait_for_timeout(300)
        check("end-handle drag lengthens the clip", pg.inner_text("#sel-len") != after)
        pg.click("#sel-play"); pg.wait_for_timeout(700)
        check("preview shows the playhead", pg.eval_on_selector("#ph", "e=>!e.hidden"))
        pg.click("#sel-play")
        pg.fill("#f-word", "ball"); pg.fill("#f-sounded", "baw"); pg.fill("#f-notes", "Pointing at the ball under the couch")
        check("keep-video label shows the size", "MB" in pg.inner_text("#keep-label"))
        pg.screenshot(path=str(OUT / "s2_trim.png"), full_page=True)
        pg.click("#save")
        pg.wait_for_selector("#v-detail:not([hidden])", timeout=15000)
        pg.wait_for_function("() => document.querySelector('first-words-panel').shadowRoot.getElementById('upbar').hidden",
                             timeout=30000)
        words = {w["word"]: w for w in json.loads((root / "first-words.json").read_text())["words"]}
        ball = words.get("ball", {})
        today = time.strftime("%Y-%m-%d")
        check("clip saved as a WAV named <date>_ball.wav", ball.get("audioFile") == f"audio/{today}_ball.wav")
        wav = (root / ball.get("audioFile", "x")).read_bytes() if ball.get("audioFile") else b""
        check("clip is a real RIFF/WAVE file", wav[:4] == b"RIFF" and wav[8:12] == b"WAVE")
        check("added_by comes from the HA user", ball.get("addedBy") == "Alex")
        check("full video uploaded and attached", ball.get("videoFile", "").endswith("_ball.mp4"))
        check(f"video needed 3+ chunks ({video.stat().st_size} bytes)", video.stat().st_size > 8 * 1024 * 1024)
        if ball.get("videoFile"):
            check("uploaded video is byte-identical",
                  (root / ball["videoFile"]).read_bytes() == video.read_bytes())
        check("no partial uploads left", not any((root / "video/.partial").glob("*.part")))
        check("video link visible", pg.eval_on_selector("#d-video-link", "e=>!e.hidden"))
        check("detail shows position", pg.inner_text("#d-pos") == "Word 3 of 3")
        check("detail age line", "months" in pg.inner_text("#d-age"))
        check("event fired", "first_words_added" in dev_state(base)["events"])
        pg.click("#d-play"); pg.wait_for_timeout(400)
        pg.screenshot(path=str(OUT / "s3_detail.png"), full_page=True)
        pg.click("#d-video-link"); pg.wait_for_timeout(800)
        check("video plays inline via a signed URL",
              pg.eval_on_selector("#d-video", "v=>!v.hidden && /authSig=/.test(v.src) && v.readyState>=1"))

        print("edit / delete")
        pg.click("#d-edit"); pg.fill("#e-word", "big ball"); pg.click("#e-save"); pg.wait_for_timeout(500)
        check("edited word shows", pg.inner_text("#d-word") == "big ball")
        check("clip renamed on disk", (root / f"audio/{today}_big-ball.wav").exists()
              and not (root / f"audio/{today}_ball.wav").exists())
        check("video renamed on disk", (root / f"video/{today}_big-ball.mp4").exists())

        print("re-cut, trim, replace, remove (a saved word's recording and video)")
        import re as _re
        import imageio_ffmpeg
        def word_named(name):
            return next(w for w in json.loads((root / "first-words.json").read_text())["words"] if w["word"] == name)
        def dur_of(path):
            import imageio_ffmpeg
            out = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
            h, m, sec = _re.search(r"Duration: (\d+):(\d+):([\d.]+)", out).groups()
            return int(h) * 3600 + int(m) * 60 + float(sec)
        before = word_named("big ball")
        pg.click("#d-edit"); pg.wait_for_timeout(150)
        check("edit dialog offers re-cut from its video", pg.is_visible("#e-recut") and "from its video" in pg.inner_text("#e-recut"))
        check("edit dialog offers trim and remove for a word with video", pg.is_visible("#e-vtrim") and pg.is_visible("#e-vremove"))
        pg.click("#e-recut")
        try:
            pg.wait_for_selector("#c-trim:not([hidden])", timeout=20000)
        except Exception:
            print("    DEBUG view:", pg.evaluate("() => document.querySelector('first-words-panel')._app._debug.S.view"),
                  "mode:", pg.evaluate("() => document.querySelector('first-words-panel')._app._debug.A.mode"),
                  "kind:", pg.evaluate("() => document.querySelector('first-words-panel')._app._debug.A.kind"),
                  "toast:", pg.inner_text("#toast"), "errs:", errs[-3:])
            raise
        pg.wait_for_timeout(400)
        st = pg.evaluate("() => { const c = document.querySelector('first-words-panel')._app._debug.A.clip; return [c.start, c.end, c.isVideo]; }")
        check(f"re-cut opens the saved video at the saved selection ({st} vs {before['clipStart']}-{before['clipEnd']})",
              st[2] and abs(st[0] - before["clipStart"]) < 0.05 and abs(st[1] - before["clipEnd"]) < 0.05)
        check("re-cut hides the word form and the keep-video toggle",
              pg.eval_on_selector("#f-word", "e=>e.offsetParent===null") and pg.eval_on_selector("#keep-wrap", "e=>e.hidden"))
        he = pg.locator("#h-end").bounding_box()
        pg.mouse.move(he["x"] + 22, he["y"] + 40); pg.mouse.down(); pg.mouse.move(he["x"] - 40, he["y"] + 40, steps=6); pg.mouse.up()
        pg.wait_for_timeout(200)
        pg.click("#save"); pg.wait_for_selector("#v-detail:not([hidden])", timeout=15000); pg.wait_for_timeout(300)
        after = word_named("big ball")
        check(f"re-cut saved a shorter clip ({before['clipEnd']} -> {after['clipEnd']})", after["clipEnd"] < before["clipEnd"] - 0.2)
        check("old clip moved to .trash", any(p.name.endswith("_big-ball.wav") for p in (root / ".trash").rglob("*.wav")))
        check("the video is untouched by a re-cut", after["videoFile"] == before["videoFile"] and (root / after["videoFile"]).read_bytes() == video.read_bytes())

        pg.click("#d-edit"); pg.click("#e-vtrim")
        pg.wait_for_selector("#c-trim:not([hidden])", timeout=20000); pg.wait_for_timeout(400)
        sel = pg.evaluate("() => { const c = document.querySelector('first-words-panel')._app._debug.A.clip; return [c.start, c.end]; }")
        check(f"trim starts from the clip padded by 2 s ({sel})", abs(sel[0] - max(0, after["clipStart"] - 2)) < 0.05)
        pg.click("#save")
        pg.wait_for_selector("#v-detail:not([hidden])", timeout=120000); pg.wait_for_timeout(300)
        tw = word_named("big ball")
        tf = root / tw.get("videoTrimFile", "missing")
        check("trimmed copy saved as .mp4 next to the original", tw.get("videoTrimFile", "").endswith("_big-ball_trim.mp4") and tf.exists())
        check("original kept, byte-identical", (root / tw["videoFile"]).read_bytes() == video.read_bytes())
        if tf.exists():
            d = dur_of(tf)
            check(f"trimmed copy is the chosen length ({d:.2f}s vs {sel[1] - sel[0]:.2f}s)", abs(d - (sel[1] - sel[0])) < 0.3)
            ff_out = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(tf)], capture_output=True, text=True).stderr
            check("trimmed copy is H.264 + AAC (plays in every browser)", "h264" in ff_out and "aac" in ff_out)
        check("detail now says Watch the moment", pg.inner_text("#d-video-link b") == "Watch the moment")
        check("and offers the full video", pg.is_visible("#d-video-full"))
        pg.click("#d-video-link"); pg.wait_for_timeout(800)
        check("Watch the moment plays the trimmed copy", pg.eval_on_selector("#d-video", "v=>/v=trim/.test(v.src) && v.readyState>=1"))
        pg.click("#d-video-full"); pg.wait_for_timeout(800)
        check("Watch the full video plays the original", pg.eval_on_selector("#d-video", "v=>!/v=trim/.test(v.src) && v.readyState>=1"))
        pg.screenshot(path=str(OUT / "s15_trimmed_detail.png"), full_page=True)

        pg.click("#d-edit"); pg.click("#e-replace"); pg.wait_for_timeout(200)
        check("replace screen is titled for the word", pg.inner_text("#add-title") == "Replace “big ball”")
        pg.set_input_files("#file-in", str(memo))
        pg.wait_for_selector("#c-trim:not([hidden])", timeout=10000)
        pg.click("#save"); pg.wait_for_selector("#v-detail:not([hidden])", timeout=15000); pg.wait_for_timeout(300)
        rw = word_named("big ball")
        check(f"replace swapped the clip for the 4 s memo (clip {rw['clipStart']}-{rw['clipEnd']})",
              rw["clipStart"] == 0 and rw["clipEnd"] > 3.5 and rw.get("capturedAt") != tw.get("capturedAt"))
        check("replace kept the video and its trim", rw["videoFile"] == tw["videoFile"] and rw.get("videoTrimFile") == tw["videoTrimFile"])

        pg.click("#d-edit"); pg.click("#e-vremove")
        check("remove asks for a second tap", "Tap again" in pg.inner_text("#e-vremove"))
        pg.click("#e-vremove"); pg.wait_for_timeout(500)
        gw = word_named("big ball")
        check("video removed from the word", gw["videoFile"] == "" and "videoTrimFile" not in gw)
        check("both video files are in .trash", any(p.name.endswith("_big-ball.mp4") for p in (root / ".trash").rglob("*.mp4"))
              and any(p.name.endswith("_big-ball_trim.mp4") for p in (root / ".trash").rglob("*.mp4")))
        check("the clip survives removing the video", (root / gw["audioFile"]).exists())
        check("detail no longer offers the video", pg.eval_on_selector("#d-video-link", "e=>e.hidden"))
        pg.click("#v-detail [data-go='list']"); pg.wait_for_timeout(200)
        pg.screenshot(path=str(OUT / "s4_list.png"), full_page=True)
        pg.click("[data-open='a2']"); pg.wait_for_timeout(200)
        pg.click("#d-edit"); pg.click("#e-delete")
        check("delete asks for a second tap", "Tap again" in pg.inner_text("#e-delete"))
        pg.click("#e-delete"); pg.wait_for_timeout(500)
        check("deleted word gone from the list", pg.locator("[data-open='a2']").count() == 0)
        check("deleted record kept in .trash", any((root / ".trash").rglob("word.json")))

        print("saved / exports")
        pg.click('#v-list [data-go="saved"]'); pg.wait_for_timeout(200)
        check("saved page shows the share path", "First Words" in pg.inner_text("#s-folder-name"))
        pg.click("#s-zip"); pg.wait_for_selector("#s-result a", timeout=5000)
        check("backup zip made", any((root / "exports").glob("*.zip")))
        pg.click("#s-book"); pg.wait_for_selector("#s-result a", timeout=5000); pg.wait_for_timeout(200)
        href = pg.get_attribute("#s-result a", "href")
        check("keepsake link is signed", "authSig=" in (href or ""))
        pg.screenshot(path=str(OUT / "s5_saved.png"), full_page=True)

        print("offline queue")
        pg.click('#v-saved [data-go="list"]'); pg.click('#v-list [data-go="add"]'); pg.wait_for_timeout(200)
        pg.set_input_files("#file-in", str(memo))
        pg.wait_for_selector("#c-trim:not([hidden])", timeout=10000)
        pg.fill("#f-word", "up")
        dev_state(base, fail=1000)  # HA unreachable
        pg.click("#save")
        pg.wait_for_selector("#v-detail:not([hidden])", timeout=10000); pg.wait_for_timeout(300)
        check("toast says it's saved on the phone", "Saved on this phone" in pg.inner_text("#toast"))
        pg.click("#v-detail [data-go='list']"); pg.wait_for_timeout(200)
        check("pending chip on the list", pg.locator(".chip.pending").count() == 1)
        check("banner explains the wait", "waiting to upload" in pg.inner_text("#banner"))
        pg.screenshot(path=str(OUT / "s6_offline.png"), full_page=True)
        pg.reload()
        pg.wait_for_function("() => { const e = document.querySelector('first-words-panel'); "
                             "return e && e.shadowRoot && e.shadowRoot.querySelectorAll('.chip.pending').length === 1; }",
                             timeout=10000)
        check("queued word survives a reload (IndexedDB)", True)
        check("not on the server yet", "up" not in [w["word"] for w in json.loads((root / "first-words.json").read_text())["words"]])
        dev_state(base, fail=0)
        pg.evaluate("window.dispatchEvent(new Event('online'))")
        pg.wait_for_function("() => document.querySelector('first-words-panel').shadowRoot.querySelectorAll('.chip.pending').length === 0",
                             timeout=10000)
        ups = [w for w in json.loads((root / "first-words.json").read_text())["words"] if w["word"] == "up"]
        check("queued word uploaded exactly once", len(ups) == 1)
        check("queued word kept its clip", bool(ups and ups[0]["audioFile"].endswith(".wav")))
        check("banner gone", pg.eval_on_selector("#banner", "e=>e.hidden"))
        pg.wait_for_timeout(500)
        check("after reconnecting, the settings load (child's name)", pg.inner_text("#list-title") == "Robin")
        check("after reconnecting, the full list loads", pg.locator(".wcard").count() == 3)

        print("just add a word, capture it later")
        pg.click('#v-list [data-go="quick"]'); pg.wait_for_timeout(200)
        pg.screenshot(path=str(OUT / "s14_quick_add.png"))
        check("quick add hides the recorder", pg.eval_on_selector("#clip-card", "e=>e.hidden"))
        check("quick add title", pg.inner_text("#add-title") == "Add a word")
        check("who-heard offers Mama, Dada, Both, Other",
              [pg.locator("#heard-seg button").nth(i).inner_text() for i in range(pg.locator("#heard-seg button").count())]
              == ["Mama", "Dada", "Both", "Other"])
        check("all four fit on one row at phone width",
              len({round(pg.locator("#heard-seg button").nth(i).bounding_box()["y"]) for i in range(4)}) == 1)
        pg.click('[data-heard="Both"]')
        check("Both is selected", pg.get_attribute('[data-heard="Both"]', "aria-pressed") == "true")
        pg.fill("#f-word", "ball"); pg.fill("#f-date", "2026-11-02"); pg.click("#save")
        pg.wait_for_selector("#v-detail:not([hidden])", timeout=10000); pg.wait_for_timeout(300)
        qball = next(w for w in json.loads((root / "first-words.json").read_text())["words"] if w["date"] == "2026-11-02")
        check("quick word saved with no clip", qball["audioFile"] == "")
        check("Both saved as 'Mama & Dada'", qball["heardBy"] == "Mama & Dada")
        check("detail offers Capture it", pg.eval_on_selector("#d-capture", "e=>!e.hidden")
              and pg.eval_on_selector("#d-player", "e=>e.hidden"))
        pg.screenshot(path=str(OUT / "s13_detail_capture.png"))
        pg.click("#v-detail [data-go='list']"); pg.wait_for_timeout(200)
        check("list shows a mic for it", pg.locator(f'[data-capture="{qball["id"]}"]').count() == 1)
        check("Both chip on the list", pg.locator(f'[data-open="{qball["id"]}"] .chip.both').inner_text() == "Mama & Dada")
        check("its line says no clip yet", "no clip yet" in pg.inner_text(f'[data-open="{qball["id"]}"]'))
        pg.screenshot(path=str(OUT / "s11_list_to_capture.png"))
        metas = [pg.locator(".wmeta").nth(i).bounding_box()["height"] for i in range(pg.locator(".wmeta").count())]
        check(f"no meta line wraps on the phone ({[round(m) for m in metas]})", max(metas) < 22)
        pg.click(f'[data-capture="{qball["id"]}"]'); pg.wait_for_timeout(200)
        check("capture screen names the word", "ball" in pg.inner_text("#add-title"))
        pg.screenshot(path=str(OUT / "s12_capture.png"))
        check("capture screen hides the word form", pg.eval_on_selector("#f-word", "e=>e.offsetParent===null"))
        pg.click("#save"); pg.wait_for_timeout(200)
        check("can't save a capture without a clip", "first" in pg.inner_text("#toast"))
        pg.set_input_files("#file-in", str(memo))
        pg.wait_for_selector("#c-trim:not([hidden])", timeout=10000)
        pg.click("#save")
        pg.wait_for_selector("#v-detail:not([hidden])", timeout=10000); pg.wait_for_timeout(300)
        words = json.loads((root / "first-words.json").read_text())["words"]
        same = [w for w in words if w["id"] == qball["id"]]
        check("clip attached to the same word (no duplicate)", len(same) == 1 and same[0]["audioFile"] == "audio/2026-11-02_ball.wav")
        check("same word count as before", len(words) == len([w for w in words]))
        check("detail now has the player", pg.eval_on_selector("#d-player", "e=>!e.hidden")
              and pg.eval_on_selector("#d-capture", "e=>e.hidden"))
        b.close()

    print("fit and desktop")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        pg.goto(base + "/?top=59")
        pg.wait_for_function("() => /so far/.test(document.querySelector('first-words-panel').shadowRoot.getElementById('list-sub').textContent)", timeout=10000)
        pg.wait_for_timeout(400)
        hero = pg.locator("#v-list .hero").bounding_box()
        bb = pg.locator("#v-list .bottombar").bounding_box()
        check(f"under a 59px header the hero starts right below it (y={hero['y']:.0f})", 59 <= hero["y"] <= 61)
        check(f"and the bottom bar ends at the screen's bottom ({bb['y'] + bb['height']:.0f})", abs(bb["y"] + bb["height"] - 844) < 2)
        pg.screenshot(path=str(OUT / "s8_phone_offset.png"))
        pg = b.new_page(viewport={"width": 1280, "height": 800})
        pg.goto(base + "/?side=256")
        pg.wait_for_function("() => /so far/.test(document.querySelector('first-words-panel').shadowRoot.getElementById('list-sub').textContent)", timeout=10000)
        pg.wait_for_timeout(400)
        cards = pg.locator(".wcard")
        xs = sorted({round(cards.nth(i).bounding_box()["x"]) for i in range(cards.count())})
        check(f"desktop list is a multi-column grid (columns at {xs})", len(xs) >= 2)
        metas = [cards.nth(i).locator(".wmeta").bounding_box()["height"] for i in range(cards.count())]
        check(f"no card's meta line wraps on desktop ({[round(m) for m in metas]})", max(metas) < 22)
        bb = pg.locator("#v-list .bottombar").bounding_box()
        check("desktop bottom bar stays inside the panel, clear of the sidebar", bb["x"] >= 256)
        pg.screenshot(path=str(OUT / "s9_desktop_list.png"))
        pg.locator(".wopen").first.click(); pg.wait_for_timeout(300)
        dc = pg.locator(".dcard").bounding_box()
        check(f"desktop detail is a centred column ({dc['width']:.0f}px)", dc["width"] <= 600)
        pg.screenshot(path=str(OUT / "s10_desktop_detail.png"))
        b.close()

    print("iPhone .mov in WebKit (the engine behind iPhone Safari and the HA app)")
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    variants = {
        "mono-44k-moov-end": ["-ac", "1", "-ar", "44100"],
        "stereo-48k-faststart": ["-ac", "2", "-ar", "48000", "-movflags", "+faststart"],
        "mono-44k-20s": ["-ac", "1", "-ar", "44100"],
        # Live Photo videos carry uncompressed PCM, not AAC
        "livephoto-pcm16le": ["-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le"],
        "pcm16be-stereo": ["-ac", "2", "-ar", "44100", "-c:a", "pcm_s16be"],
        "pcm24le": ["-ac", "1", "-ar", "48000", "-c:a", "pcm_s24le"],
        "pcm-float32": ["-ac", "1", "-ar", "48000", "-c:a", "pcm_f32le"],
    }
    with sync_playwright() as p:
        b = p.webkit.launch()
        for name, extra in variants.items():
            secs = 20 if "20s" in name else 3
            mov = tmp / f"IMG_{name}.MOV"
            # 1 s of silence, then a tone: the waveform and the clip must both show sound
            subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30",
                            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono:d=1[s];sine=frequency=330:duration={secs}[t];[s][t]concat=n=2:v=0:a=1",
                            "-t", str(secs), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", *extra,
                            "-f", "mov", str(mov)], check=True)
            pg = b.new_page(viewport={"width": 390, "height": 844})
            pg.goto(base + "/"); pg.wait_for_timeout(800)
            pg.click('#v-list [data-go="add"]'); pg.wait_for_timeout(200)
            # Same file, but the iPhone picker may hand it over with no type: both must work.
            pg.set_input_files("#file-in", files=[{"name": mov.name, "mimeType": "video/quicktime", "buffer": mov.read_bytes()}])
            pg.wait_for_selector("#c-trim:not([hidden])", timeout=20000); pg.wait_for_timeout(300)
            check(f"{name}: waveform drawn (sound read from the .mov)", "No waveform" not in pg.inner_text("#trim-hint"))
            pg.click("#sel-play"); pg.wait_for_timeout(300)
            st = pg.evaluate("""() => { const a = document.querySelector('first-words-panel')._app._debug, v = a.A.clip.el;
              return { audio: a.P.id, muted: v.muted, playing: !v.paused }; }""")
            check(f"{name}: preview plays our decoded sound with the picture muted alongside ({st})",
                  st["audio"] == "preview" and st["muted"] and st["playing"])
            pg.click("#sel-play"); pg.wait_for_timeout(100)
            pg.fill("#f-word", "w-" + name); pg.click("#save")
            pg.wait_for_selector("#v-detail:not([hidden])", timeout=20000)
            pg.wait_for_function("() => document.querySelector('first-words-panel').shadowRoot.getElementById('upbar').hidden", timeout=30000)
            w = next(x for x in json.loads((root / "first-words.json").read_text())["words"] if x["word"] == "w-" + name)
            check(f"{name}: clip saved as .wav", w["audioFile"].endswith(".wav"))
            with wave.open(str(root / w["audioFile"])) as wf:
                frames = wf.readframes(wf.getnframes()); sr = wf.getframerate(); nfr = wf.getnframes()
            samples = struct.unpack("<%dh" % (len(frames) // 2), frames)
            sec1 = samples[sr: 2 * sr] if len(samples) >= 2 * sr else samples[sr:]
            quiet = samples[: int(sr * 0.8)]
            rms = lambda xs: math.sqrt(sum(x * x for x in xs) / max(1, len(xs)))
            check(f"{name}: clip has the tone after 1 s (rms {rms(sec1):.0f}) and silence before (rms {rms(quiet):.0f})",
                  rms(sec1) > 1000 and rms(quiet) < 200)
            pg.close()

        # The HA app on its http:// internal URL: no microphone API and no audioSession.
        print("insecure page (HA app on http://)")
        pg = b.new_page(viewport={"width": 390, "height": 844})
        pg.add_init_script("delete Navigator.prototype.mediaDevices; delete Navigator.prototype.audioSession;"
                           "Object.defineProperty(navigator, 'mediaDevices', {value: undefined});"
                           "Object.defineProperty(navigator, 'audioSession', {value: undefined});"
                           # and WebKit never finishing a big video into IndexedDB
                           "(() => { const t = IDBDatabase.prototype.transaction; IDBDatabase.prototype.transaction = function (n, m) {"
                           "  if (m !== 'readwrite') return t.apply(this, arguments);"
                           "  const req = {}; return { objectStore: () => ({ put: () => req, delete: () => req }) }; }; })();")
        pg.goto(base + "/"); pg.wait_for_timeout(800)
        check("init script removed the APIs", pg.evaluate("() => !navigator.mediaDevices && !navigator.audioSession"))
        pg.click('#v-list [data-go="add"]'); pg.wait_for_timeout(200)
        with pg.expect_file_chooser(timeout=3000) as fc:
            pg.click("#rec-start")
        check("record button opens the camera instead of failing", fc.value is not None)
        mov = tmp / "IMG_livephoto-pcm16le.MOV"
        fc.value.set_files(str(mov))
        pg.wait_for_selector("#c-trim:not([hidden])", timeout=20000); pg.wait_for_timeout(300)
        check("camera clip reaches the trim view", "No waveform" not in pg.inner_text("#trim-hint"))
        pg.click("#sel-play"); pg.wait_for_timeout(400)
        st = pg.evaluate("""() => { const a = document.querySelector('first-words-panel')._app._debug, h = a.hush();
          return { audio: a.P.id, hush: !!h && !h.paused }; }""")
        check(f"no audioSession: a silent media element plays alongside the Web Audio ({st})",
              st["audio"] == "preview" and st["hush"])
        pg.click("#sel-play"); pg.wait_for_timeout(200)
        check("and stops with it", pg.evaluate("() => { const h = document.querySelector('first-words-panel')._app._debug.hush(); return h.paused; }"))
        pg.fill("#f-word", "camera-word"); pg.click("#save")
        pg.wait_for_selector("#v-detail:not([hidden])", timeout=20000)
        t0 = time.time()
        pg.wait_for_function("() => document.querySelector('first-words-panel').shadowRoot.getElementById('upbar').hidden", timeout=30000)
        w = next(x for x in json.loads((root / "first-words.json").read_text())["words"] if x["word"] == "camera-word")
        check(f"video uploads although the offline copy never finishes ({time.time() - t0:.1f}s)", bool(w.get("videoFile")))

        # Home Assistant never answers the start: the bar must count, sit clear of the
        # header, and cancel must clear it and forget the queued video.
        pg.route("**/video/*/start", lambda route: None)
        pg.click('#v-detail [data-go="list"], #v-detail .back') if pg.locator('#v-detail .back').count() else None
        pg.evaluate("() => document.querySelector('first-words-panel')._app._debug")
        pg.goto(base + "/"); pg.wait_for_timeout(800)
        pg.click('#v-list [data-go="add"]'); pg.wait_for_timeout(200)
        pg.set_input_files("#file-in", str(mov))
        pg.wait_for_selector("#c-trim:not([hidden])", timeout=20000)
        pg.fill("#f-word", "hung-word"); pg.click("#save")
        pg.wait_for_selector("#v-detail:not([hidden])", timeout=20000)
        pg.wait_for_function("() => /Contacting Home Assistant… [2-9]s/.test(document.querySelector('first-words-panel').shadowRoot.getElementById('up-text').textContent)", timeout=15000)
        check("stalled start shows a running count", True)
        bar = pg.locator("#upbar").bounding_box()
        head = pg.locator("#v-detail button").first.bounding_box()
        check(f"upload bar sits clear of the header (bar y={bar['y']:.0f}, first button y={head['y']:.0f})",
              bar["y"] > head["y"] + head["height"])
        check("bar is at the bottom of the screen", bar["y"] + bar["height"] > 844 - 120)
        pg.click("#up-cancel"); pg.wait_for_timeout(300)
        st = pg.evaluate("""() => { const a = document.querySelector('first-words-panel')._app._debug;
          return { up: a.S.upload, hidden: document.querySelector('first-words-panel').shadowRoot.getElementById('upbar').hidden,
                   pending: a.S.pending.filter(x => x.type === 'video').length }; }""")
        check(f"cancel clears the bar and forgets the queued video ({st})", st["up"] is None and st["hidden"] and st["pending"] == 0)
        pg.close()
        b.close()

    real = [Path(x) for x in os.environ.get("FW_REAL_MOVS", "").split(os.pathsep) if x]
    if real:
        print("real phone files (FW_REAL_MOVS, never committed)")
        with sync_playwright() as p:
            b = p.webkit.launch()
            for f in real:
                pg = b.new_page(viewport={"width": 390, "height": 844})
                pg.goto(base + "/"); pg.wait_for_timeout(800)
                pg.click('#v-list [data-go="add"]'); pg.set_input_files("#file-in", str(f))
                pg.wait_for_selector("#c-trim:not([hidden])", timeout=60000); pg.wait_for_timeout(300)
                check(f"{f.name}: waveform drawn", "No waveform" not in pg.inner_text("#trim-hint"))
                pg.close()
            b.close()

    print("not mounted")
    tmp2 = Path(tempfile.mkdtemp(prefix="fw-ui2-"))
    start_server(str(tmp2), port + 1, mounted=False)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 390, "height": 844})
        pg.on("pageerror", lambda e: errs.append("PAGEERROR " + str(e)))
        pg.goto(f"http://127.0.0.1:{port + 1}/"); pg.wait_for_timeout(1200)
        check("banner says the NAS isn't connected", "isn't connected" in pg.inner_text("#banner") and "Test NAS" in pg.inner_text("#banner"))
        pg.screenshot(path=str(OUT / "s7_unmounted.png"))
        b.close()
    check("nothing written when not mounted", not any(tmp2.rglob("first-words.json")))

    check("no console errors: " + "; ".join(errs[:3]), not errs)
    shutil.rmtree(tmp, ignore_errors=True); shutil.rmtree(tmp2, ignore_errors=True)
    print(f"\n{len(FAILS)} failed" if FAILS else "\nall passed")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
