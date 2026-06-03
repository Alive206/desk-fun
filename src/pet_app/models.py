from __future__ import annotations

from dataclasses import dataclass, field

from .constants import DEFAULT_FRAME_DURATION_MS, DEFAULT_SCALE


@dataclass(slots=True)
class AnimationSpec:
    frame_duration_ms: int = DEFAULT_FRAME_DURATION_MS
    enable_frame_animation: bool = False
    anchor_bottom_offset: int = 0
    default_scale: float = DEFAULT_SCALE
    hitbox_padding: int = 8
    max_display_size: int = 256
    auto_remove_background: bool = True
    background_tolerance: int = 48
    drag_hold_ms: int = 180
    click_pause_ms: int = 400
    click_dialogues: list[str] = field(
        default_factory=lambda: ["嗨，我在呢！", "你点到我啦~", "今天也一起玩吧！"]
    )
    click_dialog_duration_ms: int = 1600
    happy_click_dialogues: list[str] = field(
        default_factory=lambda: ["好开心！", "这个互动真有趣！", "再来一次吧！"]
    )
    bored_click_dialogues: list[str] = field(
        default_factory=lambda: ["唔，有点无聊。", "我一直陪着你。", "我们找点事情做吧。"]
    )
    sleepy_click_dialogues: list[str] = field(
        default_factory=lambda: ["呼噜呼噜……", "我有点困了。", "轻轻点我就好。"]
    )
    pet_dialogues: list[str] = field(
        default_factory=lambda: ["摸摸真舒服。", "收到你的摸摸啦！", "心情变好了！"]
    )
    feed_dialogues: list[str] = field(
        default_factory=lambda: ["好吃！", "开饭时间到！", "能量恢复啦！"]
    )
    special_dialogues: list[str] = field(
        default_factory=lambda: ["看我的！", "特殊动作启动！", "蹦一下！"]
    )


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
