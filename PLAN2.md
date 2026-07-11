# PLAN2 — Independent Analysis of the Current Repo

This is a from-scratch read of the actual code, config, and environment as
they exist today (not a revision of `PLAN.md`). Goal: answer "will this
work as-is?" and propose concrete fixes. Written by inspecting every
module in `02-scripts/`, running the test suite, and probing the live
environment on this Pi (dependency resolution, venv contents, apt
packages). `main.py` was **not** executed — it runs an infinite loop that
claims the camera exclusively and can send a real email, so that needs a
deliberate, supervised manual test rather than an unattended one.

---

## Bottom line

The module-level logic (config, storage, notifier, motion detector) is
sound and is proven by 27 passing unit tests. But there is **one
environment-level blocker** and **one behavioral bug** that will each
stop this from working correctly the first time it's run for real on
hardware. Everything else below is a smaller correctness or hygiene gap.

---

## Critical — will prevent it from running at all

### 1. The project's `.venv` cannot see `picamera2`

`picamera2` is correctly installed via apt (`dpkg -l` confirms
`python3-picamera2 0.3.36-1`), and the *system* Python
(`/usr/bin/python3`) can import it fine. But the project's `uv`-managed
`.venv` was created with `include-system-site-packages = false`
(confirmed in `.venv/pyvenv.cfg`), which isolates it from
`/usr/lib/python3/dist-packages` where apt puts `picamera2`. I verified
this live:

```
/usr/bin/python3 -c "import picamera2"        # OK
.venv/bin/python -c "import picamera2"        # ModuleNotFoundError
```

So `uv run python 02-scripts/main.py` (the natural way to launch this
project) will fail on `import camera` the moment it hits
`from picamera2 import Picamera2`, despite every setup step in
`PROGRESS.md`'s hardware checklist having been followed correctly. This
isn't a missing step — it's that `uv sync` and apt-installed system
packages are isolated from each other by default.

**Proposal:** recreate the venv with system site-package access:
```bash
uv venv --system-site-packages
uv sync
```
Then verify with `uv run python -c "import picamera2, cv2, dotenv"`
before relying on it. Document this explicitly in `PROGRESS.md`'s
hardware checklist — right now it just says `uv sync` with no mention
of this isolation, which will bite the next person who sets this up on
a fresh Pi.

---

### 2. Motion cooldown is reused as the recording-continue signal — recordings will be hard-capped at ~5 seconds

`motion_detector.detect()` returns `True` **at most once per
`MOTION_COOLDOWN_SEC` (10s)**, even while real motion is continuously
present in frame — the cooldown suppresses the return value, not just a
side effect:

```python
if motion_detected and (now - _last_motion) > config.MOTION_COOLDOWN_SEC:
    _last_motion = now
    return True, frame
return False, frame          # <- also hit while motion is still ongoing
```

`main.py` uses that same return value to decide whether to keep
recording:

```python
if motion and not currently_recording:
    ... start recording ...
if not motion and currently_recording:
    time.sleep(config.POST_MOTION_BUFFER_SEC)
    camera.stop_recording()
```

Trace through an actual event: a person walks into frame and lingers
for 30 seconds.
- Frame 1: real motion → `detect()` returns `True` → recording starts.
- Frame 2 (fraction of a second later): the person is still there, so
  there *is* motion, but cooldown hasn't elapsed → `detect()` returns
  `False`. `main.py` sees `not motion and currently_recording` → sleeps
  `POST_MOTION_BUFFER_SEC` (5s) and **stops the recording** — while the
  person is still standing right there.
- No new recording can start again until 10s after the first trigger,
  so several seconds of the event go completely uncaptured.

Net effect: every clip is a fixed ~5 seconds long regardless of how long
the actual motion lasts, with blind gaps in between. For a security
camera this is the difference between "captured the intruder" and
"captured five seconds and missed the rest."

**Root cause:** one boolean is being used for two different jobs —
"should we allow a new *event/notification* to fire" (should be
cooldown-gated) vs. "is there motion in frame right now" (should be
raw, every frame, for the recording loop to key off of).

**Proposal:** split these two concerns. For example, have `detect()`
return the raw per-frame boolean, and track the cooldown separately —
only for gating *new notifications*, not for gating whether the
recording keeps running:

```python
def detect(frame):
    ...
    return motion_detected, frame        # raw signal, no cooldown here

def should_notify():                     # separate helper, or inline in main.py
    global _last_motion
    now = time.time()
    if now - _last_motion > config.MOTION_COOLDOWN_SEC:
        _last_motion = now
        return True
    return False
```

`main.py`'s recording loop would then key off the raw `motion` boolean
(plus perhaps its own "N consecutive no-motion frames" debounce before
stopping), while the notifier's own `NOTIFICATION_COOLDOWN_SEC` already
handles not spamming emails. This also removes the current redundancy
of having two independent 10s/60s cooldowns doing overlapping jobs.

---

## Medium — will run, but not as documented / with silent risk

### 3. `CLIPS_DIR` resolves relative to the current working directory, not the project root — and doesn't match the documented folder

