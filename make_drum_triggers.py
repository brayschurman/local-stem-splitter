#!/usr/bin/env python3
"""Create MIDI trigger files from separated kick and snare stems."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

import librosa
import numpy as np


TICKS_PER_BEAT = 960
TEMPO_BPM = 120
TEMPO_US_PER_BEAT = round(60_000_000 / TEMPO_BPM)


def write_varlen(value: int) -> bytes:
    buffer = value & 0x7F
    value >>= 7
    while value:
        buffer <<= 8
        buffer |= ((value & 0x7F) | 0x80)
        value >>= 7

    result = bytearray()
    while True:
        result.append(buffer & 0xFF)
        if buffer & 0x80:
            buffer >>= 8
        else:
            break
    return bytes(result)


def seconds_to_ticks(seconds: float) -> int:
    beats = seconds * TEMPO_BPM / 60
    return round(beats * TICKS_PER_BEAT)


def note_events(times: list[float], note: int, velocities: list[int]) -> list[tuple[int, bytes]]:
    events: list[tuple[int, bytes]] = []
    duration_ticks = round(TICKS_PER_BEAT / 8)
    for time_seconds, velocity in zip(times, velocities):
        tick = seconds_to_ticks(time_seconds)
        events.append((tick, bytes([0x90, note, velocity])))
        events.append((tick + duration_ticks, bytes([0x80, note, 0])))
    return events


def write_midi(path: Path, tracks: list[tuple[str, list[tuple[int, bytes]]]]) -> None:
    header = b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), TICKS_PER_BEAT)
    chunks = [header]

    for name, events in tracks:
        raw = bytearray()
        raw += write_varlen(0) + b"\xff\x03" + write_varlen(len(name)) + name.encode()
        raw += write_varlen(0) + b"\xff\x51\x03" + TEMPO_US_PER_BEAT.to_bytes(3, "big")

        last_tick = 0
        for tick, payload in sorted(events, key=lambda item: (item[0], item[1][0] == 0x80)):
            tick = max(tick, last_tick)
            raw += write_varlen(tick - last_tick) + payload
            last_tick = tick

        raw += write_varlen(0) + b"\xff\x2f\x00"
        chunks.append(b"MTrk" + struct.pack(">I", len(raw)) + bytes(raw))

    path.write_bytes(b"".join(chunks))


def detect_hits(path: Path, *, threshold: float, min_gap_ms: float) -> tuple[list[float], list[int]]:
    y, sr = librosa.load(path, sr=None, mono=True)
    y = librosa.util.normalize(y)

    hop_length = 256
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
    if onset_env.size == 0:
        return [], []

    normalized = onset_env / max(float(np.max(onset_env)), 1e-9)
    frames = librosa.util.peak_pick(
        normalized,
        pre_max=3,
        post_max=3,
        pre_avg=12,
        post_avg=12,
        delta=threshold,
        wait=max(1, round((min_gap_ms / 1000) * sr / hop_length)),
    )

    times = librosa.frames_to_time(frames, sr=sr, hop_length=hop_length)
    velocities = [
        int(np.clip(35 + (normalized[frame] * 92), 35, 127))
        for frame in frames
    ]
    return times.tolist(), velocities


def find_stem(stem_dir: Path, stem: str) -> Path:
    matches = sorted(stem_dir.glob(f"*-{stem}.wav"))
    if not matches:
        raise FileNotFoundError(f"No `{stem}` WAV found in {stem_dir}")
    return matches[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create kick/snare MIDI triggers from separated WAV stems.")
    parser.add_argument("stem_dir", type=Path, help="Folder containing numbered kick/snare WAV stems.")
    parser.add_argument("--prefix", default=None, help="Output filename prefix. Defaults to the stem folder name.")
    parser.add_argument("--kick-threshold", type=float, default=0.18)
    parser.add_argument("--snare-threshold", type=float, default=0.16)
    parser.add_argument("--kick-min-gap-ms", type=float, default=75)
    parser.add_argument("--snare-min-gap-ms", type=float, default=90)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stem_dir = args.stem_dir.expanduser().resolve()
    prefix = args.prefix or stem_dir.name

    kick_times, kick_velocities = detect_hits(
        find_stem(stem_dir, "kick"),
        threshold=args.kick_threshold,
        min_gap_ms=args.kick_min_gap_ms,
    )
    snare_times, snare_velocities = detect_hits(
        find_stem(stem_dir, "snare"),
        threshold=args.snare_threshold,
        min_gap_ms=args.snare_min_gap_ms,
    )

    trigger_dir = stem_dir / "midi-triggers"
    trigger_dir.mkdir(exist_ok=True)

    kick_events = note_events(kick_times, 36, kick_velocities)
    snare_events = note_events(snare_times, 38, snare_velocities)

    write_midi(trigger_dir / f"{prefix}-kick-triggers-c1.mid", [("kick C1", kick_events)])
    write_midi(trigger_dir / f"{prefix}-snare-triggers-d1.mid", [("snare D1", snare_events)])
    write_midi(
        trigger_dir / f"{prefix}-kick-snare-triggers.mid",
        [("kick C1", kick_events), ("snare D1", snare_events)],
    )

    print(f"Kick hits: {len(kick_times)}")
    print(f"Snare hits: {len(snare_times)}")
    print(f"MIDI triggers written to: {trigger_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
