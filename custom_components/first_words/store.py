"""All file I/O for First Words.

Plain Python with no Home Assistant imports, so it can be tested on its own and
so the on-disk format stays readable without HA. Every public method is
blocking and must be called from the executor.

Layout under the storage root:

    first-words.json                 source of truth, rewritten atomically
    audio/<date>_<slug>.<ext>        one clip per word
    video/<date>_<slug>.<ext>        optional full original videos
    video/.partial/<token>.part      a chunked upload in progress
    history/first-words-<date>.json  one snapshot per day, never pruned
    .trash/<stamp>_<id>/             deleted words: their files plus word.json
    exports/                         backup zips and the printable keepsake

Nothing is ever unlinked except finished-upload bookkeeping and our own temp
files. Deleting a word moves it into .trash.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import threading
import uuid
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Callable

DATA_FILE = "first-words.json"
AUDIO_DIR = "audio"
VIDEO_DIR = "video"
PARTIAL_DIR = "video/.partial"
HISTORY_DIR = "history"
TRASH_DIR = ".trash"
EXPORT_DIR = "exports"

AUDIO_EXTS = {"wav", "m4a", "mp4", "webm", "ogg", "mp3", "aac"}
TRIM_SUFFIX = "_trim"
VIDEO_EXTS = {"mov", "mp4", "m4v", "webm", "3gp"}
MAX_AUDIO_BYTES = 30 * 1024 * 1024
MAX_CHUNK_BYTES = 8 * 1024 * 1024
MAX_VIDEO_BYTES = 4 * 1024 * 1024 * 1024

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EXPORT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,120}\.(zip|html|csv|json)$")

CSV_HEADERS = ["ID", "Word", "Sounded like", "Date", "Heard by", "Notes", "Added by",
               "Audio file", "Video file", "Clip start (s)", "Clip end (s)", "Saved at"]


class FirstWordsError(Exception):
    """Base error. The message is shown to the person in the app."""

    status = 400


class StorageUnavailable(FirstWordsError):
    """The share is not mounted (or the data file is unreadable). Nothing was written."""

    status = 503


class NotFound(FirstWordsError):
    status = 404


class BadRequest(FirstWordsError):
    status = 400


class Conflict(FirstWordsError):
    """A chunk arrived at the wrong offset. `received` says where to resume."""

    status = 409

    def __init__(self, message: str, received: int) -> None:
        super().__init__(message)
        self.received = received


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:40].strip("-")
    return s or "word"


def file_stem(word: dict[str, Any]) -> str:
    return f"{word['date']}_{slug(word['word'])}"


def _txt(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", "" if value is None else str(value)).strip()[:limit]


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n != n or n in (float("inf"), float("-inf")):
        return None
    return round(n, 2)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class StoreConfig:
    mount_path: str
    folder: str
    child: str
    birthday: str = ""
    require_mount: bool = True
    both_label: str = ""  # what "Both" means, e.g. "Mama & Dada"


class WordStore:
    """Reads and writes the First Words folder. Thread-safe; blocking."""

    def __init__(self, config: StoreConfig, today: Callable[[], date] | None = None) -> None:
        self.config = config
        self.mount = Path(config.mount_path)
        self.root = self.mount / config.folder if config.folder else self.mount
        self._today = today or date.today
        self._lock = threading.RLock()

    # ------------------------------------------------------------ readiness

    def is_mounted(self) -> bool:
        if not self.config.require_mount:
            return self.mount.is_dir()
        try:
            return os.path.ismount(self.mount)
        except OSError:
            return False

    def check_ready(self) -> None:
        """Refuse to touch anything unless the share is really mounted.

        Without this, an unmounted /media/<share> is just an empty directory on
        the VM's own disk, and words would be "saved" somewhere no backup sees.
        """
        if not self.is_mounted():
            raise StorageUnavailable(
                f"The network share isn't mounted at {self.mount}, so nothing was saved. "
                "Check Settings > System > Storage in Home Assistant."
            )
        for sub in ("", AUDIO_DIR, VIDEO_DIR, PARTIAL_DIR, HISTORY_DIR, TRASH_DIR, EXPORT_DIR):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    def status(self) -> dict[str, Any]:
        mounted = self.is_mounted()
        out: dict[str, Any] = {"mounted": mounted, "path": str(self.root), "words": None}
        if mounted:
            try:
                out["words"] = len(self._read()["words"])
            except FirstWordsError as err:
                out["error"] = str(err)
        return out

    # ------------------------------------------------------------ the data file

    def _read(self) -> dict[str, Any]:
        path = self.root / DATA_FILE
        if not path.exists():
            return {"child": self.config.child, "birthday": self.config.birthday, "words": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            # Never "recover" by writing an empty file over a damaged one.
            raise StorageUnavailable(
                f"{DATA_FILE} can't be read ({err}). Nothing was changed; "
                f"the daily copies are in {HISTORY_DIR}/."
            ) from err
        if not isinstance(data, dict) or not isinstance(data.get("words"), list):
            raise StorageUnavailable(f"{DATA_FILE} isn't in the expected format. Nothing was changed.")
        return data

    def _atomic_write_bytes(self, path: Path, payload: bytes) -> None:
        tmp = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex[:8]}")
        try:
            with open(tmp, "wb") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                tmp.unlink()

    def _write(self, data: dict[str, Any]) -> None:
        data = {
            "child": self.config.child,
            "birthday": self.config.birthday,
            "exportedAt": _now_iso(),
            "words": sort_words(data["words"]),
        }
        payload = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self._atomic_write_bytes(self.root / DATA_FILE, payload)
        snap = self.root / HISTORY_DIR / f"first-words-{self._today().isoformat()}.json"
        self._atomic_write_bytes(snap, payload)

    # ------------------------------------------------------------ helpers

    def _clean(self, raw: dict[str, Any]) -> dict[str, Any]:
        d = str(raw.get("date") or "")
        if not DATE_RE.match(d):
            d = self._today().isoformat()
        return {
            "word": _txt(raw.get("word"), 60),
            "sounded": _txt(raw.get("sounded"), 60),
            "date": d,
            "heardBy": self._heard(raw.get("heardBy")),
            "notes": ("" if raw.get("notes") is None else str(raw.get("notes"))).strip()[:1000],
        }

    def _heard(self, value: Any) -> str:
        h = _txt(value, 40)
        if self.config.both_label and h.lower() in ("both", "both of us", "both parents"):
            return self.config.both_label
        return h

    def normalize_heard_by(self) -> int:
        """Rewrite words saved as plain "Both" to the full label. Returns how many changed."""
        if not self.config.both_label:
            return 0
        with self._lock:
            self.check_ready()
            data = self._read()
            n = 0
            for w in data["words"]:
                fixed = self._heard(w.get("heardBy"))
                if fixed != (w.get("heardBy") or ""):
                    w["heardBy"] = fixed
                    n += 1
            if n:
                self._write(data)
            return n

    def _safe(self, rel: str) -> Path:
        """Resolve a stored relative path, refusing anything outside the root."""
        if not rel or rel.startswith(("/", "\\")) or "\x00" in rel:
            raise NotFound("That file isn't part of First Words.")
        root = self.root.resolve()
        path = (self.root / rel).resolve()
        if path != root and root not in path.parents:
            raise NotFound("That file isn't part of First Words.")
        return path

    def _unique(self, directory: str, stem: str, ext: str, own: str = "") -> str:
        """A free relative path like audio/2026-11-12_ball.wav (or _ball-2.wav)."""
        n = 1
        while True:
            name = f"{stem}{'' if n == 1 else '-' + str(n)}.{ext}"
            rel = f"{directory}/{name}"
            if rel == own or not (self.root / rel).exists():
                return rel
            n += 1

    @staticmethod
    def _find(words: list[dict[str, Any]], word_id: str) -> dict[str, Any] | None:
        for w in words:
            if w.get("id") == word_id:
                return w
        return None

    def _rename(self, word: dict[str, Any], key: str, directory: str, suffix: str = "") -> None:
        rel = word.get(key) or ""
        if not rel:
            return
        src = self.root / rel
        ext = rel.rsplit(".", 1)[-1] if "." in rel else ""
        target = self._unique(directory, file_stem(word) + suffix, ext, own=rel)
        if target != rel and src.exists():
            os.replace(src, self.root / target)
            word[key] = target

    def _trash(self, word: dict[str, Any], reason: str) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = self.root / TRASH_DIR / f"{stamp}_{word.get('id', 'word')}_{reason}"
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    # ------------------------------------------------------------ words

    def list_words(self) -> list[dict[str, Any]]:
        with self._lock:
            self.check_ready()
            return sort_words(self._read()["words"])

    def get_word(self, word_id: str) -> dict[str, Any]:
        with self._lock:
            self.check_ready()
            w = self._find(self._read()["words"], word_id)
            if not w:
                raise NotFound("That word was not found. Pull down to refresh.")
            return w

    def create(self, meta: dict[str, Any], added_by: str, audio: bytes | None = None,
               audio_ext: str = "wav") -> tuple[dict[str, Any], bool]:
        """Save a new word. Returns (word, created).

        The client may supply the id. A retry of the same id (the offline queue
        resending after a dropped response) returns the stored word unchanged
        instead of saving a duplicate.
        """
        c = self._clean(meta)
        if not c["word"]:
            raise BadRequest("Type the word first.")
        word_id = str(meta.get("id") or "")
        if not ID_RE.match(word_id):
            word_id = str(uuid.uuid4())
        if audio is not None:
            if len(audio) > MAX_AUDIO_BYTES:
                raise BadRequest("That clip is too long. Keep it under a minute.")
            audio_ext = str(audio_ext or "wav").lower()
            if audio_ext not in AUDIO_EXTS:
                audio_ext = "wav"
        with self._lock:
            self.check_ready()
            data = self._read()
            existing = self._find(data["words"], word_id)
            if existing:
                return existing, False
            word: dict[str, Any] = {
                "id": word_id, **c, "addedBy": _txt(added_by, 40),
                "audioFile": "", "videoFile": "",
                "clipStart": _num(meta.get("clipStart")), "clipEnd": _num(meta.get("clipEnd")),
                "savedAt": _now_iso(),
            }
            if audio:
                rel = self._unique(AUDIO_DIR, file_stem(word), audio_ext)
                self._atomic_write_bytes(self.root / rel, audio)
                word["audioFile"] = rel
            data["words"].append(word)
            self._write(data)
            return word, True

    def update(self, word_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self.check_ready()
            data = self._read()
            w = self._find(data["words"], word_id)
            if not w:
                raise NotFound("That word was not found. Pull down to refresh.")
            merged = {k: fields.get(k, w.get(k)) for k in ("word", "sounded", "date", "heardBy", "notes")}
            c = self._clean(merged)
            if not c["word"]:
                raise BadRequest("The word can't be empty.")
            w.update(c)
            w["editedAt"] = _now_iso()
            self._rename(w, "audioFile", AUDIO_DIR)
            self._rename(w, "videoFile", VIDEO_DIR)
            self._rename(w, "videoTrimFile", VIDEO_DIR, TRIM_SUFFIX)
            self._write(data)
            return w

    def attach_audio(self, word_id: str, audio: bytes, audio_ext: str = "wav",
                     clip_start: Any = None, clip_end: Any = None) -> dict[str, Any]:
        """Give an existing word its clip (a word written down first, captured later).

        A clip it already had is moved to .trash, never overwritten.
        """
        if not audio:
            raise BadRequest("There's no recording to save.")
        if len(audio) > MAX_AUDIO_BYTES:
            raise BadRequest("That clip is too long. Keep it under a minute.")
        audio_ext = str(audio_ext or "wav").lower()
        if audio_ext not in AUDIO_EXTS:
            audio_ext = "wav"
        with self._lock:
            self.check_ready()
            data = self._read()
            w = self._find(data["words"], word_id)
            if not w:
                raise NotFound("That word was not found. Pull down to refresh.")
            if w.get("audioFile") and (self.root / w["audioFile"]).exists():
                dest = self._trash(w, "replaced-audio")
                shutil.move(str(self.root / w["audioFile"]), str(dest / Path(w["audioFile"]).name))
            rel = self._unique(AUDIO_DIR, file_stem(w), audio_ext)
            self._atomic_write_bytes(self.root / rel, audio)
            w["audioFile"] = rel
            w["clipStart"] = _num(clip_start)
            w["clipEnd"] = _num(clip_end)
            w["capturedAt"] = _now_iso()
            self._write(data)
            return w

    def delete(self, word_id: str) -> str:
        """Move the word's files and its record into .trash. Returns the trash folder."""
        with self._lock:
            self.check_ready()
            data = self._read()
            w = self._find(data["words"], word_id)
            if not w:
                raise NotFound("That word was not found. Pull down to refresh.")
            dest = self._trash(w, "deleted")
            for key in ("audioFile", "videoFile", "videoTrimFile"):
                rel = w.get(key)
                if rel and (self.root / rel).exists():
                    shutil.move(str(self.root / rel), str(dest / Path(rel).name))
            (dest / "word.json").write_text(json.dumps(w, indent=2, ensure_ascii=False), encoding="utf-8")
            data["words"] = [x for x in data["words"] if x.get("id") != word_id]
            self._write(data)
            return str(dest.relative_to(self.root))

    def file_path(self, word_id: str, kind: str) -> Path:
        """kind: 'audio', 'video' (the full original) or 'trim' (the trimmed copy)."""
        key = {"audio": "audioFile", "video": "videoFile", "trim": "videoTrimFile"}.get(kind, "videoFile")
        w = self.get_word(word_id)
        rel = w.get(key) or ""
        if not rel:
            raise NotFound("This word has no recording." if kind == "audio" else "This word has no video.")
        path = self._safe(rel)
        if not path.is_file():
            raise NotFound(f"The file {rel} is missing from the share.")
        return path

    # ------------------------------------------------------------ chunked video upload

    def _partial(self, token: str) -> tuple[Path, Path]:
        if not TOKEN_RE.match(token or ""):
            raise NotFound("That upload has expired. Tap retry.")
        base = self.root / PARTIAL_DIR
        return base / f"{token}.part", base / f"{token}.json"

    def video_start(self, word_id: str, name: str, mime: str, size: int) -> str:
        try:
            size = int(size)
        except (TypeError, ValueError) as err:
            raise BadRequest("Missing the video's size.") from err
        if size <= 0 or size > MAX_VIDEO_BYTES:
            raise BadRequest("That video is too big to keep (4 GB limit).")
        m = re.search(r"\.([A-Za-z0-9]{2,4})$", str(name or ""))
        ext = m.group(1).lower() if m else ""
        if ext not in VIDEO_EXTS:
            ext = "mov" if "quicktime" in str(mime) else "mp4"
        self.get_word(word_id)
        token = uuid.uuid4().hex
        part, meta = self._partial(token)
        with self._lock:
            part.touch()
            meta.write_text(json.dumps({"wordId": word_id, "size": size, "ext": ext,
                                        "startedAt": _now_iso()}), encoding="utf-8")
        return token

    def discard_partial(self, path: Path) -> None:
        """Remove our own temp file (an unfinished trim). Only inside video/.partial."""
        p = Path(path)
        if p.parent.resolve() == (self.root / PARTIAL_DIR).resolve() and p.name.startswith("trim-") and p.exists():
            p.unlink()

    def video_received(self, token: str) -> int:
        part, meta = self._partial(token)
        if not meta.exists():
            raise NotFound("That upload has expired. Tap retry.")
        return part.stat().st_size if part.exists() else 0

    def video_chunk(self, token: str, offset: int, chunk: bytes) -> int:
        """Append one chunk. The offset must equal what has already arrived."""
        self.check_ready()
        part, meta = self._partial(token)
        if len(chunk) > MAX_CHUNK_BYTES:
            raise BadRequest("Chunk too large.")
        with self._lock:
            if not meta.exists():
                raise NotFound("That upload has expired. Tap retry.")
            info = json.loads(meta.read_text(encoding="utf-8"))
            have = part.stat().st_size if part.exists() else 0
            if offset != have:
                raise Conflict("Out of step; resuming.", have)
            if have + len(chunk) > info["size"]:
                raise BadRequest("More data than the video's size.")
            with open(part, "ab") as fh:
                fh.write(chunk)
                fh.flush()
                os.fsync(fh.fileno())
            return have + len(chunk)

    def video_finish(self, token: str) -> dict[str, Any]:
        self.check_ready()
        part, meta = self._partial(token)
        with self._lock:
            if not meta.exists():
                raise NotFound("That upload has expired. Tap retry.")
            info = json.loads(meta.read_text(encoding="utf-8"))
            have = part.stat().st_size if part.exists() else 0
            if have != info["size"]:
                raise Conflict(f"The video is incomplete ({have} of {info['size']} bytes).", have)
            data = self._read()
            w = self._find(data["words"], info["wordId"])
            if not w:
                raise NotFound("The word was deleted before its video finished.")
            if (w.get("videoFile") and (self.root / w["videoFile"]).exists()) or w.get("videoTrimFile"):
                dest = self._trash(w, "replaced-video")
                for key in ("videoFile", "videoTrimFile"):  # a trim belongs to the video it was cut from
                    if w.get(key) and (self.root / w[key]).exists():
                        shutil.move(str(self.root / w[key]), str(dest / Path(w[key]).name))
                for key in ("videoTrimFile", "videoTrimStart", "videoTrimEnd"):
                    w.pop(key, None)
            rel = self._unique(VIDEO_DIR, file_stem(w), info["ext"])
            os.replace(part, self.root / rel)
            meta.unlink()
            w["videoFile"] = rel
            self._write(data)
            return w

    # ------------------------------------------------------------ editing a saved video

    def remove_video(self, word_id: str) -> dict[str, Any]:
        """Detach the video (and any trimmed copy) from a word: both go to .trash."""
        with self._lock:
            self.check_ready()
            data = self._read()
            w = self._find(data["words"], word_id)
            if not w:
                raise NotFound("That word was not found. Pull down to refresh.")
            if not w.get("videoFile") and not w.get("videoTrimFile"):
                raise NotFound("This word has no video.")
            dest = self._trash(w, "removed-video")
            for key in ("videoFile", "videoTrimFile"):
                if w.get(key) and (self.root / w[key]).exists():
                    shutil.move(str(self.root / w[key]), str(dest / Path(w[key]).name))
            w["videoFile"] = ""
            for key in ("videoTrimFile", "videoTrimStart", "videoTrimEnd"):
                w.pop(key, None)
            self._write(data)
            return w

    def trim_job(self, word_id: str, start: Any, end: Any) -> tuple[Path, Path, float, float]:
        """Validate a trim and return (source, temp output, start, end). The cut itself
        (ffmpeg) runs outside the lock; finish_trim() then puts the result in place."""
        s, e = _num(start), _num(end)
        if s is None or e is None or s < 0 or e - s < 0.5:
            raise BadRequest("Pick at least half a second of video.")
        src = self.file_path(word_id, "video")
        tmp = self.root / PARTIAL_DIR / f"trim-{uuid.uuid4().hex}.mp4"
        return src, tmp, s, e

    def finish_trim(self, word_id: str, tmp: Path, start: float, end: float, ext: str = "mp4") -> dict[str, Any]:
        """Move a finished cut into video/<stem>_trim.<ext>; an older trim goes to .trash."""
        with self._lock:
            self.check_ready()
            data = self._read()
            w = self._find(data["words"], word_id)
            if not w:
                raise NotFound("The word was deleted while its video was being trimmed.")
            old = w.get("videoTrimFile")
            if old and (self.root / old).exists():
                dest = self._trash(w, "replaced-trim")
                shutil.move(str(self.root / old), str(dest / Path(old).name))
            rel = self._unique(VIDEO_DIR, file_stem(w) + TRIM_SUFFIX, ext)
            os.replace(tmp, self.root / rel)
            w["videoTrimFile"] = rel
            w["videoTrimStart"] = round(start, 2)
            w["videoTrimEnd"] = round(end, 2)
            self._write(data)
            return w

    # ------------------------------------------------------------ exports

    def _export_path(self, name: str) -> Path:
        if not EXPORT_NAME_RE.match(name or ""):
            raise NotFound("No such export.")
        return self.root / EXPORT_DIR / name

    def export_file(self, name: str) -> Path:
        self.check_ready()
        path = self._export_path(name)
        if not path.is_file():
            raise NotFound("No such export.")
        return path

    def export_zip(self) -> str:
        """Zip every clip with a CSV and JSON copy of the log. Returns the file name."""
        with self._lock:
            self.check_ready()
            words = sort_words(self._read()["words"])
            name = f"{self.config.child} First Words backup {self._today().isoformat()}.zip"
            path = self._export_path(name)
            tmp = path.with_name(f".{path.name}.tmp")
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
                for w in words:
                    rel = w.get("audioFile")
                    if rel and (self.root / rel).is_file():
                        zf.write(self.root / rel, rel)
                zf.writestr("first-words.csv", words_csv(words))
                zf.writestr("first-words.json", json.dumps(
                    {"child": self.config.child, "birthday": self.config.birthday,
                     "exportedAt": _now_iso(), "words": words}, indent=2, ensure_ascii=False))
            os.replace(tmp, path)
            return name

    def keepsake(self) -> str:
        """A printable page, oldest word first. Returns the file name."""
        with self._lock:
            self.check_ready()
            words = list(reversed(sort_words(self._read()["words"])))
            name = f"{self.config.child} First Words keepsake.html"
            html = keepsake_html(self.config.child, self.config.birthday, words)
            self._atomic_write_bytes(self._export_path(name), html.encode("utf-8"))
            return name

    # ------------------------------------------------------------ import

    def import_json(self, source: str, clips: str = "") -> dict[str, int]:
        """Import an Apps Script `first-words.json`, or the backup .zip that holds one.

        Apps Script words carry Drive ids (audioId/audioUrl/videoId/videoUrl).
        Clips are matched by file name (`<date>_<slug>.<ext>`) in the zip or in
        `clips` (a folder or another zip). Words whose id already exists are
        skipped, so running the import twice is harmless.
        """
        src = Path(source)
        files: dict[str, Callable[[], bytes]] = {}
        payload: dict[str, Any] | None = None

        def add_zip(zpath: Path) -> None:
            nonlocal payload
            zf = zipfile.ZipFile(zpath)
            for info in zf.infolist():
                base = Path(info.filename).name
                if base == DATA_FILE and payload is None:
                    payload = json.loads(zf.read(info).decode("utf-8"))
                elif not info.is_dir():
                    files.setdefault(base, lambda i=info, z=zf: z.read(i))

        if not src.exists():
            raise NotFound(f"{source} doesn't exist.")
        if zipfile.is_zipfile(src):
            add_zip(src)
        else:
            payload = json.loads(src.read_text(encoding="utf-8"))
        if clips:
            cp = Path(clips)
            if zipfile.is_zipfile(cp):
                add_zip(cp)
            elif cp.is_dir():
                for f in cp.rglob("*"):
                    if f.is_file():
                        files.setdefault(f.name, lambda p=f: p.read_bytes())
        if not payload or not isinstance(payload.get("words"), list):
            raise BadRequest("No first-words.json with a words list was found.")

        counts = {"imported": 0, "skipped": 0, "clips": 0, "missing_clips": 0}
        with self._lock:
            self.check_ready()
            data = self._read()
            for raw in payload["words"]:
                wid = str(raw.get("id") or "")
                if not ID_RE.match(wid):
                    wid = str(uuid.uuid4())
                if self._find(data["words"], wid):
                    counts["skipped"] += 1
                    continue
                c = self._clean(raw)
                if not c["word"]:
                    counts["skipped"] += 1
                    continue
                word: dict[str, Any] = {
                    "id": wid, **c, "addedBy": _txt(raw.get("addedBy"), 40),
                    "audioFile": "", "videoFile": "",
                    "clipStart": _num(raw.get("clipStart")), "clipEnd": _num(raw.get("clipEnd")),
                    "savedAt": str(raw.get("savedAt") or _now_iso()),
                    "importedFrom": "apps-script",
                }
                if raw.get("videoUrl"):
                    word["driveVideoUrl"] = str(raw["videoUrl"])
                had_audio = bool(raw.get("audioId") or raw.get("audioFile"))
                if had_audio:
                    stem = file_stem(word)
                    hit = None
                    wanted = Path(str(raw.get("audioFile") or "")).name
                    if wanted and wanted in files:
                        hit = wanted
                    else:
                        for fname in sorted(files):
                            m = re.match(re.escape(stem) + r"(?: ?\(\d+\)|-\d+)?\.([A-Za-z0-9]{2,4})$", fname)
                            if m and m.group(1).lower() in AUDIO_EXTS:
                                hit = fname
                                break
                    if hit:
                        ext = hit.rsplit(".", 1)[-1].lower()
                        rel = self._unique(AUDIO_DIR, stem, ext)
                        self._atomic_write_bytes(self.root / rel, files[hit]())
                        word["audioFile"] = rel
                        counts["clips"] += 1
                    else:
                        counts["missing_clips"] += 1
                data["words"].append(word)
                counts["imported"] += 1
            if counts["imported"]:
                self._write(data)
        return counts


