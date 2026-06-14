# EditMyRaw

Gemini-guided RAW/JPG editing for Sony `.ARW` and regular images. Edit from an
**example** image, a **prompt**, or a **combination** of both — one image or a whole
batch — and (optionally) make a batch look **consistent** with a hidden AI sparring loop.

## Workflows

| Workflow | What you give | What happens |
|---|---|---|
| **Prompt** | a text description | Gemini returns a bounded edit recipe, applied locally |
| **Example** | a reference image | builds a skin-weighted look profile, matches targets to it |
| **Combination** | example + prompt | "use this mood, but brighter" — both at once |

Two quality modes:
- **Faithful** — non-generative. Gemini analyzes previews and returns a JSON recipe;
  local code applies tone, color, geometry/proportion, and look-matching.
- **Creative** — stronger corrections, and may optionally ask a Gemini image model to
  produce a generated edit (use when the saved look matters more than pixel fidelity).

Extra: **batch consistency** — after editing a set, a hidden multi-round critic nudges
the whole batch toward one uniform look (great for marketplace or dating-profile sets).
Skin/face weighting keeps skin tones matched. Exports JPEG or 16-bit TIFF, plus a ZIP for batches.

## API key (stored locally, never committed)

There is **no hardcoded key**. Set it once in the GUI (**API key & models** panel):
you paste the key, click **Save**, and it is written to `~/.editmyraw/config.json`
(permissions `600`) — outside this repo. The panel always shows a **masked** view of the
active key and where it came from. You can **Test** or **Clear** it any time.

Resolution order: GUI-saved key → `GEMINI_API_KEY` environment variable → none.

> If a key was ever shared in chat or logs, rotate it in Google AI Studio.

## Quick install (one line — for anyone)

Fetches a managed Python and all dependencies (~200 MB, one time) and puts a
launcher on your Desktop. No pre-installed Python needed (uses [uv](https://docs.astral.sh/uv/)).

**macOS** — in Terminal:
```bash
curl -fsSL https://raw.githubusercontent.com/jyharju-code/EditMyRaw/main/install.sh | bash
```

**Windows** — in PowerShell:
```powershell
irm https://raw.githubusercontent.com/jyharju-code/EditMyRaw/main/install.ps1 | iex
```

Then double-click the launcher and add a free [Gemini API key](https://aistudio.google.com/apikey)
in the app's settings panel. To update later, run the same line again.

## Standalone apps (no Terminal)

Prefer a double-click app? Grab the build for your platform from the
[latest release](https://github.com/jyharju-code/EditMyRaw/releases/latest):

- `EditMyRaw-macOS-AppleSilicon.zip` — Apple Silicon Macs
- `EditMyRaw-macOS-Intel.zip` — Intel Macs
- `EditMyRaw-Windows.zip` — Windows 10/11

Unzip and run. First launch is unsigned, so the OS warns once: macOS → right-click →
**Open**; Windows → "More info" → **Run anyway**. These are built automatically for every
release by GitHub Actions (`.github/workflows/build.yml`); build locally on macOS with
`./build_app.sh`.

## Install from source (developers)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Run the GUI

```bash
editmyraw-web          # or: python -m editmyraw.cli web
```

Opens `http://127.0.0.1:<free-port>/` in your browser. Pick targets/reference with native
macOS dialogs (big RAW files are read straight from disk — nothing is uploaded).

## CLI

```bash
# Prompt edit, batch:
editmyraw edit --inputs ./raws --workflow prompt --mode faithful \
  --prompt "Warm cinematic edit, keep skin natural." --out exports

# Match a folder to an example, skin-weighted, consistent set:
editmyraw edit --inputs ./raws --reference look.jpg --workflow example --out exports

# Combination + 16-bit TIFF:
editmyraw edit --inputs ./raws --reference look.jpg --workflow combo \
  --prompt "use the example mood but a touch brighter" --format tiff --out exports

# Local dry run (no Gemini):
editmyraw edit --inputs ./raws --reference look.jpg --workflow example --dry-run

# Key:
editmyraw key --set "AIza..."     # save locally
editmyraw key --show              # masked status
editmyraw key --clear
```

## How it works

1. RAW is rendered with `rawpy`/LibRaw to an RGB working image (JPEG/PNG load directly).
2. Example → a **skin-weighted** look profile (Lab mean/std + luma histogram + saturation).
3. Prompt/combo → a small preview goes to Gemini with a strict JSON schema.
4. Gemini returns a **bounded** recipe (tone + geometry/proportion + crop + optional creative).
5. Local edits via OpenCV/Pillow: look matching, exposure/contrast/highlights/shadows/
   temperature/tint/clarity/vignette, lens & perspective correction, feathered subject/face
   scaling, crop/aspect.
6. Optional hidden batch-consistency sparring nudges the whole set to a uniform look.
7. Export JPEG / 16-bit TIFF (+ ZIP for batches).

Gemini is treated as an **advisor**, not an unchecked editor: every value it returns is
clamped to safe ranges per mode.

## Layout

```
src/editmyraw/
  config.py     secure local API-key store (GUI-managed)
  raw_io.py     load RAW/JPG, previews, export JPEG/TIFF
  skin.py       face/skin weight maps
  style.py      reference look profile + skin-weighted transfer
  recipe.py     bounded edit recipe (pydantic)
  geometry.py   proportion/geometry corrections
  tone.py       tonal/color adjustments
  gemini.py     Gemini client (recipe, generative, consistency critic)
  pipeline.py   orchestration + batch consistency + ZIP
  server.py     Flask browser GUI
  cli.py        command line
  web/          GUI (index.html, app.js, styles.css)
```
