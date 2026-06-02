# DeskPet

一个基于 `PySide6` 的 Windows 桌面宠物 MVP。当前版本包含透明置顶宠物窗口、逐帧动画、拖拽、点击反馈、随机移动、托盘驻留和本地 JSON 设置持久化。

## Quick Start

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Project Layout

- `main.py`: 应用入口
- `src/pet_app/`: 核心业务逻辑
- `assets/pet/`: 精灵图素材与 `manifest.json`
- `tests/`: 逻辑与冒烟测试

## Asset Contract

- `assets/pet/idle/*.png`
- `assets/pet/walk_left/*.png`
- `assets/pet/walk_right/*.png`
- `assets/pet/clicked/*.png`
- `assets/pet/dragged/*.png` 可选

如果缺少：
- `walk_left`，会由 `walk_right` 自动镜像生成
- `dragged` 或 `clicked`，会回退到 `idle`

可选 `assets/pet/manifest.json`：

```json
{
  "frame_duration_ms": 120,
  "anchor_bottom_offset": 0,
  "default_scale": 1.0,
  "hitbox_padding": 8,
  "max_display_size": 256,
  "auto_remove_background": true,
  "background_tolerance": 48,
  "drag_hold_ms": 180,
  "click_pause_ms": 400
}
```

`max_display_size` 会限制宠物显示时的最长边，避免超大原图直接铺满桌面。
`auto_remove_background` 会在图片没有透明通道时，尝试自动去掉与边缘连通的背景色。
`background_tolerance` 用来控制自动抠背景的颜色容差；如果人物边缘被误抠，可以调小一些，比如 `24` 或 `32`。
`drag_hold_ms` 会控制按住多久后才进入拖拽，默认是 `180ms`。
`click_pause_ms` 控制点击后 `clicked` 帧停留时长，默认 `400ms`。

## Packaging

```powershell
pyinstaller DeskPet.spec
```

打包产物会把 `assets/` 一起带入，源码运行和打包后运行都使用统一的资源定位逻辑。
# desk-fun
