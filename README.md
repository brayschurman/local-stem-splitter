# Local Stem Splitter

Local stem separation for Apple Silicon Macs. Give Codex a YouTube link or a
local audio file, and it can run this repo to produce cleanly named stems for a
DAW session.

The default split uses Demucs `htdemucs_ft` for broad stems:

- `vocals`
- `drums`
- `bass`
- `other`

It also writes an `instrumental` stem and, by default, tries to split `drums`
into drum sub-stems:

- `kick`
- `snare`
- `toms`
- `hh`
- `ride`
- `crash`

## Workflow

The intended day-to-day flow is simple:

1. Give Codex either a YouTube link or a path to a local audio file.
2. Codex downloads the YouTube audio when needed, or uses the local file as-is.
3. Codex runs `split_stems.py` in the local virtual environment.
4. Finished stems land in `~/Music/local-stems/htdemucs_ft/<song-slug>/`.
5. Files are numbered and named in kebab-case so they sort correctly when
   dragged into Logic, Ableton, Pro Tools, or another DAW.

Example prompt:

```text
Split this into stems:
https://www.youtube.com/watch?v=...
```

Or:

```text
Split ~/Downloads/song.wav into stems and put them in ~/Downloads/stems
```

## Output Names

Files are named in stable, DAW-friendly order:

```text
00-song-title-instrumental.wav
01-song-title-drums.wav
02-song-title-kick.wav
03-song-title-snare.wav
04-song-title-hh.wav
05-song-title-ride.wav
06-song-title-crash.wav
07-song-title-toms.wav
08-song-title-bass.wav
09-song-title-other.wav
10-song-title-vocals.wav
```

The prefix comes from the source filename. For example, `My Song Final.mp3`
becomes `my-song`, so the stem files are easy to scan and sort.

## Setup

Install dependencies in a local Python 3.12 virtual environment:

```sh
cd ~/local-stem-splitter
python3.12 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

You also need `ffmpeg` available on your `PATH`. On macOS with Homebrew:

```sh
brew install ffmpeg
```

## Split A Local File

```sh
./.venv/bin/python split_stems.py "/path/to/song.mp3"
```

Use a custom output folder:

```sh
./.venv/bin/python split_stems.py "/path/to/song.mp3" -o ~/Downloads/stems
```

Write MP3 instead of the default 24-bit WAV:

```sh
./.venv/bin/python split_stems.py "/path/to/song.mp3" --format mp3
```

Skip drum sub-stems:

```sh
./.venv/bin/python split_stems.py "/path/to/song.mp3" --no-drum-substems
```

## Split A YouTube Link Manually

Codex can handle this for you, but the manual equivalent is:

```sh
mkdir -p ~/Downloads/stem-sources
./.venv/bin/yt-dlp \
  --extract-audio \
  --audio-format wav \
  --output "$HOME/Downloads/stem-sources/%(title)s.%(ext)s" \
  "https://www.youtube.com/watch?v=..."

./.venv/bin/python split_stems.py "$HOME/Downloads/stem-sources/Song Title.wav"
```

Only download audio you have the right to use.

## MIDI Drum Triggers

After splitting a track with `kick` and `snare` WAV stems, generate MIDI trigger
files:

```sh
./.venv/bin/python make_drum_triggers.py ~/Music/local-stems/htdemucs_ft/song-title
```

This writes:

```text
midi-triggers/song-title-kick-triggers-c1.mid
midi-triggers/song-title-snare-triggers-d1.mid
midi-triggers/song-title-kick-snare-triggers.mid
```

## Notes

- The script prefers Apple Metal/MPS on M-series Macs and falls back to CPU.
- First run downloads the Demucs model weights.
- First granular drum run downloads the DrumSep model to `~/local-stem-splitter/models`.
- `wav24` is the default because it is better for further processing than MP3.
- MP3 can report encoder delay or padding. Use `wav24` or `flac` for DAW/editing alignment.
- Demucs models process at their trained sample rate, so stems may be written at
  44.1 kHz even if the source file was 48 kHz.
