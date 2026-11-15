# First Words

A Home Assistant integration for saving a child's first words. Each entry stores:

- a short audio clip, either recorded live or cut from a video or voice memo
- the word, how it sounded, the date, who heard it, and notes
- optionally, the full original video

Everything is saved as **plain files on a network share**: `.wav` clips, the original videos, and one JSON log. You can still read them in twenty years without Home Assistant.

The integration adds a **First Words** item to the sidebar. Every signed-in HA user can use it, admins and non-admins alike, so there are no PINs or extra accounts. Home Assistant's remote access (Nabu Casa, Tailscale and so on) makes it work away from home too.

## Install

1. Mount a network share in Home Assistant under **Settings → System → Storage → Add network storage** and set **Usage** to **Media**. A share named `FirstWords` appears at `/media/FirstWords`.
2. In HACS, add this repository as a custom repository (type: Integration), install **First Words**, then restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → First Words** and fill in:
   - **Child's name** and **birthday** (the birthday turns on the age line for each word)
   - **People**, one per line as `Name: label`, for example `Alex: Mama`. The name is matched against each person's HA user name and picks the default for "Who heard it".
   - **Mounted share**, for example `/media/FirstWords`. Setup refuses a path that isn't a live mount.

## On the share

```
First Words/
  first-words.json                    the log; rewritten atomically on every change
  audio/2026-11-12_ball.wav           one clip per word (16-bit mono WAV, 12 ms fades)
  video/2026-11-12_ball.mov           optional full videos
  history/first-words-YYYY-MM-DD.json one snapshot per day, never pruned
  .trash/<when>_<id>_deleted/         deleted words: their files plus word.json
  exports/                            backup zips and the printable keepsake
```

**Nothing is ever hard-deleted.** Deleting a word moves its files into `.trash`. If the share isn't mounted, every save is refused and the app says why, so nothing ends up on the VM's own disk. Saves made while HA or the NAS is unreachable stay on the phone (IndexedDB) and upload automatically once it's reachable again.

## In Home Assistant

- `sensor.<child>_words`: the word count, with the newest word, its date, who heard it and who added it. When storage is unavailable the sensor goes *unavailable*; it never drops to 0.
- Events `first_words_added`, `first_words_updated` and `first_words_deleted` carry `word`, `date`, `heard_by`, `added_by` and `user_id`. Use them to notify the other parent.
- Services:
  - `first_words.export_zip`
  - `first_words.make_keepsake`
  - `first_words.import_json`, which imports the Apps Script version's `first-words.json` or the backup `.zip` that contains it. It's safe to run twice.

## Offsite backup

Copy the share somewhere else, and **copy, don't sync**, so a delete on the NAS can never delete the offsite copy. For example, a nightly Unraid User Script:

```
rclone copy "/mnt/user/FirstWords/First Words" "gdrive:First Words (NAS mirror)" --create-empty-src-dirs
```

## Development

- `tests/`: storage tests. Plain pytest, no Home Assistant needed: `pytest tests`.
- `dev/server.py`: runs the real `api.py` and `store.py` behind small HA stubs, and serves the panel at `/`.
- `dev/ui_test.py`: drives the panel in headless Chromium at phone size. It covers recording-free flows, video trim, chunked video upload, edit, delete, exports, the offline queue and the not-mounted state. Needs `playwright`, `aiohttp` and `imageio-ffmpeg`.

The panel is a single plain web component with no build step.
