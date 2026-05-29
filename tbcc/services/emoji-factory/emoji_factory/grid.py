"""Grid geometry for tile crops."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TileRect:
    row: int
    col: int
    x: int
    y: int
    w: int
    h: int

    @property
    def name(self) -> str:
        return f"tile_{self.row:02d}_{self.col:02d}"


def compute_tile_rects(
    *,
    frame_w: int,
    frame_h: int,
    cols: int,
    rows: int,
    margin_pct: float = 0.0,
) -> list[TileRect]:
    if cols < 1 or rows < 1:
        raise ValueError("cols and rows must be >= 1")
    if frame_w < cols or frame_h < rows:
        raise ValueError(f"frame {frame_w}x{frame_h} too small for {cols}x{rows} grid")

    cell_w = frame_w // cols
    cell_h = frame_h // rows
    margin_pct = max(0.0, min(40.0, margin_pct))
    inset_x = int(cell_w * margin_pct / 100.0 / 2)
    inset_y = int(cell_h * margin_pct / 100.0 / 2)

    rects: list[TileRect] = []
    for row in range(rows):
        for col in range(cols):
            x0 = col * cell_w + inset_x
            y0 = row * cell_h + inset_y
            w = cell_w - 2 * inset_x
            h = cell_h - 2 * inset_y
            if w < 8 or h < 8:
                raise ValueError("margin_pct too large for cell size")
            rects.append(TileRect(row=row, col=col, x=x0, y=y0, w=w, h=h))
    return rects
