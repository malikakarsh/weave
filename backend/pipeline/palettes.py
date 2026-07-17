"""Named, perceptually-uniform color palettes for grouped charts.

The HCL-based palettes (vibrant/dark/light/muted) share the same golden-angle hue
spacing and only vary chroma/lightness, so series stay perceptually distinct and
uniform across palettes. The conversion matches d3-color's Lab/HCL math (D50 white
point) so a Python-generated palette is identical to `d3.hcl(...)` in the browser —
including the default `d3.hcl(230 + i*137.508, 68, 65)` the templates fall back to.
"""

import math

# d3-color Lab constants (D50 white point)
_Xn, _Yn, _Zn = 0.96422, 1.0, 0.82521
_t0 = 4 / 29
_t1 = 6 / 29
_t2 = 3 * _t1 * _t1
_t3 = _t1 * _t1 * _t1


def _lab2xyz(t: float) -> float:
    return t * t * t if t > _t1 else _t2 * (t - _t0)


def _lrgb2rgb(x: float) -> int:
    v = 12.92 * x if x <= 0.0031308 else 1.055 * (x ** (1 / 2.4)) - 0.055
    return max(0, min(255, round(255 * v)))


def hcl_to_hex(h: float, c: float, l: float) -> str:
    """Convert a CIE HCL (Lab-based, like d3.hcl) color to a #rrggbb hex string."""
    hr = math.radians(h)
    a = math.cos(hr) * c
    b = math.sin(hr) * c

    y = (l + 16) / 116
    x = y + a / 500
    z = y - b / 200
    x = _Xn * _lab2xyz(x)
    y = _Yn * _lab2xyz(y)
    z = _Zn * _lab2xyz(z)

    r = _lrgb2rgb(3.1338561 * x - 1.6168667 * y - 0.4906146 * z)
    g = _lrgb2rgb(-0.9787684 * x + 1.9161415 * y + 0.0334540 * z)
    bb = _lrgb2rgb(0.0719453 * x - 0.2289914 * y + 1.4052427 * z)
    return f"#{r:02x}{g:02x}{bb:02x}"


_GOLDEN = 137.508  # golden-angle hue step for maximally-distinct successive hues


def _hcl_ramp(chroma: float, lightness: float, n: int = 20) -> list[str]:
    """Generate n colors sharing hue spacing, at a fixed chroma and lightness."""
    return [hcl_to_hex(230 + i * _GOLDEN, chroma, lightness) for i in range(n)]


# HCL ramps — same hue spacing, only chroma/lightness change between them.
# "vibrant" reproduces the templates' built-in default exactly.
_HCL_PALETTES = {
    "vibrant": _hcl_ramp(68, 65),
    "dark":    _hcl_ramp(58, 48),
    "light":   _hcl_ramp(42, 82),
    "muted":   _hcl_ramp(32, 62),
}

# Fixed categorical schemes (well-known, cycle for >len groups via scaleOrdinal).
_SCHEME_PALETTES = {
    "tableau10": ["#4e79a7", "#f28e2c", "#e15759", "#76b7b2", "#59a14f",
                  "#edc949", "#af7aa1", "#ff9da7", "#9c755f", "#bab0ab"],
    "category10": ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
                   "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"],
    "set2": ["#66c2a5", "#fc8d62", "#8da0cb", "#e78ac3", "#a6d854",
             "#ffd92f", "#e5c494", "#b3b3b3"],
    "dark2": ["#1b9e77", "#d95f02", "#7570b3", "#e7298a", "#66a61e",
              "#e6ab02", "#a6761d", "#666666"],
    "pastel": ["#fbb4ae", "#b3cde3", "#ccebc5", "#decbe4", "#fed9a6",
               "#ffffcc", "#e5d8bd", "#fddaec", "#f2f2f2"],
}

PALETTES: dict[str, list[str]] = {**_HCL_PALETTES, **_SCHEME_PALETTES}

# Accept common aliases the LLM (or a user) might produce.
_ALIASES = {
    "default": "vibrant",
    "standard": "vibrant",
    "bright": "vibrant",
    "colorful": "vibrant",
    "tableau": "tableau10",
    "d3": "category10",
    "soft": "set2",
    "bold": "dark2",
    "pastel1": "pastel",
}

# Names to advertise to the LLM in the refine prompt.
PALETTE_NAMES = list(PALETTES.keys())


def resolve_palette(name: str | None) -> list[str] | None:
    """Return the color list for a named palette, or None if unknown/empty.

    Tolerant of extra words: 'dark', 'dark shade', 'use a dark palette' all
    resolve to the 'dark' ramp. Exact/alias match wins; otherwise the first
    known palette name (or alias) appearing as a whole word in the string.
    """
    if not name:
        return None
    s = name.strip().lower()
    direct = _ALIASES.get(s, s)
    if direct in PALETTES:
        return PALETTES[direct]

    import re
    tokens = set(re.findall(r"[a-z0-9]+", s))
    # More specific names (e.g. 'dark2', 'tableau10') take precedence over 'dark'.
    for cand in sorted(list(PALETTES) + list(_ALIASES), key=len, reverse=True):
        if cand in tokens:
            return PALETTES[_ALIASES.get(cand, cand)]
    return None
