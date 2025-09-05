from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any

import yaml


@dataclass
class Origin:
    x: int
    y: int


@dataclass
class Size:
    w: int
    h: int


@dataclass
class Panel:
    id: str
    address: int
    origin: Origin
    size: Size
    orientation: str = "normal"


@dataclass
class SerialCfg:
    device: str
    baud: int
    parity: str = "none"
    data_bits: int = 8
    stop_bits: int = 1


@dataclass
class Canvas:
    width: int
    height: int


@dataclass
class DisplayConfig:
    version: int
    canvas: Canvas
    panel_size: Size
    panels: List[Panel]
    serial: SerialCfg
    fps: int = 30

    def to_dict(self) -> Dict[str, Any]:
        return json.loads(json.dumps(self, default=lambda o: o.__dict__))


def load_config(path: str | Path) -> DisplayConfig:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        if p.suffix.lower() in {".yaml", ".yml"}:
            raw = yaml.safe_load(f)
        else:
            raw = json.load(f)

    def _size(obj):
        return Size(
            w=int(obj["w"]) if "w" in obj else int(obj["width"]),
            h=int(obj["h"]) if "h" in obj else int(obj["height"]),
        )

    panels = [
        Panel(
            id=str(pn["id"]),
            address=int(pn["address"]),
            origin=Origin(x=int(pn["origin"]["x"]), y=int(pn["origin"]["y"])),
            size=_size(pn["size"]),
            orientation=str(pn.get("orientation", "normal")),
        )
        for pn in raw["panels"]
    ]

    cfg = DisplayConfig(
        version=int(raw["version"]),
        canvas=Canvas(
            width=int(raw["canvas"]["width"]), height=int(raw["canvas"]["height"])
        ),
        panel_size=Size(
            w=int(raw["panel_size"]["width"]), h=int(raw["panel_size"]["height"])
        ),
        panels=panels,
        serial=SerialCfg(
            device=str(raw.get("serial", {}).get("device", "")),
            baud=int(raw.get("serial", {}).get("baud", 0)),
            parity=str(raw.get("serial", {}).get("parity", "none")),
            data_bits=int(raw.get("serial", {}).get("data_bits", 8)),
            stop_bits=int(raw.get("serial", {}).get("stop_bits", 1)),
        ),
        fps=int(raw.get("fps", 30)),
    )

    return cfg
