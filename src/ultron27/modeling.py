from __future__ import annotations

import json
import math
import re
from typing import Any

from .llm import GroqChatProvider, LLMChatError
from .runtime import RuntimeSettings


ALLOWED_SHAPES = {"box", "sphere", "cylinder", "cone", "pyramid", "torus", "capsule"}
DEFAULT_COLORS = ("#55e6a2", "#67cce6", "#f1c66d", "#ff8f70", "#b7a2ff")


def generate_model_scene(description: str, settings: RuntimeSettings) -> dict[str, Any]:
    clean = " ".join(str(description or "").strip().split())[:180]
    if not clean:
        return {"status": "empty", "message": "Tell me what 3D object to create, sir.", "scene": None}

    local = _local_scene(clean)
    if local is not None:
        return {
            "status": "success",
            "message": f"I created a manipulable 3D {local['name']}, sir.",
            "source": "procedural",
            "scene": local,
        }

    if settings.llm_provider != "groq":
        return {
            "status": "unsupported",
            "message": f"I do not know how to compose {clean} from my supported 3D primitives yet, sir.",
            "source": "local",
            "scene": None,
        }

    messages = [
        {
            "role": "system",
            "content": (
                "Create a compact 3D scene approximation from safe primitives. Return JSON only with this shape: "
                '{"name":"short name","objects":[{"shape":"box|sphere|cylinder|cone|pyramid|torus|capsule",'
                '"position":[x,y,z],"rotation":[x,y,z],"scale":[x,y,z],"color":"#RRGGBB"}]}. '
                "Use at most 20 objects. Coordinates are in meters near the origin. Keep every scale between 0.05 and 6. "
                "Never emit code, URLs, files, text labels, lights, cameras, materials, or keys outside the schema. "
                "Approximate recognizable structure with simple parts and do not claim photorealistic accuracy."
            ),
        },
        {"role": "user", "content": f"Object to model: {clean}"},
    ]
    try:
        provider = GroqChatProvider(endpoint=settings.llm_endpoint, model=settings.llm_model)
        raw = provider.complete_chat(messages, settings.llm_timeout_seconds, max_tokens=900)
        scene = validate_scene_spec(_parse_json_object(raw), fallback_name=clean)
    except (LLMChatError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "error",
            "message": f"I could not build a safe 3D approximation of {clean} right now, sir.",
            "source": "groq",
            "error": str(exc),
            "scene": None,
        }
    return {
        "status": "success",
        "message": f"I created a primitive-based 3D approximation of {clean}, sir.",
        "source": "groq",
        "scene": scene,
    }


def validate_scene_spec(payload: dict[str, Any], *, fallback_name: str = "model") -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Model scene must be a JSON object.")
    raw_objects = payload.get("objects")
    if not isinstance(raw_objects, list) or not raw_objects:
        raise ValueError("Model scene must include at least one object.")
    objects = []
    for index, raw in enumerate(raw_objects[:20]):
        if not isinstance(raw, dict):
            continue
        shape = str(raw.get("shape") or "").strip().lower()
        if shape not in ALLOWED_SHAPES:
            continue
        objects.append(
            {
                "shape": shape,
                "position": _vector(raw.get("position"), default=(0.0, 0.0, 0.0), low=-6.0, high=6.0),
                "rotation": _vector(raw.get("rotation"), default=(0.0, 0.0, 0.0), low=-math.tau, high=math.tau),
                "scale": _vector(raw.get("scale"), default=(1.0, 1.0, 1.0), low=0.05, high=6.0),
                "color": _color(raw.get("color"), DEFAULT_COLORS[index % len(DEFAULT_COLORS)]),
            }
        )
    if not objects:
        raise ValueError("Model scene did not contain supported primitives.")
    name = re.sub(r"[^a-z0-9 _-]+", "", str(payload.get("name") or fallback_name).lower()).strip()[:48] or "model"
    return {"name": name, "objects": objects, "approximate": True}


