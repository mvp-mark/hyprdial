"""Sound (no GTK, testable): devices and app streams read from `pactl -f json`, and the commands that change them."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import core

NORM = 65536  # pactl volume value for 100%
LIST_NAMES = {"sink": "sinks", "source": "sources", "sink-input": "sink-inputs", "source-output": "source-outputs"}
METER_APPS = {"org.PulseAudio.pavucontrol"}  # level meters, not apps really recording
SOUND_DIR = Path("/usr/share/sounds/freedesktop/stereo")
TEST_SOUNDS = ("audio-test-signal.oga", "audio-volume-change.oga", "bell.oga", "complete.oga")


@dataclass
class Device:
    index: int
    name: str
    description: str
    volume: float  # 1.0 = 100%
    muted: bool
    node_id: str = ""  # PipeWire id (wpctl's), not the same as pactl's index


@dataclass
class Stream:
    index: int
    app: str
    media: str
    icon: str
    volume: float
    muted: bool


@dataclass
class Snapshot:
    outputs: list[Device]
    inputs: list[Device]
    default_output: str
    default_input: str
    playing: list[Stream]
    recording: list[Stream]


def volume_of(volume: dict) -> float:
    """Average of the channels, as a fraction (1.0 = 100%)."""
    values = [ch.get("value", 0) for ch in volume.values() if isinstance(ch, dict)]
    return round(sum(values) / len(values) / NORM, 2) if values else 0.0


def _list(kind: str) -> list[dict]:
    try:
        data = json.loads(core.out(["pactl", "-f", "json", "list", LIST_NAMES[kind]]) or "[]")
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def is_monitor(source: dict) -> bool:
    """Sources that only echo an output: confusing next to the real microphones."""
    return source.get("monitor_of_sink") not in (None, "", "n/a") or str(source.get("name", "")).endswith(".monitor")


def parse_devices(data: list[dict]) -> list[Device]:
    return [Device(d["index"], d.get("name", ""), d.get("description") or d.get("name", ""),
                   volume_of(d.get("volume", {})), bool(d.get("mute")),
                   str(d.get("properties", {}).get("object.id", "")))
            for d in data if "index" in d and not is_monitor(d)]


def parse_streams(data: list[dict]) -> list[Stream]:
    streams = []
    for s in data:
        props = s.get("properties", {})
        if "index" not in s or props.get("application.id") in METER_APPS:
            continue
        app = props.get("application.name") or props.get("application.process.binary") or props.get("media.name", "")
        media = props.get("media.name", "")
        if media in (app, "Playback", "RecordStream", "playback", "Playback Stream", "Record Stream"):
            media = ""  # generic names add nothing
        icon = props.get("application.icon_name") or "audio-x-generic-symbolic"
        streams.append(Stream(s["index"], app, media, icon, volume_of(s.get("volume", {})), bool(s.get("mute"))))
    return streams


def snapshot() -> Snapshot:
    return Snapshot(parse_devices(_list("sink")), parse_devices(_list("source")),
                    core.out(["pactl", "get-default-sink"]), core.out(["pactl", "get-default-source"]),
                    parse_streams(_list("sink-input")), parse_streams(_list("source-output")))


def ok(r) -> bool:
    return r is not None and r.returncode == 0


SET_DEFAULT = {"sink": "omarchy-audio-output-set-default", "source": "omarchy-audio-input-set-default"}


def set_default(kind: str, device: Device) -> bool:
    """Omarchy's command also moves the apps playing (or recording) to the new device; pactl alone doesn't."""
    command = SET_DEFAULT[kind]
    if device.node_id and core.have(command):
        core.run([command, device.node_id, device.name])  # always exits 0: check the result below
        return core.out(["pactl", f"get-default-{kind}"]) == device.name
    return ok(core.run(["pactl", f"set-default-{kind}", device.name]))


def set_volume(kind: str, index: int, fraction: float) -> bool:
    return ok(core.run(["pactl", f"set-{kind}-volume", str(index), f"{round(fraction * 100)}%"]))


def set_mute(kind: str, index: int, on: bool) -> bool:
    return ok(core.run(["pactl", f"set-{kind}-mute", str(index), "1" if on else "0"]))


def find_test_sound(directory: Path = SOUND_DIR) -> Path | None:
    return next((directory / n for n in TEST_SOUNDS if (directory / n).is_file()), None)


def play(path: Path) -> bool:
    """Plays on the default output (pw-play waits until the sound ends)."""
    return ok(core.run(["pw-play", str(path)], timeout=15))
