"""U-Net water segmentation on NISAR L2 GCOV HH backscatter.

UNet architecture copied from NISAR_UNET_MODELO_V1 (proyecto/nisar_training/unet.py):
in_channels=1, out_channels=1, base=16, depth=3. Weights are a plain state_dict exported
from checkpoints/best_unet.pt and loaded with weights_only=True only.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import torch
from torch import nn

HERE = Path(__file__).parent
WEIGHTS = HERE / "unet_water_v1.pt"
META = HERE / "unet_water_v1.json"


class DoubleConv(nn.Module):
    def __init__(self, in_ch: int, out_ch: int):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.block(x)


class UNet(nn.Module):
    def __init__(self, in_channels: int = 1, out_channels: int = 1, base: int = 16, depth: int = 3):
        super().__init__()
        widths = [base * 2**level for level in range(depth)]
        self.encoders = nn.ModuleList()
        ch = in_channels
        for w in widths:
            self.encoders.append(DoubleConv(ch, w))
            ch = w
        self.pool = nn.MaxPool2d(2, 2)
        self.bottleneck = DoubleConv(widths[-1], widths[-1] * 2)
        self.ups = nn.ModuleList()
        self.decoders = nn.ModuleList()
        ch = widths[-1] * 2
        for w in reversed(widths):
            self.ups.append(nn.ConvTranspose2d(ch, w, 2, 2))
            self.decoders.append(DoubleConv(w * 2, w))
            ch = w
        self.head = nn.Conv2d(base, out_channels, 1)

    def forward(self, x):
        skips = []
        for enc in self.encoders:
            x = enc(x)
            skips.append(x)
            x = self.pool(x)
        x = self.bottleneck(x)
        for up, dec, skip in zip(self.ups, self.decoders, reversed(skips)):
            x = dec(torch.cat((skip, up(x)), 1))
        return self.head(x)


@lru_cache(maxsize=1)
def load() -> tuple[UNet, dict]:
    meta = json.loads(META.read_text())
    model = UNet(meta["in_channels"], 1, meta["base"], meta["depth"])
    model.load_state_dict(torch.load(WEIGHTS, map_location="cpu", weights_only=True))
    model.eval()
    return model, meta


def _starts(length: int, size: int, step: int) -> list[int]:
    out = list(range(0, max(1, length - size + 1), step))
    last = max(0, length - size)
    if not out or out[-1] != last:
        out.append(last)
    return sorted(set(out))


def predict(power: np.ndarray, batch: int = 64) -> tuple[np.ndarray, np.ndarray]:
    """Water probability from gamma0 linear power on a 30 m grid (NaN = nodata).

    Returns (prob float32 with NaN nodata, valid mask). Patches 64, overlap 32, Hann blending.
    """
    model, meta = load()
    mean, std, ps = meta["mean"], meta["std"], meta["patch"]
    step = ps - meta["overlap"]
    h0, w0 = power.shape
    valid = np.isfinite(power) & (power > 0)
    x = np.full(power.shape, mean, np.float32)
    x[valid] = 10 * np.log10(power[valid])
    # Pad small inputs up to one patch so every pixel is covered.
    h, w = max(h0, ps), max(w0, ps)
    xn = np.zeros((h, w), np.float32)
    xn[:h0, :w0] = (x - mean) / std
    coords = [(r, c) for r in _starts(h, ps, step) for c in _starts(w, ps, step)]
    ax = np.hanning(ps + 2)[1:-1].astype(np.float32)
    wt = np.maximum(ax[:, None] * ax[None, :], 1e-3)
    acc = np.zeros((h, w), np.float32)
    ww = np.zeros((h, w), np.float32)
    for i in range(0, len(coords), batch):
        bc = coords[i : i + batch]
        ten = torch.from_numpy(np.stack([xn[r : r + ps, c : c + ps] for r, c in bc])[:, None])
        with torch.inference_mode():
            pr = model(ten).sigmoid().numpy()[:, 0]
        for (r, c), q in zip(bc, pr):
            acc[r : r + ps, c : c + ps] += q * wt
            ww[r : r + ps, c : c + ps] += wt
    prob = (acc / np.maximum(ww, 1e-8))[:h0, :w0]
    prob[~valid] = np.nan
    return prob.astype(np.float32), valid


def classify(prob: np.ndarray, threshold: float) -> np.ndarray:
    cl = np.full(prob.shape, 255, np.uint8)
    ok = np.isfinite(prob)
    cl[ok] = (prob[ok] >= threshold).astype(np.uint8)
    return cl



def predict_db(db: np.ndarray) -> np.ndarray:
    """Water probability (0-1, NaN nodata) from HH backscatter in dB (NaN = nodata)."""
    db = np.asarray(db, np.float32)
    power = np.where(np.isfinite(db), 10 ** (db / 10), np.nan).astype(np.float32)
    return predict(power)[0]


def utm_epsg(lon: float, lat: float) -> int:
    zone = min(60, max(1, int(math.floor((lon + 180) / 6)) + 1))
    return (32700 if lat < 0 else 32600) + zone
