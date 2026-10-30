"""Page geometry: finding the sheet in a photo and flattening it to a known scale.

Everything downstream works in millimetres on a flattened page, with the origin
at the top-left corner of the paper. That is what lets an answer box found in a
phone photo become a pen position on the printer bed.
"""
from __future__ import annotations

import cv2
import numpy as np

LETTER_MM = (215.9, 279.4)
A4_MM = (210.0, 297.0)
PX_PER_MM = 6.0  # ~150 dpi: plenty for handwriting, small enough to send to the API


def load(path: str) -> np.ndarray:
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(f"could not read image: {path}")
    return img


def order_corners(pts: np.ndarray) -> np.ndarray:
    """Return corners as top-left, top-right, bottom-right, bottom-left."""
    pts = pts.reshape(4, 2).astype(np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[s.argmin()], pts[d.argmin()], pts[s.argmax()], pts[d.argmax()]], np.float32)


def find_page(img: np.ndarray) -> np.ndarray | None:
    """Find the four corners of the largest bright quadrilateral (the sheet).

    Returns None when nothing page-like fills a reasonable share of the frame,
    which is the case for a flatbed scan that is already just the page.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.dilate(cv2.Canny(blur, 50, 150), np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    frame_area = img.shape[0] * img.shape[1]
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        area = cv2.contourArea(approx)
        if len(approx) == 4 and 0.2 * frame_area < area < 0.98 * frame_area:
            return order_corners(approx)
    return None


def flatten(img: np.ndarray, page_mm=LETTER_MM, corners: np.ndarray | None = None) -> np.ndarray:
    """Warp the sheet to a top-down image of exactly page_mm at PX_PER_MM."""
    w, h = int(page_mm[0] * PX_PER_MM), int(page_mm[1] * PX_PER_MM)
    if corners is None:
        corners = find_page(img)
    if corners is None:
        return cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], np.float32)
    m = cv2.getPerspectiveTransform(order_corners(corners), dst)
    return cv2.warpPerspective(img, m, (w, h))


def ink_mask(img: np.ndarray) -> np.ndarray:
    """Binary mask (uint8 0/255) of dark pen strokes, robust to uneven lighting."""
    gray = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 15
    )
