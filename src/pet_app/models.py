from __future__ import annotations

from dataclasses import dataclass, field

from .constants import DEFAULT_FRAME_DURATION_MS, DEFAULT_SCALE


@dataclass(slots=True)
class AnimationSpec:
    frame_duration_ms: int = DEFAULT_FRAME_DURATION_MS
    anchor_bottom_offset: int = 0
    default_scale: float = DEFAULT_SCALE
    hitbox_padding: int = 8
    max_display_size: int = 256
    auto_remove_background: bool = True
    background_tolerance: int = 48
    drag_hold_ms: int = 180
    click_pause_ms: int = 400


@dataclass(slots=True)
class AppSettings:
    position_x: int = 1200
    position_y: int = 800
    movement_enabled: bool = True
    visible: bool = True
    scale: float = DEFAULT_SCALE
    muted: bool = True


@dataclass(slots=True)
class MovementSnapshot:
    x: int
    y: int
    direction: str
    moving: bool


@dataclass(slots=True)
class MotionPlan:
    moving: bool
    direction: str
    duration_ms: int
    speed: int = 0


@dataclass(slots=True)
class SpriteSet:
    animations: dict[str, list] = field(default_factory=dict)
    spec: AnimationSpec = field(default_factory=AnimationSpec)
