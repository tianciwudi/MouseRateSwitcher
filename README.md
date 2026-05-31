# MouseRateSwitcher
MouseRateSwitcher for MCHOSE G3 V2

# MouseRateSwitcher - 鼠标轮询率自动切换工具

> ⚠️ **本工具目前仅适用于 MCHOSE G3 V2 鼠标。** 其 HID 配置协议为该型号私有协议，其他品牌/型号的鼠标无法使用。

## 项目简介

MouseRateSwitcher 是一款 Windows 后台工具，通过 HID 协议与鼠标通信，根据当前是否运行游戏自动切换鼠标轮询率（回报率）：

- **检测到游戏运行** → 自动切换到高轮询率（默认 1000Hz），获得更低的输入延迟
- **游戏退出** → 自动切回低轮询率（默认 250Hz），降低 CPU 占用和功耗

程序运行在系统托盘，无需手动操作，全程自动切换。

### 工作原理

1. 后台线程每隔数秒扫描系统进程列表，检测是否有游戏进程在运行
2. 通过 HID 设备通信（Vendor Defined 用法页）向鼠标发送配置指令，修改轮询率
3. 切换时弹出 Windows 系统通知，托盘图标颜色同步变化（绿=闲置，红=游戏）
4. 退出时自动恢复到闲置轮询率

### 兼容性说明

> 本工具的 HID 通信协议（USAGE_PAGE=0xFF01, USAGE=0x10 及指令格式）为特定鼠标固件的私有协议，仅对兼容该协议的鼠标有效。不同品牌/型号的鼠标配置协议各不相同，无法通用。

## 功能特性

- 游戏进程自动检测，轮询率自动切换
- 系统托盘图标，后台静默运行
- 开机自启（注册表方式），exe 移动后自动修正路径
- 可配置的游戏进程列表、轮询率、检测间隔
- 退出时自动恢复闲置轮询率
- Windows 系统通知弹窗

## 使用说明

### 直接运行（已打包）

1. 将 `dist/MouseRateSwitcher.exe` 放到任意目录
2. 双击运行，程序会最小化到系统托盘
3. 首次运行会在 exe 同目录下自动生成 `config.ini` 配置文件

### 托盘菜单

| 菜单项 | 说明 |
|--------|------|
| 当前: 闲置/游戏模式 (xxxHz) | 显示当前状态和轮询率（不可点击） |
| 开机自启: ✓ 已开启 / ✗ 未开启 | 点击切换开机自启的开启/关闭 |
| 退出 | 退出程序，自动恢复闲置轮询率 |

### 配置文件

程序同目录下的 `config.ini`，首次运行自动生成：

```ini
[rate]
; 游戏中轮询率 (可选: 125, 250, 500, 1000)
gaming_hz = 1000
; 闲置时轮询率 (可选: 125, 250, 500, 1000)
idle_hz = 250

[general]
; 进程检测间隔 (秒)
check_interval = 3

[games]
; 游戏进程名, 中英文逗号均可 (不区分大小写)
processes = LeagueClientUx.exe, VALORANT-Win64-Shipping.exe, cs2.exe, TslGame.exe, ApexLegends.exe, Overwatch.exe
```

#### 添加自定义游戏

在 `config.ini` 的 `processes` 字段中添加游戏的进程名，用逗号分隔。进程名可通过任务管理器查看。

示例：添加原神和永劫无间：

```ini
processes = LeagueClientUx.exe, YuanShen.exe, NarakaBladepoint.exe
```

## 从源码运行

### 环境要求

- Python 3.11+
- Windows 10/11

### 安装依赖

```bash
python -m venv .venv
.venv\Scripts\activate
pip install hid pystray Pillow winotify pyinstaller
```

### 运行

```bash
python mouse_hid.py
```

### 打包为 exe

```bash
pyinstaller --noconfirm --noconsole --onefile --name MouseRateSwitcher mouse_hid.py
```

打包产物在 `dist/MouseRateSwitcher.exe`。

## 注意事项

- 程序需要能够访问鼠标的 HID 设备
- 如果提示"未找到鼠标设备"，说明当前鼠标不支持此工具的 HID 协议
- 移动 exe 到新目录后，下次启动时会自动修正注册表中的开机自启路径
- `config.ini` 需要和 exe 在同一目录下

