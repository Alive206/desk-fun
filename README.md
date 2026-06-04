# DeskPet (desk-fun)

一个基于 `PySide6` 的 Windows 桌面宠物项目。  
当前版本包含：透明置顶宠物、随机巡航、点击/双击互动、右键道具菜单、文件拖放处理、托盘控制、跨屏移动与本地设置持久化。

## 功能概览

- 透明无边框桌宠窗口，支持拖拽与跨屏移动
- 待机/行走/点击等动作资源自动加载
- 单击、双击、三连击彩蛋（跳跃反馈）
- 右键菜单互动：摸摸、投喂、幸运签、道具箱
- 鼠标跟随模式（短时）和鼠标精灵模式
- 文件拖到宠物可触发删除流程（支持 5 秒内撤销）
- 整点提醒、开机自启动（Windows 注册表）
- 系统托盘常驻控制（显示、移动、缩放、退出）
- 本地 JSON 配置持久化（位置、缩放、统计等）

## 环境要求

- Windows 10/11
- Python `>=3.11`（推荐 Conda 环境）

## 快速开始

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

如果你使用 Conda：

```powershell
conda create -n deskpet python=3.13 -y
conda activate deskpet
pip install -r requirements.txt
python main.py
```

## 开发模式（热重载）

项目提供了简单热重载脚本，监听 `src/`、`assets/`、`main.py`、`pyproject.toml` 变更后自动重启应用：

```powershell
python tools/dev_hot_reload.py
```

## 测试

```powershell
python -m pytest -q
```

## 打包 EXE

```powershell
python -m PyInstaller DeskPet.spec
```

产物路径：

- `dist/DeskPet.exe`

`DeskPet.spec` 已包含 `assets/`，打包后可直接读取宠物资源与 `manifest.json`。

## 资源目录约定

必备（至少 `idle`）：

- `assets/pet/idle/*.png`

常用动作目录：

- `assets/pet/walk_right/*.png`
- `assets/pet/walk_left/*.png`（可省略，程序会用 `walk_right` 自动镜像）
- `assets/pet/clicked/*.png`（可省略，回退 `idle`）
- `assets/pet/dragged/*.png`（可省略，回退 `idle`）

配置文件：

- `assets/pet/manifest.json`

## 常用 manifest 字段

- `enable_frame_animation`: 是否启用逐帧循环动画
- `default_scale`: 默认缩放
- `max_display_size`: 显示最大边长（防止图片过大）
- `auto_remove_background`: 对无透明通道图片尝试自动去底
- `background_tolerance`: 自动去底颜色容差
- `drag_hold_ms`: 按住进入拖拽阈值
- `click_pause_ms`: 点击动作停留时长
- `click_dialogues` / `pet_dialogues` / `feed_dialogues` / `special_dialogues`: 对话池

## 配置文件位置

运行时设置存放在用户目录：

- `~/.deskpet/settings.json`

## 右键菜单说明

- `摸摸`: 提升心情并触发摸摸台词
- `投喂`: 大幅提升心情并触发投喂台词
- `抽今日幸运签`: 抽取当天运势签文；同一天重复点击会返回同一签
- `道具箱 -> 咖啡`: 30 秒加速巡航
- `道具箱 -> 零食`: 提升心情并短时跟随鼠标
- `道具箱 -> 玩具`: 触发高跳彩蛋动作
- `成就进度`: 查看已解锁/未解锁成就列表
- `缩放比例`: 滑杆调整宠物显示缩放
- `跟随我（5秒）`: 短时进入鼠标跟随模式
- `开启/关闭鼠标精灵模式`: 用宠物替代系统鼠标视觉
- `开启/关闭整点提醒`: 整点弹出简短提醒台词
- `开启/关闭开机自启动`: 写入或移除 Windows 自启动项
- `撤销上次删除（5秒内）`: 仅对最近一批拖放删除生效

## 安全提示

- 拖放文件到宠物会触发删除流程
- 删除前会先移动到临时目录，默认可在 5 秒内通过菜单“撤销上次删除”
- 超过撤销时间后会执行最终删除，请谨慎操作