`config.py` sets `CLIPS_DIR = "clips"`, and `storage.py` does
`os.makedirs(config.CLIPS_DIR, exist_ok=True)` with that relative path.
Whatever directory you happen to run the script from becomes the parent
of `clips/`. Meanwhile `PROGRESS.md`'s project structure documents
`00-clips/` as "where recorded video and snapshots are saved" — but
no code ever references `00-clips`. This isn't hypothetical: there is
already a stray, empty top-level `clips/` directory in the repo right
now (alongside the actually-tracked `00-clips/.gitkeep` and
`00-clips/placeholder`) — almost certainly created by an earlier test
run or `import storage`, from the repo root.

**Proposal:** anchor `CLIPS_DIR` to the project root regardless of CWD,
e.g. in `config.py`:
```python
BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIPS_DIR = os.path.join(BASE_DIR, "00-clips")
```
and delete the dead top-level `clips/` directory. Pick one name
(`00-clips` fits the numbered-folder convention already used
elsewhere) and make the code and docs agree.

### 4. `.gitignore` doesn't actually exclude the clips output directory

`PROGRESS.md` explicitly claims `.gitignore` "Excludes `.env` and
`clips/` from version control," but `.gitignore` has no `clips/` (or
`00-clips/`) entry at all — only `.env` is excluded. Once `main.py` runs
for real, every `.mp4` and `.jpg` it writes is untracked-but-not-ignored,
one `git add -A` away from getting committed as binary bloat.

**Proposal:** add the real clips directory to `.gitignore` once #3 is
resolved (e.g. `00-clips/*` with a `!00-clips/.gitkeep` exception).

### 5. `requirements.txt` contradicts `pyproject.toml`'s own instructions

`pyproject.toml` has an explicit comment: *"picamera2 is installed via
apt... Do not add it here — pip/uv cannot install it correctly on Pi."*
But `01-reqs/requirements.txt` lists `picamera2` as a plain pip
dependency. Anyone following the `requirements.txt` fallback path
(`pip install -r requirements.txt`, mentioned in `PROGRESS.md` as an
alternative to `uv sync`) will either get a broken PyPI `picamera2`
wheel (no libcamera bindings) or a confusing failure.

**Proposal:** remove `picamera2` from `requirements.txt`, or replace it
with a comment pointing to the apt install command, matching
`pyproject.toml`.

---

## Low — cosmetic / dead config / polish

- **`config.FPS` is defined but never used.** `camera.py`'s
  `create_video_configuration` never passes a `controls={"FrameRate": ...}`
  (or equivalent), so this setting currently does nothing. Either wire
  it up or drop it so it doesn't imply control that isn't there.
- **Email attachment filename includes the directory.** `notifier.py`
  sets `Content-Disposition` filename to the full `snapshot_path`
  (e.g. `clips/snapshot_2026-...jpg`) instead of
  `os.path.basename(snapshot_path)` — cosmetic, but the attachment will
  show up in Gmail named with a stray `clips` prefix.
- **`pyproject.toml` packages a directory literally named `02-scripts`
  as the wheel's importable package.** `02-scripts` isn't a valid
  Python identifier (leading digit, hyphen), so `pip install .` would
  produce a package nothing can `import`. Harmless today since nothing
  installs this as a package — everything runs via direct script
  execution — but worth knowing if packaging is ever revisited.
- **32 `ruff` findings** in `02-scripts/`/`03-tests/` (mostly unsorted
  imports, one unused `pytest` import, one over-length line). Run
  `uv run ruff check --fix 02-scripts 03-tests` — 12 are auto-fixable,
  the rest are one-line manual edits.
- **No clip retention / disk space management.** This is meant to run
  unattended long-term; nothing currently caps how much video
  accumulates in the clips folder. Not a correctness bug today, but
  worth a follow-up (e.g. delete oldest clips past a disk-usage
  threshold, or a cron job).
- **No process supervision.** There's no systemd unit (or equivalent)
  to start `main.py` on boot and restart it if it crashes — currently
  it would need to be launched and re-launched by hand.

---

## What was actually verified live (not just read)

| Check | Result |
|---|---|
| `uv run pytest 03-tests/` | 27 passed |
| System `python3` → `import picamera2` | Works (apt package present) |
| Project `.venv` → `import picamera2` | **Fails** (see Critical #1) |
| Project `.venv` → `import cv2`, `import dotenv` | Both work |
| `python3-picamera2` apt package | Installed (`0.3.36-1`) |
| `rpicam-hello` binary present | Yes (camera stack installed) |
| Stray untracked `clips/` dir already present in repo | Yes, confirms #3 |
| `.gitignore` contains `clips` or `00-clips` rule | No — confirms #4 |

## What was **not** verified (needs a supervised manual test, not automated)

- Actually running `main.py` end-to-end on hardware (claims the camera,
  records real video, sends a real email).
- Physical camera module attachment / IR night-vision behavior.
- Real Gmail SMTP send with the credentials currently in `.env`.
- CPU/thermal behavior running MOG2 continuously at full 1920×1080.

---

## Suggested fix order

1. Fix #1 (venv/system-site-packages) — nothing else can be tested on
   real hardware until this is fixed.
2. Fix #2 (recording/cooldown logic) — this is the core "does the
   product actually work as a security camera" bug.
3. Fix #3 + #4 together (clips path + gitignore) — one small, coupled
   change.
4. Fix #5 (requirements.txt) — one-line change.
5. Do a supervised manual test of `main.py` on the Pi with the camera
   attached, confirm a clip records for the actual duration of motion
   and an email arrives.
6. Low-priority cleanup (ruff, FPS, attachment filename, packaging
   name) whenever convenient.