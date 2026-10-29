"""Synthesises the sound for the BrandIntro / BrandOutro cards (no samples, so no licences): a warm, business-news sound. A string
ensemble, a piano and a soft timpani, in a bright major key, like the bumper that opens a financial news programme, with nothing
electronic or "techy" in it. Usage: make-brand-sound.py intro|outro out.wav"""

import sys
import wave

import numpy as np

SR = 44100
rng = np.random.default_rng(11)

NOTE = lambda m: 440 * 2 ** ((m - 69) / 12)  # noqa: E731  (MIDI note number to Hz)


def t_(d):
    return np.arange(int(d * SR)) / SR


def fade(y, a=0.01, r=0.1):
    n = len(y)
    na, nr = max(1, int(a * SR)), max(1, int(r * SR))
    e = np.ones(n)
    e[:na] = np.linspace(0, 1, na)
    e[-nr:] = np.minimum(e[-nr:], np.linspace(1, 0, nr))
    return y * e


def lowpass(x, cutoff, order=2):
    """Smooth FFT low-pass (no ringing at the edges: the signal is faded in and out before and after)."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return np.fft.irfft(X / (1 + (f / cutoff) ** (2 * order)), len(x))


def highpass(x, cutoff):
    return x - lowpass(x, cutoff, 1)


def reverb(y, seconds=1.1, wet=0.2):
    """A room: the dry sound plus its own tail (noise that decays), which is what makes synthesised notes sound played in a space."""
    n = int(seconds * SR)
    ir = rng.standard_normal(n) * np.exp(-np.arange(n) / SR * 5.5)
    ir = lowpass(ir, 5500)
    ir /= np.abs(ir).sum() ** 0.5 + 1e-9
    size = len(y) + n
    wet_sig = np.fft.irfft(np.fft.rfft(y, size) * np.fft.rfft(ir, size), size)[: len(y)]
    wet_sig *= np.abs(y).max() / (np.abs(wet_sig).max() + 1e-9)
    return y * (1 - wet) + wet_sig * wet


def piano(midi, d, gain=0.4):
    """A struck string: harmonics that die away faster the higher they are, a touch of detune for body, and a soft hammer."""
    f = NOTE(midi)
    t = t_(d)
    y = np.zeros_like(t)
    for k, amp in enumerate((1.0, 0.55, 0.32, 0.2, 0.12, 0.08, 0.05), start=1):
        stretch = 1 + 0.0004 * k * k  # strings are slightly stiff: upper partials sit a little sharp
        decay = (1.6 + 0.9 * k) * (1.0 if midi < 72 else 1.4)
        y += amp * np.sin(2 * np.pi * f * k * stretch * t) * np.exp(-t * decay)
        y += 0.5 * amp * np.sin(2 * np.pi * f * 1.0015 * k * stretch * t + 0.7) * np.exp(-t * decay)
    n = rng.standard_normal(len(t))
    y += 0.05 * lowpass(n, 1800) * np.exp(-t * 60)  # hammer
    return fade(y, 0.003, min(0.12, d / 2)) * gain / 1.8


def strings(chord, d, gain=0.3, attack=0.35):
    """A section of strings: several players per note, each a little out of tune, bowing in slowly."""
    t = t_(d)
    y = np.zeros_like(t)
    for midi in chord:
        for cents, ph in ((-7, 0.0), (0, 1.3), (6, 2.6), (11, 4.1)):
            f = NOTE(midi) * 2 ** (cents / 1200)
            vib = 1 + 0.0025 * np.sin(2 * np.pi * (5.2 + 0.4 * ph) * t + ph)  # a slow vibrato
            saw = sum(np.sin(2 * np.pi * f * k * vib * t + ph * k) / k for k in range(1, 9))
            y += saw
    y = lowpass(y, 2600)
    y = fade(y, attack, min(0.5, d / 2))
    return y / (np.abs(y).max() + 1e-9) * gain


def timpani(midi=43, gain=0.9):
    """A soft timpani roll-off: the pitch falls a little as it speaks, with a rounded thump and no click."""
    t = t_(1.4)
    f = NOTE(midi) * (1 + 0.35 * np.exp(-t * 25))
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.2)
    y += 0.4 * np.sin(2 * np.pi * np.cumsum(f * 1.5) / SR) * np.exp(-t * 5)
    thump = lowpass(rng.standard_normal(len(t)), 220) * np.exp(-t * 30)
    return fade(y + 1.5 * thump, 0.004, 0.2) * gain


def swell(d, gain=0.25):
    """A soft cymbal swell that rises into a downbeat."""
    n = int(d * SR)
    x = rng.standard_normal(n)
    x = highpass(lowpass(x, 9000), 1800)
    return x / (np.abs(x).max() + 1e-9) * (np.linspace(0, 1, n) ** 2.2) * gain


def shaker(gain=0.07):
    n = int(0.07 * SR)
    x = highpass(rng.standard_normal(n), 5500) * np.exp(-np.arange(n) / SR * 55)
    return x * gain


def mix(total, events):
    out = np.zeros(int(total * SR))
    for at, y in events:
        i = int(at * SR)
        if i >= len(out):
            continue
        out[i : i + len(y)] += y[: len(out) - i]
    return out


# G major, a warm and confident key: I (G), V (D), vi (Em), IV (C)
G, D, EM, C = (43, 50, 55, 59, 62), (38, 50, 54, 57, 62), (40, 52, 55, 59, 64), (36, 48, 52, 55, 60)


def intro():
    """5 s. Strings swell from nothing, a cymbal swell rises, and on the logo the timpani and the full chord land together; a
    rising piano figure finishes the phrase and it settles on a ringing G."""
    ev = [
        (0.0, strings(G, 2.2, 0.22, attack=1.2)),
        (0.0, swell(1.9, 0.22)),
        (1.9, timpani(43, 0.9)),
        (1.9, piano(55, 1.8, 0.5)),
        (1.9, piano(62, 1.8, 0.45)),
        (1.9, piano(67, 1.8, 0.42)),
        (1.9, strings(G, 3.1, 0.3, attack=0.08)),
    ]
    run = [67, 71, 74, 79, 74, 71]  # G B D G D B: an easy rising and falling figure
    for k, m in enumerate(run):
        ev.append((2.15 + k * 0.28, piano(m, 0.9, 0.3)))
    ev += [
        (3.9, piano(79, 1.1, 0.42)),  # the top G rings out
        (3.9, piano(71, 1.1, 0.3)),
        (3.9, strings(D, 1.1, 0.2, attack=0.05)),
    ]
    return mix(5.0, ev)


def outro():
    """6 s. A hopeful progression (G, D, Em, C) under a flowing piano figure, a very soft pulse, and a held final G that rings."""
    beat = 0.5
    chords = [G, D, EM, C]
    ev = []
    for i, ch in enumerate(chords):  # one chord a bar, two beats of 0.75 s
        at = 0.15 + i * 1.35
        ev.append((at, strings(ch, 1.6, 0.22, attack=0.25)))
        notes = [ch[1] + 12, ch[2] + 12, ch[3] + 12, ch[2] + 24 if False else ch[3] + 12, ch[2] + 12, ch[1] + 12]
        for k, m in enumerate(notes[:4]):
            ev.append((at + k * 0.3, piano(m, 0.9, 0.25)))
    ev.append((0.15, timpani(43, 0.55)))
    for k in range(int(4.6 / beat)):  # a barely-there pulse
        if k % 2 == 1:
            ev.append((0.4 + k * beat, shaker(0.07)))
    ev += [
        (4.1, swell(0.8, 0.14)),
        (4.8, strings(G, 1.2, 0.3, attack=0.05)),
        (4.8, timpani(43, 0.6)),
        (4.8, piano(55, 1.2, 0.45)),
        (4.8, piano(67, 1.2, 0.4)),
        (4.8, piano(79, 1.2, 0.38)),
        (4.8, piano(71, 1.2, 0.3)),
    ]
    return mix(6.0, ev)


if __name__ == "__main__":
    kind, path = sys.argv[1], sys.argv[2]
    y = intro() if kind == "intro" else outro()
    y = reverb(y, 1.2, 0.22)
    y = highpass(y, 35)
    k = int(0.3 * SR)
    y[-k:] *= np.linspace(1, 0, k)  # the picture holds to the last frame; only the sound's tail eases out (no click)
    y = np.tanh(y * 1.05)
    y = y / np.abs(y).max() * 0.85
    st = np.stack([y, np.roll(y, 70) * 0.97], axis=1)  # a touch of width
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((st * 32767).astype("<i2").tobytes())
