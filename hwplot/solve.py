"""Reading the homework sheet and working out the answers, with Claude.

One call does both jobs: it reads the questions off the photo, solves them, and
says where on the page each answer goes. The result is written to answers.json
before anything is drawn, so a wrong answer or a badly placed box can be fixed
by hand rather than discovered in ink.
"""
from __future__ import annotations

import base64
import json
from dataclasses import asdict, dataclass

import anthropic
import cv2
import numpy as np

from .page import PX_PER_MM

MODEL = "claude-opus-5-5"

SCHEMA = {
    "type": "object",
    "properties": {
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Question number as printed, e.g. '3b'"},
                    "question": {"type": "string"},
                    "answer": {"type": "string", "description": "Exactly what to write on the sheet"},
                    "kind": {"type": "string", "enum": ["write", "circle"]},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "w": {"type": "number"},
                    "h": {"type": "number"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["id", "question", "answer", "kind", "x", "y", "w", "h", "confidence"],
                "additionalProperties": False,
            },
        },
        "notes": {"type": "string"},
    },
    "required": ["answers", "notes"],
    "additionalProperties": False,
}

PROMPT = """This is a photo of a homework sheet, flattened to {w}x{h} pixels.

For every question on it that is waiting for an answer:
1. Read the question carefully and solve it. Check your working; these answers
   get written in ink.
2. Decide what a student would write in the space provided, and nothing more:
   the final answer, with brief working only if the space is clearly meant for it.
   Keep it short enough to fit the blank comfortably at normal handwriting size.
3. Give the box where it should be written, in pixels of this image (x, y = top
   left). Use the blank line, box or gap meant for the answer. Never overlap
   printed text.

For multiple choice, set kind to "circle" and give the box tightly around the
option to circle (answer = the option's label). Otherwise kind is "write".

Only these characters can be written (the student's handwriting sample):
{charset}
Spell answers using those alone: write "x" for multiplication if "×" is missing,
"sqrt" for a root, "^" for powers, "/" for fractions.

Skip questions that are already answered. Put anything the student should know
(unreadable questions, assumptions you made) in notes."""


@dataclass
class Answer:
    id: str
    question: str
    answer: str
    kind: str
    box: tuple[float, float, float, float]  # x, y, w, h in page mm
    confidence: str
    # What the box was snapped to on the page: "line" (box bottom is the line),
    # "box", "option" (a multiple-choice label), or "none" (Claude's own box).
    target: str = "none"


def _encode(img: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise RuntimeError("could not encode image")
    return base64.standard_b64encode(buf.tobytes()).decode()


def solve(flat: np.ndarray, charset: str, client: anthropic.Anthropic | None = None) -> tuple[list[Answer], str]:
    client = client or anthropic.Anthropic()
    h, w = flat.shape[:2]
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=64000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        thinking={"type": "adaptive"},
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _encode(flat)}},
                    {"type": "text", "text": PROMPT.format(w=w, h=h, charset=charset)},
                ],
            }
        ],
    ) as stream:
        msg = stream.get_final_message()

    if msg.stop_reason == "refusal":
        raise RuntimeError("the model declined to answer this sheet")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("the response was cut off before it finished; try a sheet with fewer questions")
    text = next(b.text for b in msg.content if b.type == "text")
    data = json.loads(text)
    answers = [
        Answer(
            a["id"], a["question"], a["answer"], a["kind"],
            (a["x"] / PX_PER_MM, a["y"] / PX_PER_MM, a["w"] / PX_PER_MM, a["h"] / PX_PER_MM),
            a["confidence"],
        )
        for a in data["answers"]
    ]
    return answers, data["notes"]


def save(path: str, answers: list[Answer], notes: str) -> None:
    with open(path, "w") as f:
        json.dump({"notes": notes, "answers": [asdict(a) for a in answers]}, f, indent=2)


def load(path: str) -> tuple[list[Answer], str]:
    with open(path) as f:
        data = json.load(f)
    return [Answer(**{"target": "none", **a, "box": tuple(a["box"])}) for a in data["answers"]], data.get("notes", "")
