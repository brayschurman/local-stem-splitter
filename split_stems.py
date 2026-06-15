#!/usr/bin/env python3
"""Local stem splitting wrapper for Apple Silicon Macs."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
VENV_PYTHON = PROJECT_DIR / ".venv" / "bin" / "python"
VENV_AUDIO_SEPARATOR = PROJECT_DIR / ".venv" / "bin" / "audio-separator"
MODEL_DIR = PROJECT_DIR / "models"
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"


STEM_ORDER = [
    "instrumental",
    "drums",
    "kick",
    "snare",
    "hh",
    "ride",
    "crash",
    "toms",
    "bass",
    "other",
    "vocals",
    "guitar",
    "piano",
]


def default_device() -> str:
    try:
        import torch

        if torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def run(command: list[str]) -> None:
    print("+ " + " ".join(command))
    subprocess.run(command, check=True)


def kebab(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def song_slug(input_path: Path) -> str:
    words = re.findall(r"[A-Za-z0-9]+", input_path.stem.lower())
    skip = {"a", "an", "and", "the", "first", "song", "track", "full", "lp", "ep"}
    useful = [word for word in words if word not in skip]
    return kebab("-".join((useful or words or ["song"])[:2]))


def extension_for(args: argparse.Namespace) -> str:
    if args.format == "flac":
        return "flac"
    if args.format == "mp3":
        return "mp3"
    return "wav"


def demucs_track_dir(args: argparse.Namespace) -> Path:
    return args.output_dir / args.model / args.input.stem


def final_track_dir(args: argparse.Namespace) -> Path:
    return args.output_dir / args.model / song_slug(args.input)


def demucs_args(args: argparse.Namespace, output_dir: Path) -> list[str]:
    command = [
        str(VENV_PYTHON if VENV_PYTHON.exists() else sys.executable),
        "-m",
        "demucs",
        "-n",
        args.model,
        "-d",
        args.device,
        "-o",
        str(output_dir),
        "--filename",
        "{track}/{stem}.{ext}",
        "--overlap",
        str(args.overlap),
        "-j",
        str(args.jobs),
    ]

    if args.segment:
        command += ["--segment", str(args.segment)]

    if args.format == "mp3":
        command += ["--mp3", "--mp3-bitrate", str(args.mp3_bitrate)]
    elif args.format == "flac":
        command += ["--flac"]
    elif args.format == "wav24":
        command += ["--int24"]
    elif args.format == "wav32":
        command += ["--float32"]

    command.append(str(args.input))
    return command


def find_stem_file(root: Path, stem: str) -> Path | None:
    matches = sorted(root.glob(f"{stem}.*")) or sorted(root.glob(f"**/{stem}.*"))
    return matches[0] if matches else None


def move_demucs_outputs(args: argparse.Namespace) -> Path:
    source_dir = demucs_track_dir(args)
    target_dir = final_track_dir(args)
    target_dir.mkdir(parents=True, exist_ok=True)

    prefix = song_slug(args.input)
    for source in sorted(source_dir.glob("*")):
        if not source.is_file():
            continue
        stem = source.stem
        target = target_dir / f"{prefix}-{kebab(stem)}{source.suffix.lower()}"
        if target.exists():
            target.unlink()
        source.replace(target)

    if source_dir.exists() and source_dir != target_dir:
        try:
            source_dir.rmdir()
        except OSError:
            pass

    return target_dir


def stem_path(track_dir: Path, args: argparse.Namespace, stem: str) -> Path:
    return track_dir / f"{song_slug(args.input)}-{stem}.{extension_for(args)}"


def stem_name_from_path(path: Path) -> str | None:
    name = path.stem
    if re.match(r"^\d{2}-", name):
        name = name[3:]
    for stem in sorted(STEM_ORDER, key=len, reverse=True):
        if name == stem or name.endswith(f"-{stem}"):
            return stem
    return None


def numbered_stem_name(prefix: str, stem: str, suffix: str) -> str:
    try:
        order = STEM_ORDER.index(stem)
    except ValueError:
        order = len(STEM_ORDER)
    return f"{order:02d}-{prefix}-{stem}{suffix.lower()}"


def apply_numbered_order(track_dir: Path, prefix: str) -> None:
    files = [path for path in track_dir.iterdir() if path.is_file() and path.suffix.lower() in {".wav", ".flac", ".mp3"}]
    planned: list[tuple[Path, Path]] = []

    for path in files:
        stem = stem_name_from_path(path)
        if stem is None:
            continue
        target = path.with_name(numbered_stem_name(prefix, stem, path.suffix))
        if path != target:
            planned.append((path, target))

    temp_pairs: list[tuple[Path, Path]] = []
    for index, (source, target) in enumerate(planned):
        temp = source.with_name(f".rename-{index}-{source.name}")
        source.replace(temp)
        temp_pairs.append((temp, target))

    for temp, target in temp_pairs:
        if target.exists():
            target.unlink()
        temp.replace(target)


def create_instrumental(args: argparse.Namespace, track_dir: Path) -> None:
    if not args.instrumental:
        return

    component_stems = ["drums", "bass", "other", "guitar", "piano"]
    inputs = [stem_path(track_dir, args, stem) for stem in component_stems]
    inputs = [path for path in inputs if path.exists()]

    if len(inputs) < 2:
        print("\nSkipping instrumental: not enough non-vocal stems were found.")
        return

    output = stem_path(track_dir, args, "instrumental")
    if output.exists():
        output.unlink()

    command = [FFMPEG, "-y"]
    for path in inputs:
        command += ["-i", str(path)]

    filter_graph = f"amix=inputs={len(inputs)}:duration=longest:dropout_transition=0:normalize=0"
    command += ["-filter_complex", filter_graph]

    if args.format == "mp3":
        command += ["-codec:a", "libmp3lame", "-b:a", f"{args.mp3_bitrate}k"]
    elif args.format == "flac":
        command += ["-codec:a", "flac"]
    elif args.format == "wav32":
        command += ["-c:a", "pcm_f32le"]
    else:
        command += ["-c:a", "pcm_s24le"]

    command.append(str(output))
    run(command)


def normalize_wav_depth(args: argparse.Namespace, track_dir: Path) -> None:
    if args.format not in {"wav24", "wav32"}:
        return

    codec = "pcm_s24le" if args.format == "wav24" else "pcm_f32le"
    for path in sorted(track_dir.glob("*.wav")):
        temp = path.with_name(f".{path.stem}.tmp.wav")
        command = [FFMPEG, "-y", "-i", str(path), "-c:a", codec, str(temp)]
        run(command)
        temp.replace(path)


def maybe_run_drum_substems(args: argparse.Namespace, track_dir: Path) -> None:
    if not args.drum_substems:
        return

    audio_separator = (
        str(VENV_AUDIO_SEPARATOR)
        if VENV_AUDIO_SEPARATOR.exists()
        else shutil.which("audio-separator")
    )
    if not audio_separator:
        print(
            "\nDrum sub-stems were requested, but `audio-separator` is not installed.\n"
            "The broad `drums` stem was created. Install a local DrumSep-capable "
            "separator/model, then rerun with `--drum-substems`."
        )
        return

    drums = stem_path(track_dir, args, "drums")
    if not drums.exists():
        drums = find_stem_file(track_dir, "drums")
    if drums is None:
        print("\nCould not find a `drums` stem to split further.")
        return

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        audio_separator,
        str(drums),
        "--output_dir",
        str(track_dir),
        "--model_file_dir",
        str(MODEL_DIR),
        "--model_filename",
        args.drum_model,
    ]
    if args.format == "mp3":
        command += ["--output_format", "MP3", "--output_bitrate", f"{args.mp3_bitrate}k"]
    elif args.format == "flac":
        command += ["--output_format", "FLAC"]
    else:
        command += ["--output_format", "WAV"]
    run(command)
    rename_drum_outputs(args, track_dir)


def rename_drum_outputs(args: argparse.Namespace, track_dir: Path) -> None:
    prefix = song_slug(args.input)
    for path in sorted(track_dir.glob("*DrumSep*")):
        if not path.is_file():
            continue
        match = re.search(r"_\(([^)]+)\)_", path.name)
        if not match:
            continue
        stem = kebab(match.group(1))
        target = track_dir / f"{prefix}-{stem}{path.suffix.lower()}"
        if target.exists():
            target.unlink()
        path.replace(target)


def print_timing_note(args: argparse.Namespace) -> None:
    if args.format == "mp3":
        print(
            "\nTiming note: MP3 files can report encoder delay/padding. "
            "Use `--format wav24` or `--format flac` for DAW/editing alignment."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Split an audio file into local stems using Demucs."
    )
    parser.add_argument("input", type=Path, help="Input audio file.")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path.home() / "Music" / "local-stems",
        help="Output folder. Default: ~/Music/local-stems",
    )
    parser.add_argument(
        "-m",
        "--model",
        default="htdemucs_ft",
        help="Demucs model. Default: `htdemucs_ft` for higher-quality vocals/drums/bass/other.",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["wav", "wav24", "wav32", "flac", "mp3"],
        default="mp3",
        help="Output format. Default: mp3.",
    )
    parser.add_argument(
        "--device",
        default=default_device(),
        choices=["mps", "cpu"],
        help="Processing device. Default prefers Apple Metal when available.",
    )
    parser.add_argument("--jobs", type=int, default=max(1, min(4, os.cpu_count() or 1)))
    parser.add_argument("--segment", type=int, default=7)
    parser.add_argument("--overlap", type=float, default=0.25)
    parser.add_argument("--mp3-bitrate", type=int, default=320)
    parser.add_argument(
        "--instrumental",
        action="store_true",
        help="Create an instrumental mix from the available non-vocal stems.",
    )
    parser.add_argument(
        "--drum-substems",
        action="store_true",
        help="After broad splitting, run an installed DrumSep-capable audio-separator model.",
    )
    parser.add_argument(
        "--drum-model",
        default="MDX23C-DrumSep-aufr33-jarredou.ckpt",
        help="audio-separator model filename to use for drum sub-stems.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.input = args.input.expanduser().resolve()
    args.output_dir = args.output_dir.expanduser().resolve()

    if not args.input.exists():
        print(f"Input file does not exist: {args.input}", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    run(demucs_args(args, args.output_dir))

    track_dir = move_demucs_outputs(args)
    create_instrumental(args, track_dir)
    maybe_run_drum_substems(args, track_dir)
    normalize_wav_depth(args, track_dir)
    apply_numbered_order(track_dir, song_slug(args.input))
    print_timing_note(args)

    print(f"\nDone. Stems are under: {track_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
