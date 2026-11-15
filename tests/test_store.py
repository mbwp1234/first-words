"""store.py tests: plain pytest, no Home Assistant needed."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import zipfile
from datetime import date
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "fw_store", Path(__file__).parents[1] / "custom_components" / "first_words" / "store.py")
store = importlib.util.module_from_spec(_SPEC)
sys.modules["fw_store"] = store
_SPEC.loader.exec_module(store)

TODAY = date(2026, 11, 14)


@pytest.fixture
def ws(tmp_path):
    cfg = store.StoreConfig(mount_path=str(tmp_path / "share"), folder="First Words",
                            child="Kid", birthday="2025-09-01", require_mount=False)
    (tmp_path / "share").mkdir()
    return store.WordStore(cfg, today=lambda: TODAY)


def data(ws):
    return json.loads((ws.root / "first-words.json").read_text())


# ---------------------------------------------------------------- mount guard

def test_refuses_to_write_when_share_not_mounted(tmp_path):
    (tmp_path / "share").mkdir()
    cfg = store.StoreConfig(mount_path=str(tmp_path / "share"), folder="First Words", child="Kid")
    ws = store.WordStore(cfg)  # require_mount defaults to True; a plain dir is not a mount
    with pytest.raises(store.StorageUnavailable):
        ws.create({"word": "ball"}, "Tester", b"RIFF")
    assert not (tmp_path / "share" / "First Words").exists(), "must not create anything on the local disk"
    assert ws.status()["mounted"] is False


def test_missing_mount_dir_is_unavailable(tmp_path):
    cfg = store.StoreConfig(mount_path=str(tmp_path / "nope"), folder="x", child="Kid", require_mount=False)
    with pytest.raises(store.StorageUnavailable):
        store.WordStore(cfg).list_words()


# ---------------------------------------------------------------- atomic write / read

def test_create_writes_json_clip_and_daily_snapshot(ws):
    w, created = ws.create({"word": "Ball", "sounded": "baw", "date": "2026-11-12", "heardBy": "Mama",
                            "clipStart": "8.234", "clipEnd": 12.6}, "Alex", b"RIFFdata", "wav")
    assert created
    assert w["audioFile"] == "audio/2026-11-12_ball.wav"
    assert (ws.root / w["audioFile"]).read_bytes() == b"RIFFdata"
    d = data(ws)
    assert d["child"] == "Kid" and d["words"][0]["word"] == "Ball"
    assert d["words"][0]["addedBy"] == "Alex"
    assert d["words"][0]["clipStart"] == 8.23 and d["words"][0]["clipEnd"] == 12.6
    snap = ws.root / "history" / "first-words-2026-11-14.json"
    assert json.loads(snap.read_text())["words"][0]["id"] == w["id"]
    leftovers = [p.name for p in ws.root.rglob("*") if ".tmp" in p.name]
    assert leftovers == []


def test_word_required_and_fields_cleaned(ws):
    with pytest.raises(store.BadRequest):
        ws.create({"word": "   "}, "x")
    w, _ = ws.create({"word": "  big   dog ", "date": "garbage", "notes": " hi \n there "}, "x")
    assert w["word"] == "big dog" and w["date"] == "2026-11-14" and w["notes"] == "hi \n there"
    assert w["audioFile"] == "" and w["clipStart"] is None


def test_same_client_id_is_idempotent(ws):
    a, c1 = ws.create({"id": "client-abc", "word": "ball"}, "x", b"1")
    b, c2 = ws.create({"id": "client-abc", "word": "ball"}, "x", b"1")
    assert c1 and not c2 and a == b
    assert len(data(ws)["words"]) == 1
    assert len(list((ws.root / "audio").iterdir())) == 1


def test_unsafe_client_id_replaced(ws):
    w, _ = ws.create({"id": "../../etc", "word": "ball"}, "x")
    assert w["id"] != "../../etc"


def test_bad_extension_falls_back_to_wav(ws):
    w, _ = ws.create({"word": "ball"}, "x", b"1", "exe")
    assert w["audioFile"].endswith(".wav")


def test_duplicate_names_get_suffix(ws):
    a, _ = ws.create({"word": "ball", "date": "2026-11-12"}, "x", b"1")
    b, _ = ws.create({"word": "ball", "date": "2026-11-12"}, "x", b"2")
    assert a["audioFile"] == "audio/2026-11-12_ball.wav"
    assert b["audioFile"] == "audio/2026-11-12_ball-2.wav"


def test_corrupt_json_is_never_overwritten(ws):
    ws.create({"word": "ball"}, "x")
    (ws.root / "first-words.json").write_text("{not json")
    with pytest.raises(store.StorageUnavailable):
        ws.create({"word": "dog"}, "x")
    assert (ws.root / "first-words.json").read_text() == "{not json"


def test_sorted_newest_first(ws):
    ws.create({"word": "a", "date": "2026-01-01"}, "x")
    ws.create({"word": "b", "date": "2026-03-01"}, "x")
    ws.create({"word": "c", "date": "2026-02-01"}, "x")
    assert [w["word"] for w in ws.list_words()] == ["b", "c", "a"]


# ---------------------------------------------------------------- edit renames

def test_edit_renames_audio_and_video(ws):
    w, _ = ws.create({"word": "ball", "date": "2026-11-12"}, "x", b"1")
    tok = ws.video_start(w["id"], "IMG_1.MOV", "video/quicktime", 3)
    ws.video_chunk(tok, 0, b"abc")
    ws.video_finish(tok)
    out = ws.update(w["id"], {"word": "Big ball", "date": "2026-11-13"})
    assert out["audioFile"] == "audio/2026-11-13_big-ball.wav"
    assert out["videoFile"] == "video/2026-11-13_big-ball.mov"
    assert (ws.root / out["audioFile"]).exists() and (ws.root / out["videoFile"]).exists()
    assert not (ws.root / "audio/2026-11-12_ball.wav").exists()
    assert data(ws)["words"][0]["audioFile"] == out["audioFile"]


def test_edit_keeps_unspecified_fields_and_rejects_empty(ws):
    w, _ = ws.create({"word": "ball", "notes": "couch", "heardBy": "Mama"}, "x")
    out = ws.update(w["id"], {"sounded": "baw"})
    assert out["notes"] == "couch" and out["heardBy"] == "Mama" and out["sounded"] == "baw"
    with pytest.raises(store.BadRequest):
        ws.update(w["id"], {"word": ""})
    with pytest.raises(store.NotFound):
        ws.update("nope", {"word": "x"})


def test_edit_same_name_no_suffix(ws):
    w, _ = ws.create({"word": "ball", "date": "2026-11-12"}, "x", b"1")
    out = ws.update(w["id"], {"notes": "changed"})
    assert out["audioFile"] == "audio/2026-11-12_ball.wav"


# ---------------------------------------------------------------- trash, not delete

def test_delete_moves_files_and_record_to_trash(ws):
    w, _ = ws.create({"word": "ball", "date": "2026-11-12"}, "x", b"clip")
    rel = ws.delete(w["id"])
    trash = ws.root / rel
    assert (trash / "2026-11-12_ball.wav").read_bytes() == b"clip"
    assert json.loads((trash / "word.json").read_text())["word"] == "ball"
    assert data(ws)["words"] == []
    assert not (ws.root / "audio/2026-11-12_ball.wav").exists()


def test_no_unlink_in_delete_paths():
    src = (Path(store.__file__)).read_text()
    body = src[src.index("    def delete("):src.index("    def file_path(")]
    assert "unlink" not in body and "os.remove" not in body and "rmtree" not in body


# ---------------------------------------------------------------- path traversal

@pytest.mark.parametrize("rel", ["../secret.txt", "audio/../../secret.txt", "/etc/passwd", "\x00"])
def test_traversal_rejected(ws, rel):
    w, _ = ws.create({"word": "ball"}, "x", b"1")
    (ws.mount / "secret.txt").write_text("outside the root")  # real file, so only the guard can refuse it
    d = data(ws)
    d["words"][0]["audioFile"] = rel
    (ws.root / "first-words.json").write_text(json.dumps(d))
    with pytest.raises(store.NotFound):
        ws.file_path(w["id"], "audio")


def test_file_path_ok(ws):
    w, _ = ws.create({"word": "ball"}, "x", b"1")
    assert ws.file_path(w["id"], "audio").read_bytes() == b"1"
    with pytest.raises(store.NotFound):
        ws.file_path(w["id"], "video")


@pytest.mark.parametrize("name", ["../first-words.json", "a/b.zip", "x.exe", ".hidden.zip"])
def test_export_name_rejected(ws, name):
    ws.list_words()
    with pytest.raises(store.NotFound):
        ws.export_file(name)


def test_bad_token_rejected(ws):
    for tok in ["../../x", "abc", "Z" * 32]:
        with pytest.raises(store.NotFound):
            ws.video_chunk(tok, 0, b"x")


# ---------------------------------------------------------------- chunked video

def test_chunk_assembly_with_size_check(ws):
    w, _ = ws.create({"word": "ball", "date": "2026-11-12"}, "x")
    blob = os.urandom(10_000)
    tok = ws.video_start(w["id"], "clip.mp4", "video/mp4", len(blob))
    assert ws.video_chunk(tok, 0, blob[:4000]) == 4000
    with pytest.raises(store.Conflict) as e:  # a resent chunk at a stale offset
        ws.video_chunk(tok, 0, blob[:4000])
    assert e.value.received == 4000
    with pytest.raises(store.Conflict):  # finishing early
        ws.video_finish(tok)
    ws.video_chunk(tok, 4000, blob[4000:])
    with pytest.raises(store.BadRequest):  # past the declared size
        ws.video_chunk(tok, 10_000, b"x")
    out = ws.video_finish(tok)
    assert out["videoFile"] == "video/2026-11-12_ball.mp4"
    assert (ws.root / out["videoFile"]).read_bytes() == blob
    assert list((ws.root / "video/.partial").iterdir()) == []
    with pytest.raises(store.NotFound):
        ws.video_finish(tok)


def test_replacing_video_trashes_old(ws):
    w, _ = ws.create({"word": "ball", "date": "2026-11-12"}, "x")
    for payload in (b"old", b"new"):
        tok = ws.video_start(w["id"], "a.mp4", "video/mp4", 3)
        ws.video_chunk(tok, 0, payload)
        out = ws.video_finish(tok)
    assert (ws.root / out["videoFile"]).read_bytes() == b"new"
    trashed = list((ws.root / ".trash").rglob("*.mp4"))
    assert len(trashed) == 1 and trashed[0].read_bytes() == b"old"


def test_video_start_validates(ws):
    w, _ = ws.create({"word": "ball"}, "x")
    with pytest.raises(store.BadRequest):
        ws.video_start(w["id"], "a.mp4", "video/mp4", 0)
    with pytest.raises(store.NotFound):
        ws.video_start("nope", "a.mp4", "video/mp4", 5)
    tok = ws.video_start(w["id"], "a.exe", "video/quicktime", 5)
    info = json.loads((ws.root / "video/.partial" / f"{tok}.json").read_text())
    assert info["ext"] == "mov"


# ---------------------------------------------------------------- export, keepsake

def test_export_zip(ws):
    ws.create({"word": "ball", "date": "2026-11-12"}, "x", b"clip")
    name = ws.export_zip()
    with zipfile.ZipFile(ws.export_file(name)) as zf:
        names = set(zf.namelist())
        assert {"audio/2026-11-12_ball.wav", "first-words.csv", "first-words.json"} <= names
        assert json.loads(zf.read("first-words.json"))["words"][0]["word"] == "ball"


def test_keepsake_escapes(ws):
    ws.create({"word": "<b>ball</b>", "date": "2026-11-12", "heardBy": "Mama"}, "x")
    html = ws.export_file(ws.keepsake()).read_text()
    assert "&lt;b&gt;ball" in html and "<b>ball" not in html
    assert "14 months, 1 week old" in html


@pytest.mark.parametrize("bday,on,want", [
    ("2025-09-01", "2025-09-20", "2 weeks"),
    ("2025-09-01", "2026-11-12", "14 months, 1 week"),
    ("2025-09-01", "2026-10-01", "13 months"),
    ("2024-01-31", "2026-03-15", "2 years, 1 months"),
    ("2025-09-01", "2025-08-01", ""),
])
def test_age_text_matches_app(bday, on, want):
    assert store.age_text(bday, on) == want


# ---------------------------------------------------------------- importer

APPS_SCRIPT = {
    "child": "Kid", "birthday": "2025-09-01", "exportedAt": "2026-11-10T00:00:00Z",
    "fields": ["ID", "Word"],
    "words": [
        {"id": "5c2b7a3e-0000-4000-8000-000000000001", "word": "ball", "sounded": "baw", "date": "2026-11-12",
         "heardBy": "Mama", "notes": "", "addedBy": "Alex", "audioId": "drive1",
         "audioUrl": "https://drive/x", "videoId": "drive2", "videoUrl": "https://drive/v",
         "clipStart": "8.2", "clipEnd": "12.6", "savedAt": "2026-11-12T15:00:00.000Z"},
        {"id": "5c2b7a3e-0000-4000-8000-000000000002", "word": "dada", "sounded": "", "date": "2026-09-18",
         "heardBy": "Dada", "notes": "", "addedBy": "Sam", "audioId": "", "audioUrl": "",
         "videoId": "", "videoUrl": "", "clipStart": "", "clipEnd": "", "savedAt": "2026-09-18T10:00:00Z"},
        {"id": "5c2b7a3e-0000-4000-8000-000000000003", "word": "up", "date": "2026-10-01",
         "audioId": "drive3", "clipStart": "", "clipEnd": "", "savedAt": "2026-10-01T10:00:00Z"},
    ],
}


def _drive_zip(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("2026-11-12_ball.wav", b"BALL")
        zf.writestr("first-words.json", json.dumps(APPS_SCRIPT))
        zf.writestr("first-words.csv", "x")
    return path


def test_import_from_backup_zip(ws, tmp_path):
    counts = ws.import_json(str(_drive_zip(tmp_path / "backup.zip")))
    assert counts == {"imported": 3, "skipped": 0, "clips": 1, "missing_clips": 1}
    words = {w["word"]: w for w in data(ws)["words"]}
    assert words["ball"]["audioFile"] == "audio/2026-11-12_ball.wav"
    assert (ws.root / "audio/2026-11-12_ball.wav").read_bytes() == b"BALL"
    assert words["ball"]["clipStart"] == 8.2 and words["ball"]["driveVideoUrl"] == "https://drive/v"
    assert words["ball"]["addedBy"] == "Alex" and words["ball"]["savedAt"] == "2026-11-12T15:00:00.000Z"
    assert words["dada"]["audioFile"] == "" and words["dada"]["clipStart"] is None
    assert "audioId" not in words["ball"]
    assert ws.import_json(str(tmp_path / "backup.zip"))["skipped"] == 3


def test_import_json_with_clips_folder(ws, tmp_path):
    (tmp_path / "clips").mkdir()
    (tmp_path / "clips" / "2026-11-12_ball (1).wav").write_bytes(b"B")
    (tmp_path / "clips" / "2026-10-01_up.m4a").write_bytes(b"U")
    (tmp_path / "fw.json").write_text(json.dumps(APPS_SCRIPT))
    counts = ws.import_json(str(tmp_path / "fw.json"), str(tmp_path / "clips"))
    assert counts["clips"] == 2 and counts["missing_clips"] == 0
    up = next(w for w in data(ws)["words"] if w["word"] == "up")
    assert up["audioFile"] == "audio/2026-10-01_up.m4a"


def test_import_own_export_roundtrip(ws, tmp_path):
    ws.create({"word": "ball", "date": "2026-11-12"}, "x", b"clip")
    name = ws.export_zip()
    cfg = store.StoreConfig(mount_path=str(tmp_path / "share2"), folder="FW", child="Kid", require_mount=False)
    (tmp_path / "share2").mkdir()
    other = store.WordStore(cfg, today=lambda: TODAY)
    counts = other.import_json(str(ws.export_file(name)))
    assert counts["imported"] == 1 and counts["clips"] == 1


# ---------------------------------------------------------------- write it down now, capture it later

def test_attach_audio_to_word_without_one(ws):
    w, _ = ws.create({"word": "ball", "date": "2026-11-10"}, "x")
    assert w["audioFile"] == ""
    out = ws.attach_audio(w["id"], b"RIFFclip", "wav", "1.234", 2.5)
    assert out["audioFile"] == "audio/2026-11-10_ball.wav"
    assert (ws.root / out["audioFile"]).read_bytes() == b"RIFFclip"
    assert out["clipStart"] == 1.23 and out["clipEnd"] == 2.5 and out["capturedAt"]
    assert data(ws)["words"][0]["audioFile"] == out["audioFile"]


def test_attach_audio_trashes_previous_clip(ws):
    w, _ = ws.create({"word": "ball", "date": "2026-11-10"}, "x", b"old")
    out = ws.attach_audio(w["id"], b"new", "m4a")
    assert (ws.root / out["audioFile"]).read_bytes() == b"new"
    assert [p.read_bytes() for p in (ws.root / ".trash").rglob("*.wav")] == [b"old"]


def test_attach_audio_validates(ws):
    w, _ = ws.create({"word": "ball"}, "x")
    with pytest.raises(store.BadRequest):
        ws.attach_audio(w["id"], b"")
    with pytest.raises(store.NotFound):
        ws.attach_audio("nope", b"x")
    assert ws.attach_audio(w["id"], b"x", "exe")["audioFile"].endswith(".wav")


def test_dispatcher_handlers_are_callbacks():
    """HA runs a non-@callback dispatcher target in the executor; the sensor's
    refresh then fails off the event loop (seen live in v0.2.0)."""
    import re as _re
    src = (Path(__file__).parents[1] / "custom_components/first_words/sensor.py").read_text()
    targets = _re.findall(r"async_dispatcher_connect\([^)]*?SIGNAL_CHANGED,\s*([^)\s]+)\)", src)
    assert targets, "sensor no longer subscribes to SIGNAL_CHANGED?"
    for t in targets:
        assert not t.startswith("lambda"), t
        name = t.split(".")[-1]
        assert _re.search(r"@callback\s+def " + name + r"\b", src), f"{name} is not a @callback"


def test_both_becomes_the_full_label(tmp_path):
    (tmp_path / "s").mkdir()
    cfg = store.StoreConfig(mount_path=str(tmp_path / "s"), folder="FW", child="Kid",
                            require_mount=False, both_label="Mama & Dada")
    ws = store.WordStore(cfg, today=lambda: TODAY)
    w, _ = ws.create({"word": "sock", "heardBy": "both"}, "x")
    assert w["heardBy"] == "Mama & Dada"
    assert ws.update(w["id"], {"heardBy": "Both"})["heardBy"] == "Mama & Dada"
    assert ws.update(w["id"], {"heardBy": "Grandma"})["heardBy"] == "Grandma"


def test_normalize_existing_both_entries(tmp_path):
    (tmp_path / "s").mkdir()
    plain = store.WordStore(store.StoreConfig(mount_path=str(tmp_path / "s"), folder="FW", child="Kid",
                                              require_mount=False), today=lambda: TODAY)
    plain.create({"word": "sock", "heardBy": "Both"}, "x")
    plain.create({"word": "dada", "heardBy": "Dada"}, "x")
    fixer = store.WordStore(store.StoreConfig(mount_path=str(tmp_path / "s"), folder="FW", child="Kid",
                                              require_mount=False, both_label="Mama & Dada"), today=lambda: TODAY)
    assert fixer.normalize_heard_by() == 1
    assert {w["word"]: w["heardBy"] for w in fixer.list_words()} == {"sock": "Mama & Dada", "dada": "Dada"}
    assert fixer.normalize_heard_by() == 0  # idempotent


def test_both_label_matches_panel_rule():
    import importlib.util as iu
    spec = iu.spec_from_file_location("fw_const", Path(__file__).parents[1] / "custom_components/first_words/const.py")
    const = iu.module_from_spec(spec); spec.loader.exec_module(const)
    assert const.both_label([{"label": "Mama"}, {"label": "Dada"}]) == "Mama & Dada"
    assert const.both_label([{"label": "A"}, {"label": "B"}, {"label": "C"}]) == "A, B & C"
    assert const.both_label([{"label": "A"}]) == ""
