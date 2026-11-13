"""A trained handwriting model that writes new text in the style of a sample.

This is Graves' handwriting synthesis network (arXiv:1308.0850): three stacked
LSTMs, a soft attention window that walks along the text being written, and a
mixture-of-Gaussians output that predicts each next pen movement. It was trained
on the IAM online handwriting database (hundreds of writers), and its weights
come from X-rayLaser/pytorch-handwriting-synthesis-toolkit (MIT licence).

"Priming" is how it copies a style: the network first reads the writer's own
pen strokes for some text, as if it had written them, and then carries on
writing the new text in the same way. Here the priming strokes are the writer's
learned letters, set out as a line of text.

Only the numbers are loaded from the downloaded checkpoint (torch.load with
weights_only=True, which can't run code); the network itself is written here.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import numpy as np

Polyline = list[tuple[float, float]]


class Model:
    def __init__(self, model_dir: str | Path, bias: float = 1.0):
        import torch
        d = Path(model_dir)
        meta = json.loads((d / "meta.json").read_text())
        self.torch = torch
        self.mu = torch.tensor(meta["mu"], dtype=torch.float32)
        self.sd = torch.tensor(meta["std"], dtype=torch.float32)
        self.charset = meta["charset"]
        self.index = {ch: i + 1 for i, ch in enumerate(self.charset)}  # 0 = anything else, and end of text
        self.p = torch.load(d / "model.pt", map_location="cpu", weights_only=True)
        self.bias = bias
        self.hidden = self.p["lstm1.W_ci"].shape[0]
        self.k_components = self.p["window.alpha.weight"].shape[0]
        self.m_components = self.p["mixture.pi.weight"].shape[0]

    # --- the network ---------------------------------------------------------
    def _lstm(self, name, x, state):
        p, torch = self.p, self.torch
        h, c = state
        z = torch.cat([x, h], dim=1) @ p[f"{name}.W_xh"]
        zi, zf, zc, zo = z.chunk(4, 1)
        i = torch.sigmoid(zi + c * p[f"{name}.W_ci"] + p[f"{name}.b_i"])
        f = torch.sigmoid(zf + c * p[f"{name}.W_cf"] + p[f"{name}.b_f"])
        c = f * c + i * torch.tanh(zc + p[f"{name}.b_c"])
        o = torch.sigmoid(zo + c * p[f"{name}.W_co"] + p[f"{name}.b_o"])
        h = o * torch.tanh(c)
        return h, (h, c)

    def _linear(self, name, x):
        return x @ self.p[f"{name}.weight"].T + self.p[f"{name}.bias"]

    def _window(self, h1, chars, k):
        torch = self.torch
        alpha = torch.exp(self._linear("window.alpha", h1))
        beta = torch.exp(self._linear("window.beta", h1))
        k = k + torch.exp(self._linear("window.k", h1))
        u = torch.arange(chars.shape[1], dtype=torch.float32)
        phi = (alpha[:, :, None] * torch.exp(-beta[:, :, None] * (k[:, :, None] - u) ** 2)).sum(dim=1)
        return phi, phi @ chars[0], k

    def _step(self, x, w, k, states, chars):
        torch = self.torch
        s1, s2, s3 = states
        h1, s1 = self._lstm("lstm1", torch.cat([x, w], dim=1), s1)
        phi, w, k = self._window(h1, chars, k)
        h2, s2 = self._lstm("lstm2", torch.cat([x, h1, w], dim=1), s2)
        h3, s3 = self._lstm("lstm3", torch.cat([x, h2, w], dim=1), s3)
        out = torch.cat([h1, h2, h3], dim=1)
        return out, phi, w, k, (s1, s2, s3)

    def _sample(self, out, rng: np.random.Generator):
        torch = self.torch
        b = self.bias
        pi = torch.softmax(self._linear("mixture.pi", out)[0] * (1 + b), dim=-1).numpy()
        mu = self._linear("mixture.mu", out)[0].numpy()
        sd = torch.exp(self._linear("mixture.sd", out)[0] - b).numpy()
        ro = torch.tanh(self._linear("mixture.ro", out)[0]).numpy()
        eos = torch.sigmoid(self._linear("mixture.eos", out)[0]).item()
        m = self.m_components
        j = rng.choice(m, p=pi / pi.sum())
        cov = [[sd[j] ** 2, ro[j] * sd[j] * sd[j + m]], [ro[j] * sd[j] * sd[j + m], sd[j + m] ** 2]]
        dx, dy = rng.multivariate_normal([mu[j], mu[j + m]], cov)
        return np.array([dx, dy, 1.0 if eos > 0.5 else 0.0], dtype=np.float32)

    # --- using it -----------------------------------------------------------
    def encode(self, text: str):
        torch = self.torch
        eye = torch.eye(len(self.charset) + 1)
        return eye[[self.index.get(ch, 0) for ch in text]][None]

    def write(self, text: str, prime: list[Polyline] | None = None, prime_text: str = "",
              seed: int = 0, max_steps: int = 2500) -> list[Polyline]:
        """Pen strokes for text, in the model's own units (y down). Primed with a sample when given."""
        torch = self.torch
        rng = np.random.default_rng(seed)
        with torch.no_grad():
            chars = self.encode((prime_text + " " if prime else "") + text + "\n")
            u = chars.shape[1]
            zeros = lambda: (torch.zeros(1, self.hidden), torch.zeros(1, self.hidden))  # noqa: E731
            states = (zeros(), zeros(), zeros())
            w = torch.zeros(1, chars.shape[2])
            k = torch.zeros(1, self.k_components)
            x = torch.zeros(1, 3)
            for point in self._offsets(prime) if prime else []:
                _, _, w, k, states = self._step(x, w, k, states, chars)
                x = ((torch.tensor(point) - self.mu) / self.sd)[None]
            points, start = [], None
            first_new = len(prime_text) + 1 if prime else 0  # where the new text begins
            for _ in range(max_steps):
                out, phi, w, k, states = self._step(x, w, k, states, chars)
                p = self._sample(out, rng)
                if start is None and int(phi[0].argmax()) >= first_new:
                    start = len(points)
                points.append(p)
                if phi[0, u - 1] > 0.8 or (phi[0].argmax() == u - 1 and p[2] > 0.5):
                    break
                x = torch.tensor(p)[None]
        raw = np.array(points) * self.sd.numpy() + self.mu.numpy()
        strokes = _to_strokes(raw)
        if prime and start:
            # After priming the model often finishes the sample's last word first; keep only what
            # it wrote once its attention reached the new text, from the start of that stroke.
            begin = int(raw[:start, 2].nonzero()[0][-1]) + 1 if raw[:start, 2].any() else 0
            strokes = _to_strokes(raw[begin:], origin=np.cumsum(raw[:begin, :2], axis=0)[-1] if begin else None)
        return strokes

    @staticmethod
    def _offsets(strokes: list[Polyline]) -> list[list[float]]:
        out, last = [], np.array(strokes[0][0])
        for s in strokes:
            for i, p in enumerate(s):
                p = np.array(p)
                d = p - last
                out.append([float(d[0]), float(d[1]), 1.0 if i == len(s) - 1 else 0.0])
                last = p
        return out