def sort_words(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(words, key=lambda w: (str(w.get("date", "")) + str(w.get("savedAt", ""))), reverse=True)


def words_csv(words: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    wr = csv.writer(buf, quoting=csv.QUOTE_ALL)
    wr.writerow(CSV_HEADERS)
    for w in words:
        wr.writerow([w.get("id", ""), w.get("word", ""), w.get("sounded", ""), w.get("date", ""),
                     w.get("heardBy", ""), w.get("notes", ""), w.get("addedBy", ""),
                     w.get("audioFile", ""), w.get("videoFile", ""),
                     "" if w.get("clipStart") is None else w["clipStart"],
                     "" if w.get("clipEnd") is None else w["clipEnd"], w.get("savedAt", "")])
    return buf.getvalue()


def _parse(d: str) -> date | None:
    try:
        return date.fromisoformat(d) if DATE_RE.match(d or "") else None
    except ValueError:
        return None


def age_text(birthday: str, on: str) -> str:
    """Same wording as the app: '14 months, 2 weeks', '2 years, 3 months'."""
    b, d = _parse(birthday), _parse(on)
    if not b or not d or d < b:
        return ""
    months = (d.year - b.year) * 12 + (d.month - b.month)
    if d.day < b.day:
        months -= 1
    if months < 1:
        return f"{(d - b).days // 7} weeks"
    y, mo = divmod(b.month - 1 + months, 12)
    try:
        anchor = date(b.year + y, mo + 1, b.day)
    except ValueError:  # e.g. the 31st in a 30-day month: JS rolls over the same way
        anchor = date(b.year + y, mo + 1, 1)
        anchor = date.fromordinal(anchor.toordinal() + b.day - 1)
    weeks = (d - anchor).days // 7
    if months < 24:
        return f"{months} months" + (f", {weeks} week{'s' if weeks != 1 else ''}" if weeks > 0 else "")
    yrs, rem = divmod(months, 12)
    return f"{yrs} years" + (f", {rem} months" if rem else "")


def keepsake_html(child: str, birthday: str, words: list[dict[str, Any]]) -> str:
    rows = []
    for w in words:
        bits = [_parse(w.get("date", "")).strftime("%A, %B %-d, %Y") if _parse(w.get("date", "")) else w.get("date", "")]
        age = age_text(birthday, w.get("date", ""))
        if age:
            bits.append(f"{age} old")
        if w.get("heardBy"):
            bits.append(f"heard by {w['heardBy']}")
        rows.append(
            "<section><h2>" + escape(w.get("word", "")) + "</h2><p class=meta>"
            + escape("  ·  ".join(bits)) + "</p>"
            + (f"<p class=sound>Sounded like “{escape(w['sounded'])}”</p>" if w.get("sounded") else "")
            + (f"<p>{escape(w['notes'])}</p>" if w.get("notes") else "")
            + "</section>"
        )
    n = len(words)
    return (
        "<!doctype html><html lang=en><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{escape(child)}'s First Words</title>"
        "<style>body{font:16px/1.45 Georgia,serif;color:#000;max-width:640px;margin:48px auto;padding:0 24px}"
        "h1{font-size:44px;margin:0}h2{font-size:48px;margin:0 0 4px}section{border-top:2px solid #000;"
        "padding:22px 0;break-inside:avoid}.meta{font-weight:700;margin:0}.sound{font-style:italic}"
        "@media print{body{margin:0 auto}}</style>"
        f"<h1>{escape(child)}'s First Words</h1><p>{n} word{'s' if n != 1 else ''}</p>"
        + "".join(rows) + "</html>"
    )
