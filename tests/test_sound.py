import json
import subprocess

import pytest

from omarchy_settings import core, sound


def vol(percent):
    v = round(percent / 100 * sound.NORM)
    return {"front-left": {"value": v}, "front-right": {"value": v}}


SINKS = [{"index": 64, "name": "usb.analog", "description": "USB Audio", "mute": False, "volume": vol(64)},
         {"index": 78, "name": "hdmi", "description": "HDMI [Monitor]", "mute": True, "volume": vol(100),
          "properties": {"object.id": "44"}}]
SOURCES = [{"index": 63, "name": "mic.analog", "description": "Microphone", "mute": False, "volume": vol(71),
            "monitor_of_sink": None},
           {"index": 65, "name": "usb.analog.monitor", "description": "Monitor of USB Audio", "mute": False,
            "volume": vol(100), "monitor_of_sink": None}]
SINK_INPUTS = [
    {"index": 227, "mute": False, "volume": vol(124),
     "properties": {"application.name": "Zen", "media.name": "A video", "application.icon_name": "zen"}},
    {"index": 300, "mute": True, "volume": vol(50),
     "properties": {"application.process.binary": "mpv", "media.name": "Playback"}},
]
SOURCE_OUTPUTS = [
    {"index": 6713, "mute": False, "volume": vol(100),
     "properties": {"application.name": "Chromium input", "media.name": "RecordStream"}},
    {"index": 7000, "mute": False, "volume": vol(100),
     "properties": {"application.name": "Volume Control", "application.id": "org.PulseAudio.pavucontrol"}},
]


@pytest.fixture
def commands(commands):
    """The shared fake, answering pactl with the lists above."""
    commands.answers.update({
        "pactl -f json list sinks": json.dumps(SINKS),
        "pactl -f json list sources": json.dumps(SOURCES),
        "pactl -f json list sink-inputs": json.dumps(SINK_INPUTS),
        "pactl -f json list source-outputs": json.dumps(SOURCE_OUTPUTS),
        "pactl get-default-sink": "usb.analog\n",
        "pactl get-default-source": "mic.analog\n",
    })
    return commands




def test_volume_is_the_channel_average():
    assert sound.volume_of(vol(64)) == 0.64
    assert sound.volume_of({"front-left": {"value": sound.NORM}, "front-right": {"value": 0}}) == 0.5
    assert sound.volume_of({}) == 0.0


def test_snapshot_hides_monitor_sources_and_meters(commands):
    snap = sound.snapshot()
    assert [d.name for d in snap.outputs] == ["usb.analog", "hdmi"]
    assert snap.outputs[1].muted and snap.outputs[0].volume == 0.64
    assert [d.name for d in snap.inputs] == ["mic.analog"]
    assert (snap.default_output, snap.default_input) == ("usb.analog", "mic.analog")
    assert [s.app for s in snap.recording] == ["Chromium input"]


def test_streams_names_and_generic_media(commands):
    zen, mpv = sound.snapshot().playing
    assert (zen.app, zen.media, zen.icon, zen.volume) == ("Zen", "A video", "zen", 1.24)
    assert (mpv.app, mpv.media, mpv.muted) == ("mpv", "", True)  # binary as the name, "Playback" dropped
    assert mpv.icon == "audio-x-generic-symbolic"


def test_bad_json_is_empty(commands):
    commands.answers["pactl -f json list sinks"] = "not json"
    assert sound.snapshot().outputs == []


def test_commands(commands):
    assert sound.set_default("sink", sound.Device(78, "hdmi", "HDMI", 1.0, False))
    assert sound.set_volume("sink-input", 227, 0.8)
    assert sound.set_mute("source", 63, True)
    assert commands.calls == [["pactl", "set-default-sink", "hdmi"], ["pactl", "set-sink-input-volume", "227", "80%"],
                     ["pactl", "set-source-mute", "63", "1"]]


def test_find_test_sound(tmp_path):
    assert sound.find_test_sound(tmp_path) is None
    (tmp_path / "bell.oga").write_bytes(b"")
    (tmp_path / "complete.oga").write_bytes(b"")
    assert sound.find_test_sound(tmp_path) == tmp_path / "bell.oga"


def test_set_default_through_omarchy_moves_the_apps(commands):
    commands.have.add("omarchy-audio-output-set-default")
    hdmi = sound.snapshot().outputs[1]
    assert hdmi.node_id == "44"
    commands.calls.clear()
    assert not sound.set_default("sink", hdmi)  # the command ran but the default is still usb.analog
    commands.answers["pactl get-default-sink"] = "hdmi"
    assert sound.set_default("sink", hdmi)
    assert commands.calls[0] == ["omarchy-audio-output-set-default", "44", "hdmi"]
