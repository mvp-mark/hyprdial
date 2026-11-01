"""Geometria da disposição de monitores (sem GTK, testável).

Coordenadas em pixels lógicos do Hyprland: tamanho do modo dividido pela escala,
com largura e altura trocadas quando o monitor está girado 90° ou 270°.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Rect:
    name: str
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    def moved(self, x: int, y: int) -> Rect:
        return replace(self, x=x, y=y)


def logical_size(mode: str, scale: float, transform: int, fallback: tuple[int, int]) -> tuple[int, int]:
    m = re.match(r"(\d+)x(\d+)", mode or "")
    w, h = (int(m.group(1)), int(m.group(2))) if m else fallback
    scale = scale if scale and scale > 0 else 1
    w, h = round(w / scale), round(h / scale)
    return (h, w) if transform % 2 else (w, h)


def overlaps(a: Rect, b: Rect) -> bool:
    return a.x < b.right and b.x < a.right and a.y < b.bottom and b.y < a.bottom


def touches(a: Rect, b: Rect) -> bool:
    """Compartilham um trecho de borda (o cursor consegue passar de um para o outro)."""
    side = (a.right == b.x or b.right == a.x) and a.y < b.bottom and b.y < a.bottom
    top = (a.bottom == b.y or b.bottom == a.y) and a.x < b.right and b.x < a.right
    return side or top


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(v, hi))


def snap(r: Rect, others: list[Rect], threshold: float) -> Rect:
    """Durante o arraste, puxa as bordas de r para as bordas próximas dos outros monitores."""

    def best(pos: int, size: int, edges: list[int]) -> int:
        candidates = [e for e in edges] + [e - size for e in edges]
        near = min(candidates, key=lambda c: abs(c - pos), default=pos)
        return near if abs(near - pos) <= threshold else pos

    xs = [e for o in others for e in (o.x, o.right)]
    ys = [e for o in others for e in (o.y, o.bottom)]
    return r.moved(best(r.x, r.w, xs), best(r.y, r.h, ys))


def settle(r: Rect, others: list[Rect]) -> Rect:
    """Ao soltar: posição mais próxima em que r não sobrepõe ninguém e encosta em algum monitor."""
    if not others:
        return r

    def valid(c: Rect) -> bool:
        return not any(overlaps(c, o) for o in others) and any(touches(c, o) for o in others)

    if valid(r):
        return r
    candidates = []
    for o in others:
        y = _clamp(r.y, o.y - r.h + 1, o.bottom - 1)
        x = _clamp(r.x, o.x - r.w + 1, o.right - 1)
        candidates += [r.moved(o.x - r.w, y), r.moved(o.right, y), r.moved(x, o.y - r.h), r.moved(x, o.bottom)]
    good = [c for c in candidates if valid(c)]
    if not good:
        return r
    return min(good, key=lambda c: (c.x - r.x) ** 2 + (c.y - r.y) ** 2)


def normalize(rects: list[Rect]) -> list[Rect]:
    """Desloca tudo para que o canto superior esquerdo da disposição fique em 0x0."""
    if not rects:
        return rects
    dx, dy = min(r.x for r in rects), min(r.y for r in rects)
    return [r.moved(r.x - dx, r.y - dy) for r in rects]