def _to_strokes(raw: np.ndarray, origin=None) -> list[Polyline]:
    pts = np.cumsum(raw[:, :2], axis=0) + (origin if origin is not None else 0)
    strokes, cur = [], []
    for (x, y), e in zip(pts, raw[:, 2]):
        cur.append((float(x), float(y)))
        if e > 0.5:
            strokes.append(cur)
            cur = []
    if len(cur) > 1:
        strokes.append(cur)
    return strokes


def x_height(strokes: list[Polyline]) -> float:
    """A robust size measure: the middle band most of the ink sits in."""
    ys = np.array([y for s in strokes for _, y in s])
    return float(np.percentile(ys, 80) - np.percentile(ys, 30)) or 1.0


def prime_from_hand(hand, text: str, unit_x_height: float, rng: random.Random) -> list[Polyline]:
    """The writer's own letters for text, set out on a line and scaled to the model's units."""
    scale = unit_x_height / max(hand.x_height, 0.5)
    strokes, pen_x = [], 0.0
    gap = 0.15 * hand.cap_height
    for ch in text:
        if ch == " ":
            pen_x += 0.6 * hand.cap_height
            continue
        g = hand.make(ch, rng)
        if g is None:
            continue
        for s in g.strokes:
            pts = s if len(s) > 1 else [s[0], (s[0][0] + 0.05, s[0][1])]
            strokes.append([((pen_x + x) * scale, y * scale) for x, y in _resample(pts, 0.4)])
        pen_x += g.width + gap
    return strokes


def _resample(pts: Polyline, step: float) -> Polyline:
    """Points about `step` mm apart, like a tablet's samples, so the model reads it as handwriting."""
    a = np.asarray(pts, float)
    seg = np.hypot(*np.diff(a, axis=0).T)
    d = np.concatenate([[0], np.cumsum(seg)])
    if d[-1] == 0:
        return [tuple(a[0]), tuple(a[-1])]
    t = np.linspace(0, d[-1], max(2, int(d[-1] / step) + 1))
    return list(zip(np.interp(t, d, a[:, 0]), np.interp(t, d, a[:, 1])))


def fit_to(strokes: list[Polyline], cap_mm: float, unit_x_height: float, x0: float, baseline: float) -> list[Polyline]:
    """Model units to page mm: scaled so its x-height matches the writer's, placed at x0 on the baseline."""
    s = (0.6 * cap_mm) / unit_x_height
    ys = np.array([y for st in strokes for _, y in st])
    xs = np.array([x for st in strokes for x, _ in st])
    base = np.percentile(ys, 85)
    return [[(x0 + (x - xs.min()) * s, baseline + (y - base) * s) for x, y in st] for st in strokes]


def looks_right(strokes: list[Polyline], text: str, unit_x_height: float) -> bool:
    """Reject the model's occasional misfires.

    Measured on good output: about 1.6-1.9 x-heights of width per letter, about
    5 x-heights from the tallest ascender to the lowest descender, pen-down steps
    under half an x-height, and roughly a stroke per letter. A misfire is one long
    looping stroke: far too narrow and tall, with few strokes.
    """
    if not strokes:
        return False
    pts = np.array([p for s in strokes for p in s])
    letters = max(len(text.replace(" ", "")), 1)
    per_letter = np.ptp(pts[:, 0]) / unit_x_height / letters
    if not 0.9 < per_letter < 3.0:
        return False
    if np.ptp(pts[:, 1]) / unit_x_height > 7.5:
        return False
    if len(strokes) < letters / 3:
        return False
    for s in strokes:
        a = np.asarray(s)
        if len(a) > 1 and np.hypot(*np.diff(a, axis=0).T).max() > 1.5 * unit_x_height:
            return False
    return True


def write_checked(model: Model, text: str, prime=None, prime_text: str = "", unit_x_height: float = 91.5,
                  seed: int = 0, tries: int = 6) -> list[Polyline]:
    """model.write, retried with fresh randomness until the result passes looks_right."""
    for t in range(tries):
        out = model.write(text, prime=prime, prime_text=prime_text, seed=seed + 1000 * t)
        if looks_right(out, text, unit_x_height):
            return out
    raise RuntimeError(f"the model couldn't write {text!r} cleanly in {tries} tries")