def _local_scene(description: str) -> dict[str, Any] | None:
    text = description.lower().strip()
    if re.search(r"\b(cube|box)\b", text):
        return _scene("cube", [_part("box", scale=(2.4, 2.4, 2.4))])
    if re.search(r"\b(sphere|ball|globe)\b", text):
        return _scene("sphere", [_part("sphere", scale=(2.2, 2.2, 2.2), color="#67cce6")])
    if re.search(r"\b(cylinder|pipe)\b", text):
        return _scene("cylinder", [_part("cylinder", scale=(1.5, 2.8, 1.5), color="#f1c66d")])
    if re.search(r"\bcone\b", text):
        return _scene("cone", [_part("cone", scale=(1.8, 3.0, 1.8), color="#ff8f70")])
    if re.search(r"\bpyramid\b", text):
        return _scene("pyramid", [_part("pyramid", scale=(2.6, 2.8, 2.6), color="#f1c66d")])
    if re.search(r"\b(torus|donut|doughnut|ring)\b", text):
        return _scene("torus", [_part("torus", scale=(2.2, 2.2, 2.2), color="#b7a2ff")])
    if re.search(r"\bcapsule\b", text):
        return _scene("capsule", [_part("capsule", scale=(1.5, 2.6, 1.5), color="#67cce6")])
    if re.search(r"\b(water\s+)?bottle\b", text):
        return _scene(
            "bottle",
            [
                _part("cylinder", scale=(1.15, 2.5, 1.15), position=(0, -0.25, 0), color="#67cce6"),
                _part("cylinder", scale=(0.48, 0.72, 0.48), position=(0, 1.35, 0), color="#67cce6"),
                _part("cylinder", scale=(0.55, 0.2, 0.55), position=(0, 1.82, 0), color="#f1c66d"),
            ],
        )
    if re.search(r"\bchair\b", text):
        parts = [
            _part("box", scale=(2.2, 0.35, 2.0), position=(0, 0.2, 0)),
            _part("box", scale=(2.2, 2.4, 0.3), position=(0, 1.45, -0.85)),
        ]
        for x in (-0.82, 0.82):
            for z in (-0.72, 0.72):
                parts.append(_part("box", scale=(0.28, 1.8, 0.28), position=(x, -0.85, z), color="#67cce6"))
        return _scene("chair", parts)
    if re.search(r"\btable\b", text):
        parts = [_part("box", scale=(3.6, 0.3, 2.4), position=(0, 1.1, 0), color="#f1c66d")]
        for x in (-1.45, 1.45):
            for z in (-0.85, 0.85):
                parts.append(_part("box", scale=(0.3, 2.3, 0.3), position=(x, -0.2, z)))
        return _scene("table", parts)
    if re.search(r"\bdumbbell\b", text):
        return _scene(
            "dumbbell",
            [
                _part("cylinder", scale=(0.35, 2.8, 0.35), rotation=(0, 0, math.pi / 2), color="#67cce6"),
                _part("cylinder", scale=(0.85, 0.55, 0.85), position=(-1.55, 0, 0), rotation=(0, 0, math.pi / 2)),
                _part("cylinder", scale=(0.85, 0.55, 0.85), position=(1.55, 0, 0), rotation=(0, 0, math.pi / 2)),
            ],
        )
    if re.search(r"\brocket\b", text):
        return _scene(
            "rocket",
            [
                _part("cylinder", scale=(1.0, 2.6, 1.0), color="#dce9e7"),
                _part("cone", scale=(1.05, 1.25, 1.05), position=(0, 1.9, 0), color="#ff8f70"),
                _part("cone", scale=(0.7, 0.9, 0.7), position=(0, -1.75, 0), rotation=(math.pi, 0, 0), color="#f1c66d"),
            ],
        )
    return None


def _scene(name: str, objects: list[dict[str, Any]]) -> dict[str, Any]:
    return {"name": name, "objects": objects, "approximate": False}


def _part(
    shape: str,
    *,
    position: tuple[float, float, float] = (0, 0, 0),
    rotation: tuple[float, float, float] = (0, 0, 0),
    scale: tuple[float, float, float] = (1, 1, 1),
    color: str = "#55e6a2",
) -> dict[str, Any]:
    return {"shape": shape, "position": list(position), "rotation": list(rotation), "scale": list(scale), "color": color}


def _vector(value: Any, *, default: tuple[float, float, float], low: float, high: float) -> list[float]:
    raw = value if isinstance(value, list) and len(value) == 3 else list(default)
    output = []
    for index, fallback in enumerate(default):
        item = raw[index]
        number = float(item) if isinstance(item, (int, float)) and math.isfinite(float(item)) else float(fallback)
        output.append(round(max(low, min(high, number)), 5))
    return output


def _color(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text.lower() if re.fullmatch(r"#[0-9a-fA-F]{6}", text) else fallback


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Model generator did not return a JSON object.")
    return payload
