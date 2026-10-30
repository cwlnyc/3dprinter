"""The handwriting sample sheet: generate it, then read it back from a scan.

Each sheet has an ArUco marker in every corner, so a photo taken at any angle
can be mapped back to exact template millimetres. Page n uses marker ids
4n..4n+3, which is how a scan says which page it is without any OCR.

Inside each box the writer puts one character. The tick marks either side of a
box show the baseline; the box itself is printed light grey and the reader crops
inside it, so the border never becomes part of a letter.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .page import LETTER_MM, ink_mask

CHARSET = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    ".,?!:;'\"()-+=/*%$<>^_#&@[]"
)
COPIES = 2  # every character twice, so a page of answers is not a page of clones

MARKER_MM = 14.0
MARGIN_MM = 10.0
BOX_W, BOX_H = 13.0, 18.0          # writing box
CELL_W, CELL_H = 15.5, 23.0        # box plus gap and label room
BASELINE_FROM_TOP = 12.5           # descenders get the 5.5 mm below this
GRID_TOP = MARGIN_MM + MARKER_MM + 6.0
GRID_LEFT = MARGIN_MM + 3.0
COLS = 12
ROWS = 9
DICT = cv2.aruco.DICT_4X4_50
READ_PX_PER_MM = 12.0              # finer than page.PX_PER_MM: skeletons need the detail


@dataclass(frozen=True)
class Cell:
    char: str
    page: int
    x: float  # box top-left, mm
    y: float


def cells() -> list[Cell]:
    chars = [c for _ in range(COPIES) for c in CHARSET]
    per_page = COLS * ROWS
    out = []
    for i, ch in enumerate(chars):
        page, k = divmod(i, per_page)
        r, c = divmod(k, COLS)
        out.append(Cell(ch, page, GRID_LEFT + c * CELL_W, GRID_TOP + r * CELL_H))
    return out


def page_count() -> int:
    return max(c.page for c in cells()) + 1


def marker_centres_mm(page_mm=LETTER_MM) -> list[tuple[float, float]]:
    w, h = page_mm
    a = MARGIN_MM + MARKER_MM / 2
    return [(a, a), (w - a, a), (w - a, h - a), (a, h - a)]


def render_page(page: int, dpi: int = 300, page_mm=LETTER_MM) -> Image.Image:
    px = dpi / 25.4
    W, H = round(page_mm[0] * px), round(page_mm[1] * px)
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", int(2.6 * px))
        small = ImageFont.truetype("DejaVuSans.ttf", int(3.2 * px))
    except OSError:
        font = small = ImageFont.load_default()

    aruco = cv2.aruco.getPredefinedDictionary(DICT)
    side = round(MARKER_MM * px)
    for i, (cx, cy) in enumerate(marker_centres_mm(page_mm)):
        m = cv2.aruco.generateImageMarker(aruco, page * 4 + i, side)
        img.paste(Image.fromarray(m), (round((cx - MARKER_MM / 2) * px), round((cy - MARKER_MM / 2) * px)))

    d.text(
        (round((MARGIN_MM + MARKER_MM + 4) * px), round(MARGIN_MM * px)),
        f"Handwriting sample - page {page + 1} of {page_count()}.  One character per box, "
        "sitting on the tick marks.\nUse the pen you will put in the printer. Keep it inside the box.",
        fill=0,
        font=small,
    )
    for cell in (c for c in cells() if c.page == page):
        x0, y0 = cell.x * px, cell.y * px
        x1, y1 = (cell.x + BOX_W) * px, (cell.y + BOX_H) * px
        d.rectangle([x0, y0, x1, y1], outline=200, width=max(1, round(0.2 * px)))
        by = (cell.y + BASELINE_FROM_TOP) * px
        tick = 1.5 * px
        d.line([x0 - tick, by, x0, by], fill=120, width=max(1, round(0.25 * px)))
        d.line([x1, by, x1 + tick, by], fill=120, width=max(1, round(0.25 * px)))
        d.text((x0, y1 + 0.6 * px), cell.char, fill=90, font=font)
    return img


def write_template(path: str, dpi: int = 300) -> int:
    pages = [render_page(p, dpi) for p in range(page_count())]
    pages[0].save(path, save_all=True, append_images=pages[1:], resolution=dpi)
    return len(pages)


def register(img: np.ndarray, page_mm=LETTER_MM) -> tuple[int, np.ndarray]:
    """Find the markers and return (page number, image flattened to template mm)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(DICT), cv2.aruco.DetectorParameters())
    corners, ids, _ = detector.detectMarkers(gray)
    if ids is None:
        raise ValueError("no corner markers found - is the whole sheet in the photo?")
    found = {int(i): c.reshape(4, 2).mean(axis=0) for i, c in zip(ids.ravel(), corners)}
    pages = {i // 4 for i in found}
    page = max(pages, key=lambda p: sum(1 for i in found if i // 4 == p))
    pts = [(found[page * 4 + k], k) for k in range(4) if page * 4 + k in found]
    if len(pts) < 4:
        raise ValueError(f"only {len(pts)} of 4 corner markers visible on page {page + 1}")
    src = np.array([p for p, _ in pts], np.float32)
    dst = np.array([marker_centres_mm(page_mm)[k] for _, k in pts], np.float32) * READ_PX_PER_MM
    m = cv2.getPerspectiveTransform(src, dst)
    size = (round(page_mm[0] * READ_PX_PER_MM), round(page_mm[1] * READ_PX_PER_MM))
    return page, cv2.warpPerspective(gray, m, size, borderValue=255)


def box_mask(flat: np.ndarray, cell: Cell, inset_mm: float = 1.0) -> np.ndarray:
    """Ink inside one writing box, with the printed border cropped off."""
    s = READ_PX_PER_MM
    x0, y0 = round((cell.x + inset_mm) * s), round((cell.y + inset_mm) * s)
    x1, y1 = round((cell.x + BOX_W - inset_mm) * s), round((cell.y + BOX_H - inset_mm) * s)
    return ink_mask(flat[y0:y1, x0:x1])
