"""Synthesises the sound for the BrandIntro / BrandOutro cards (no samples, no licences): whooshes, impacts, plucks and a short
upbeat bed, timed to the animation. Usage: make-brand-sound.py intro|outro out.wav"""

import sys
import wave

import numpy as np

SR = 44100
rng = np.random.default_rng(7)


def t_(d):
    return np.arange(int(d * SR)) / SR


def env(n, a=0.005, r=0.2):
    e = np.ones(n)
    na, nr = max(1, int(a * SR)), max(1, int(r * SR))
    e[:na] = np.linspace(0, 1, na)
    e[-nr:] = np.minimum(e[-nr:], np.linspace(1, 0, nr))
    return e


def lowpass(x, cutoff):
    """One-pole low-pass; cutoff may be an array (Hz) to sweep it."""
    c = np.broadcast_to(cutoff, x.shape)
    a = 1 - np.exp(-2 * np.pi * c / SR)
    y = np.empty_like(x)
    s = 0.0
    for i in range(len(x)):
        s += a[i] * (x[i] - s)
        y[i] = s
    return y


def whoosh(d, up=True, gain=0.5):
    n = int(d * SR)
    x = rng.standard_normal(n)
    sweep = np.geomspace(300, 7000, n) if up else np.geomspace(7000, 300, n)
    y = lowpass(x, sweep)
    y = y - lowpass(y, 180)  # keep it airy, not boomy
    shape = np.sin(np.linspace(0, np.pi, n)) ** 2
    return y / (np.abs(y).max() + 1e-9) * shape * gain


def tone(freq, d, kind="pluck", gain=0.4):
    t = t_(d)
    if kind == "pluck":
        y = (
            np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(4 * np.pi * freq * t) + 0.15 * np.sin(6 * np.pi * freq * t)
        ) * np.exp(-t * 7)
    elif kind == "bell":
        y = (
            np.sin(2 * np.pi * freq * t)
            + 0.5 * np.sin(2 * np.pi * freq * 2.76 * t)
            + 0.3 * np.sin(2 * np.pi * freq * 5.4 * t)
        ) * np.exp(-t * 3.2)
    elif kind == "bass":
        y = np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(4 * np.pi * freq * t)
        y *= env(len(t), 0.005, 0.08)
    else:  # pad
        y = sum(np.sin(2 * np.pi * freq * k * t + p) for k, p in ((1, 0), (1.005, 1), (2, 2))) / 3
        y *= env(len(t), 0.3, 0.5)
    return y * gain


def kick(gain=0.9):
    t = t_(0.28)
    f = 48 + 120 * np.exp(-t * 28)
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 12)
    return y * gain


def hat(gain=0.18):
    n = int(0.06 * SR)
    x = rng.standard_normal(n)
    return (x - lowpass(x, 5000)) * np.exp(-np.arange(n) / SR * 70) * gain


def impact(gain=0.9):
    t = t_(1.1)
    boom = np.sin(2 * np.pi * (38 + 60 * np.exp(-t * 9)) * t) * np.exp(-t * 4.2)
    n = rng.standard_normal(len(t))
    crack = (n - lowpass(n, 2500)) * np.exp(-t * 22) * 0.5
    return (boom + crack) * gain


def mix(total, events):
    out = np.zeros(int(total * SR))
    for at, y in events:
        i = int(at * SR)
        out[i : i + len(y)] += y[: len(out) - i]
    return out


NOTE = lambda m: 440 * 2 ** ((m - 69) / 12)  # noqa: E731


def intro():
    ev = [(0.0, whoosh(1.0, True, 0.5)), (1.1, impact(0.8)), (1.15, tone(NOTE(84), 0.6, "bell", 0.25))]
    ev += [(1.27, tone(NOTE(72), 0.4, "pluck", 0.35)), (1.53, tone(NOTE(76), 0.4, "pluck", 0.35))]
    ev += [(1.85, whoosh(0.7, True, 0.35))]
    for at, m in ((2.07, 67), (2.31, 71), (2.55, 74)):  # the three words
        ev += [(at, tone(NOTE(m), 0.35, "pluck", 0.3)), (at, hat(0.25))]
    ev += [(2.9, tone(NOTE(79), 1.4, "bell", 0.22)), (4.15, whoosh(0.85, True, 0.6)), (4.85, impact(0.55))]
    return mix(5.0, ev)


def outro():
    beat = 0.5
    ev = [
        (0.15, whoosh(0.7, True, 0.4)),
        (0.5, whoosh(0.7, True, 0.35)),
        (1.0, whoosh(0.5, True, 0.5)),
        (1.2, impact(0.95)),
    ]
    ev += [(1.22, tone(NOTE(79), 1.0, "bell", 0.25)), (2.0, whoosh(0.9, True, 0.35))]
    start = 1.2  # the bed comes in on the address hit
    arp = [60, 64, 67, 72, 67, 64, 69, 72]  # C major / A minor colours
    bass = [36, 36, 33, 33, 41, 41, 43, 43]
    steps = int((6.0 - start) / (beat / 2))
    for k in range(steps):
        at = start + k * beat / 2
        ev.append((at, tone(NOTE(arp[k % 8] + 12), 0.28, "pluck", 0.16)))
        if k % 2 == 0:
            ev.append((at, kick(0.8)))
            ev.append((at, tone(NOTE(bass[(k // 2) % 8]), 0.45, "bass", 0.32)))
        else:
            ev.append((at, hat(0.2)))
        if k % 4 == 2:
            ev.append((at, hat(0.12)))
    ev.append((start, tone(NOTE(48), 4.8, "pad", 0.1)))
    for i in range(5):  # the region labels
        ev.append((2.87 + i * 0.2, tone(NOTE(72 + [0, 2, 4, 7, 9][i]), 0.35, "bell", 0.22)))
    ev += [
        (3.33, whoosh(0.6, False, 0.3)),
        (3.45, tone(NOTE(91), 1.8, "bell", 0.2)),
        (3.45, tone(NOTE(84), 1.8, "bell", 0.16)),
    ]
    return mix(6.0, ev)


if __name__ == "__main__":
    kind, path = sys.argv[1], sys.argv[2]
    y = intro() if kind == "intro" else outro()
    k = int(0.3 * SR)
    y[-k:] *= np.linspace(1, 0, k)  # the picture holds to the last frame; only the sound's tail eases out (no click)
    y = np.tanh(y * 1.1)  # gentle glue, no clipping
    y = y / np.abs(y).max() * 0.89
    st = np.stack([y, np.roll(y, 40) * 0.98], axis=1)  # a touch of width
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((st * 32767).astype("<i2").tobytes())
