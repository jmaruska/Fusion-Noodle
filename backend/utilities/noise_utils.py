"""
Noise utilities — pure-Python 3D Simplex noise with fBm layering.

Public API
----------
build_perm_table(seed)          → list[int] (512 entries, cached by seed)
simplex3(x, y, z, perm)         → float in approximately [-1, 1]
fbm3(x, y, z, perm, **kwargs)   → float in [-1, 1]  (layered octaves)
noise3_range(x, y, z, perm, **kwargs) → float remapped to [out_min, out_max]

Based on Stefan Gustavson's public-domain Simplex implementation, adapted for
pure Python with seed-controlled permutation tables.
"""

import math
import random as _random
from functools import lru_cache
from typing import List

# 3D gradient vectors — 12 edges of a unit cube
_GRAD3 = [
    ( 1,  1,  0), (-1,  1,  0), ( 1, -1,  0), (-1, -1,  0),
    ( 1,  0,  1), (-1,  0,  1), ( 1,  0, -1), (-1,  0, -1),
    ( 0,  1,  1), ( 0, -1,  1), ( 0,  1, -1), ( 0, -1, -1),
]

# Skew / unskew factors for 3D
_F3 = 1.0 / 3.0
_G3 = 1.0 / 6.0


@lru_cache(maxsize=32)
def build_perm_table(seed: int) -> tuple:
    """Return a 512-entry permutation table as a tuple (immutable, cacheable)."""
    p = list(range(256))
    _random.Random(seed).shuffle(p)
    doubled = p + p
    return tuple(doubled)


def _dot3(g: tuple, x: float, y: float, z: float) -> float:
    return g[0] * x + g[1] * y + g[2] * z


def simplex3(x: float, y: float, z: float, perm: tuple) -> float:
    """
    3D Simplex noise.  Returns a value in approximately [-1, 1].

    perm should be a 512-entry table from build_perm_table().
    """
    # Skew into simplex grid
    s  = (x + y + z) * _F3
    i  = math.floor(x + s)
    j  = math.floor(y + s)
    k  = math.floor(z + s)
    t  = (i + j + k) * _G3

    # Unskewed distances from cell origin
    x0 = x - (i - t)
    y0 = y - (j - t)
    z0 = z - (k - t)

    # Determine which simplex we're in (one of 6 tetrahedra)
    if x0 >= y0:
        if y0 >= z0:      i1,j1,k1,i2,j2,k2 = 1,0,0,1,1,0
        elif x0 >= z0:    i1,j1,k1,i2,j2,k2 = 1,0,0,1,0,1
        else:             i1,j1,k1,i2,j2,k2 = 0,0,1,1,0,1
    else:
        if y0 < z0:       i1,j1,k1,i2,j2,k2 = 0,0,1,0,1,1
        elif x0 < z0:     i1,j1,k1,i2,j2,k2 = 0,1,0,0,1,1
        else:             i1,j1,k1,i2,j2,k2 = 0,1,0,1,1,0

    # Offsets for remaining three corners
    x1 = x0 - i1 + _G3;      y1 = y0 - j1 + _G3;      z1 = z0 - k1 + _G3
    x2 = x0 - i2 + 2 * _G3;  y2 = y0 - j2 + 2 * _G3;  z2 = z0 - k2 + 2 * _G3
    x3 = x0 - 1  + 3 * _G3;  y3 = y0 - 1  + 3 * _G3;  z3 = z0 - 1  + 3 * _G3

    ii = int(i) & 255
    jj = int(j) & 255
    kk = int(k) & 255

    gi0 = perm[ii      + perm[jj      + perm[kk     ]]] % 12
    gi1 = perm[ii + i1 + perm[jj + j1 + perm[kk + k1]]] % 12
    gi2 = perm[ii + i2 + perm[jj + j2 + perm[kk + k2]]] % 12
    gi3 = perm[ii +  1 + perm[jj +  1 + perm[kk +  1]]] % 12

    def _contrib(gi: int, dx: float, dy: float, dz: float) -> float:
        t = 0.6 - dx * dx - dy * dy - dz * dz
        if t < 0:
            return 0.0
        t *= t
        return t * t * _dot3(_GRAD3[gi], dx, dy, dz)

    n = (_contrib(gi0, x0, y0, z0) + _contrib(gi1, x1, y1, z1) +
         _contrib(gi2, x2, y2, z2) + _contrib(gi3, x3, y3, z3))

    return 32.0 * n  # scale to ~[-1, 1]


def fbm3(x: float, y: float, z: float, perm: tuple,
         octaves: int = 1, frequency: float = 1.0,
         lacunarity: float = 2.0, persistence: float = 0.5) -> float:
    """
    Fractional Brownian Motion over 3D Simplex noise.

    Layers `octaves` passes of simplex3, each at `lacunarity` × the previous
    frequency and `persistence` × the previous amplitude.

    Returns a value in [-1, 1].
    """
    value     = 0.0
    amplitude = 1.0
    max_amp   = 0.0
    freq      = frequency

    for _ in range(max(1, octaves)):
        value   += simplex3(x * freq, y * freq, z * freq, perm) * amplitude
        max_amp += amplitude
        amplitude *= persistence
        freq      *= lacunarity

    return value / max_amp if max_amp > 0 else 0.0


def noise3_range(x: float, y: float, z: float, perm: tuple,
                 octaves: int = 1, frequency: float = 1.0,
                 lacunarity: float = 2.0, persistence: float = 0.5,
                 out_min: float = 0.0, out_max: float = 1.0) -> float:
    """
    Evaluate fBm noise and remap the result from [-1, 1] to [out_min, out_max].
    """
    raw = fbm3(x, y, z, perm, octaves, frequency, lacunarity, persistence)
    t   = (raw + 1.0) * 0.5          # [-1,1] → [0,1]
    t   = max(0.0, min(1.0, t))
    return out_min + t * (out_max - out_min)


__all__ = ['build_perm_table', 'simplex3', 'fbm3', 'noise3_range']
