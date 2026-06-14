# Local Stem Splitter

Local stem separation for Apple Silicon Macs. This uses Demucs in a Python 3.12
virtual environment and defaults to the higher-quality `htdemucs_ft` model, which
produces:

- `vocals`
- `drums`
- `bass`
- `other`

## Usage

Install dependencies in a local virtual environment:

```sh
python3.12 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

```sh
cd ~/local-stem-splitter
./.venv/bin/python split_stems.py "/path/to/song.mp3"
```

Outputs go to `~/Music/local-stems/htdemucs_6s/<song-slug>/`.

Files are named in ordered kebab-case for drag-and-drop into a DAW:

```text
00-song-title-instrumental.wav
01-song-title-drums.wav
02-song-title-kick.wav
03-song-title-snare.wav
08-song-title-bass.wav
09-song-title-other.wav
10-song-title-vocals.wav
```

For MP3 output:

```sh
./.venv/bin/python split_stems.py "/path/to/song.mp3" --format mp3
```

For a custom folder:

```sh
./.venv/bin/python split_stems.py "/path/to/song.mp3" -o ~/Downloads/stems
```

## Notes

- The script prefers Apple Metal/MPS on M-series Macs and falls back to CPU.
- First run downloads the Demucs model weights.
- First granular drum run downloads the DrumSep model to `~/local-stem-splitter/models`.
- `wav24` is the default because it is better for further processing than MP3.
- Granular drum sub-stems are available with `--drum-substems` and use
  `MDX23C-DrumSep-aufr33-jarredou.ckpt` by default.

## Broad Stems Plus Drum Sub-Stems

```sh
./.venv/bin/python split_stems.py "/path/to/song.mp3" --drum-substems
```

This produces the broad quality stems, writes an `instrumental` stem, then splits
`drums` into the same folder. Drum sub-stems are enabled by default; pass
`--no-drum-substems` to skip them.

- `kick`
- `snare`
- `toms`
- `hh`
- `ride`
- `crash`

## Installed Environment

The project venv lives at:

```sh
~/local-stem-splitter/.venv
```

Demucs is installed there, leaving system Python alone.

## Timing And Format

Use `wav24` or `flac` for DAW/editing work. MP3 adds encoder delay/padding and
may report small start-time or duration offsets even when the audio content is
aligned. Demucs models process at their trained sample rate, so stems may be
written at 44.1 kHz even if the source file was 48 kHz.
