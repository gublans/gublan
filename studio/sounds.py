"""soft, built-in sound effects for the studio: opening things, running, finishing, errors and more.

every sound is made here from a few sine (or soft square) waves, so there are no sound files to ship.
the first time a sound plays it is written to a small .wav in the settings folder and reused after that.
"""

import io
import math
import os
import random
import struct
import subprocess
import sys
import threading
import time
import wave

from . import config

RATE = 22050

# what happens -> the notes that play: (frequency, start in seconds, length in seconds, loudness 0-1)
EVENTS = {
    "open": [(660, 0.0, 0.11, 0.8), (880, 0.06, 0.14, 0.7)],
    "close": [(880, 0.0, 0.1, 0.6), (660, 0.05, 0.14, 0.55)],
    "run": [(523.25, 0.0, 0.12, 0.7), (659.25, 0.07, 0.12, 0.7), (783.99, 0.14, 0.22, 0.75)],
    "stop": [(587.33, 0.0, 0.12, 0.6), (440, 0.08, 0.2, 0.55)],
    "done": [(659.25, 0.0, 0.3, 0.45), (783.99, 0.03, 0.3, 0.4), (987.77, 0.07, 0.34, 0.35)],
    "error": [(233.08, 0.0, 0.13, 0.85), (196, 0.11, 0.2, 0.85)],
    "warning": [(440, 0.0, 0.16, 0.6)],
    "save": [(1318.5, 0.0, 0.05, 0.45), (1760, 0.03, 0.07, 0.35)],
    "click": [(1046.5, 0.0, 0.035, 0.35)],
    "notify": [(783.99, 0.0, 0.18, 0.55), (1174.66, 0.05, 0.22, 0.35)],
    "type": [(1600, 0.0, 0.012, 0.18)],
    "pass": [(783.99, 0.0, 0.1, 0.55), (1046.5, 0.06, 0.18, 0.5)],
}

# how each pack shapes a note: (wave, octave shift, attack seconds, how fast it fades, overtone amount)
PACKS = {
    "soft": ("sine", 0, 0.008, 9.0, 0.18),
    "glass": ("sine", 1, 0.002, 7.0, 0.42),
    "wood": ("triangle", -1, 0.001, 22.0, 0.08),
    "retro": ("square", 0, 0.001, 11.0, 0.0),
}

ABOUT = {
    "soft": "gentle round tones. the default.",
    "glass": "bright little bells.",
    "wood": "short knocks, like a wooden xylophone.",
    "retro": "quiet square waves, like an old console.",
}

_settings = {"sounds": True, "sound_volume": 45, "sound_pack": "soft", "typing_sounds": False}
_last = {}
_lock = threading.Lock()
_mixer = {"ready": None}


def configure(settings):
    """read the sound settings (called whenever settings change)."""
    for key in _settings:
        if key in settings:
            _settings[key] = settings[key]


def enabled():
    return bool(_settings.get("sounds"))


def _wave(kind, phase):
    if kind == "square":
        return 1.0 if phase % 1.0 < 0.5 else -1.0
    if kind == "triangle":
        return 4.0 * abs(phase % 1.0 - 0.5) - 1.0
    return math.sin(2 * math.pi * phase)


def render(event, pack="soft", volume=45):
    """the samples for one event as 16-bit mono .wav bytes."""
    notes = EVENTS.get(event)
    if not notes:
        raise KeyError(f"there is no sound called {event}")
    kind, octave, attack, decay, overtone = PACKS.get(pack, PACKS["soft"])
    length = max(start + seconds for _f, start, seconds, _l in notes) + 0.05
    count = int(RATE * length)
    samples = [0.0] * count
    gain = 0.32 * max(0.0, min(1.0, volume / 100.0))
    if kind == "square":
        gain *= 0.45
    for frequency, start, seconds, loudness in notes:
        frequency *= 2.0 ** octave
        first = int(start * RATE)
        last = min(count, first + int((seconds + 0.04) * RATE))
        for index in range(first, last):
            t = (index - first) / RATE
            envelope = min(1.0, t / attack) if attack > 0 else 1.0
            envelope *= math.exp(-decay * t / max(0.05, seconds * 3.0))
            if t > seconds:
                envelope *= max(0.0, 1.0 - (t - seconds) / 0.04)
            value = _wave(kind, frequency * t)
            if overtone:
                value += overtone * math.sin(2 * math.pi * frequency * 2.0 * t) * math.exp(-decay * 2.0 * t)
            samples[index] += value * envelope * loudness
    # notes that overlap add up: scale them back so the loudest moment never clips
    peak = max(1.0, max((abs(value) for value in samples), default=1.0))
    data = bytearray()
    for value in samples:
        data += struct.pack("<h", int(max(-1.0, min(1.0, value / peak)) * gain * 32767))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(bytes(data))
    return buffer.getvalue()


def sounds_folder():
    return os.path.join(config.settings_folder(), "sounds")


def sound_file(event, pack, volume):
    """the cached .wav for an event, made the first time it is needed."""
    volume = int(round(max(0, min(100, volume)) / 5.0) * 5)
    path = os.path.join(sounds_folder(), f"{pack}-{event}-{volume}.wav")
    if not os.path.isfile(path):
        os.makedirs(sounds_folder(), exist_ok=True)
        temporary = f"{path}.{random.randrange(1 << 30)}.tmp"
        with open(temporary, "wb") as handle:
            handle.write(render(event, pack, volume))
        os.replace(temporary, path)
    return path


def _play_file(path):
    if sys.platform == "win32":
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        return
    for command in (["afplay", path], ["paplay", path], ["aplay", "-q", path]):
        try:
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
            return
        except OSError:
            continue


def play(event, force=False):
    """play a sound for something that happened. quiet when sounds are off or the same sound just played."""
    if not force and (not enabled() or (event == "type" and not _settings.get("typing_sounds"))):
        return False
    if event not in EVENTS:
        return False
    now = time.monotonic()
    with _lock:
        if now - _last.get(event, 0.0) < (0.03 if event == "type" else 0.08):
            return False
        _last[event] = now
    pack = str(_settings.get("sound_pack") or "soft")
    volume = int(_settings.get("sound_volume", 45))
    if volume <= 0:
        return False

    def work():
        try:
            _play_file(sound_file(event, pack if pack in PACKS else "soft", volume))
        except Exception:  # noqa: BLE001 - sounds are a nicety; never let them break anything
            pass

    threading.Thread(target=work, daemon=True).start()
    return True


configure(config.load())
