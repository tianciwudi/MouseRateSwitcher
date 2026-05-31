"""
游戏轮询率自动切换工具
- 检测到游戏运行 → 切换轮询率到 1000Hz
- 游戏退出 → 切换回 250Hz
- 系统托盘图标，后台运行
- 支持开机自启注册/取消
"""

import configparser
import os
import subprocess
import sys
import threading
import time
import winreg

import hid
from winotify import Notification, audio
from PIL import Image, ImageDraw
import pystray

# ============ 默认配置 ============
DEFAULT_GAME_PROCESSES = [
    "LeagueClientUx.exe",
    "VALORANT-Win64-Shipping.exe",
    "cs2.exe",
    "TslGame.exe",
    "ApexLegends.exe",
    "Overwatch.exe",
]

RATE_GAMING = 3    # 1000Hz
RATE_IDLE = 1      # 250Hz
CHECK_INTERVAL = 3

# 运行时配置 (由 load_config 填充)
GAME_PROCESS_NAMES = list(DEFAULT_GAME_PROCESSES)


def get_app_dir():
    """获取 exe/脚本 所在目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_FILENAME = "config.ini"


def load_config():
    """读取同目录下 config.ini, 不存在则用默认值并自动创建"""
    global RATE_GAMING, RATE_IDLE, CHECK_INTERVAL, GAME_PROCESS_NAMES

    config = configparser.ConfigParser()
    config_path = os.path.join(get_app_dir(), CONFIG_FILENAME)

    if os.path.exists(config_path):
        config.read(config_path, encoding="utf-8")
    else:
        # 首次运行, 生成默认配置文件
        write_default_config(config_path)
        return

    # 读取轮询率
    rate_hz_map = {"125": 0, "250": 1, "500": 2, "1000": 3}
    gaming_hz = config.getint("rate", "gaming_hz", fallback=1000)
    idle_hz = config.getint("rate", "idle_hz", fallback=250)
    RATE_GAMING = rate_hz_map.get(str(gaming_hz), 3)
    RATE_IDLE = rate_hz_map.get(str(idle_hz), 1)

    CHECK_INTERVAL = config.getint("general", "check_interval", fallback=3)

    # 读取游戏进程 (支持中英文逗号)
    processes = config.get("games", "processes", fallback="")
    if processes.strip():
        GAME_PROCESS_NAMES = [p.strip() for p in processes.replace("，", ",").split(",") if p.strip()]


def write_default_config(path):
    """生成默认配置文件"""
    content = """\
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
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

USAGE = 0x10
USAGE_PAGE = 0xFF01

RATE_NAMES = {0: "125Hz", 1: "250Hz", 2: "500Hz", 3: "1000Hz"}

REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_NAME = "MouseRateSwitcher"

# 全局状态
dev_info = None
current_state = "idle"
monitor_thread = None
stop_event = threading.Event()
tray_icon = None


# ============ 开机自启 ============

def get_exe_path():
    """获取当前 exe 路径 (PyInstaller 打包后为 exe, 否则为脚本)"""
    if getattr(sys, 'frozen', False):
        return sys.executable
    return os.path.abspath(__file__)


def is_autostart_enabled():
    """检查是否已注册开机自启"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(key, REG_NAME)
        winreg.CloseKey(key)
        return val.lower() == get_exe_path().lower()
    except FileNotFoundError:
        return False
    except Exception:
        return False


def set_autostart(enable: bool):
    """注册或取消开机自启"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_WRITE)
        if enable:
            winreg.SetValueEx(key, REG_NAME, 0, winreg.REG_SZ, get_exe_path())
        else:
            try:
                winreg.DeleteValue(key, REG_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"[!] 自启设置失败: {e}")
        return False


def ensure_autostart_path():
    """如果已注册自启但路径不对，自动更新"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(key, REG_NAME)
        winreg.CloseKey(key)
        if val.lower() != get_exe_path().lower():
            set_autostart(True)
    except FileNotFoundError:
        pass
    except Exception:
        pass


# ============ 通知 ============

def notify(title: str, msg: str):
    """Windows 系统通知弹窗"""
    try:
        toast = Notification(app_id="鼠标轮询率", title=title, msg=msg, duration="short")
        toast.set_audio(audio.Default, loop=False)
        toast.show()
    except Exception:
        pass


# ============ 托盘图标 ============

def create_tray_icon_image(state="idle"):
    """创建托盘图标: 绿=闲置, 红=游戏"""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (220, 50, 50) if state == "gaming" else (50, 200, 80)
    draw.ellipse([8, 8, 56, 56], fill=color)
    draw.ellipse([16, 16, 48, 48], fill=(255, 255, 255))
    draw.ellipse([22, 22, 42, 42], fill=color)
    return img


# ============ HID 通信 ============

def find_mouse_device():
    """查找鼠标 HID 设备"""
    for dev in hid.enumerate():
        if dev.get('usage') == USAGE and dev.get('usage_page') == USAGE_PAGE:
            return dev['vendor_id'], dev['product_id'], dev['path']
    return None


def set_report_rate(vid, pid, path, rate_index):
    """设置轮询率: 0=125Hz, 1=250Hz, 2=500Hz, 3=1000Hz"""
    device = hid.device()
    try:
        device.open_path(path if isinstance(path, bytes) else path.encode())
        device.set_nonblocking(0)

        read_cmd = [0] * 65
        read_cmd[1] = 85
        read_cmd[2] = 14
        read_cmd[3] = 165
        read_cmd[4] = 11
        read_cmd[5] = 48
        read_cmd[6] = 1
        read_cmd[7] = 1
        read_cmd[8] = 1

        device.write(bytes(read_cmd))
        time.sleep(0.05)
        resp = device.read(64, 2000)

        if len(resp) < 57:
            print("[!] 读取配置失败")
            return False

        offset = 0
        if resp[0] == 0 and resp[1] == 85:
            offset = 1

        r10 = resp[10 + offset]
        if r10 == 0 or (resp[12 + offset] == 0xFF and resp[13 + offset] == 0xFF):
            print("[!] 收到无效响应数据")
            return False

        current_rate = r10 - 1
        if current_rate == rate_index:
            return True

        write_cmd = [0] * 65
        write_cmd[1] = 85
        write_cmd[2] = 15
        write_cmd[3] = 174
        write_cmd[4] = 10
        write_cmd[5] = 48
        write_cmd[6] = 1
        write_cmd[7] = 1
        write_cmd[8] = 1
        write_cmd[9] = 0
        write_cmd[10] = 0
        write_cmd[11] = rate_index + 1
        write_cmd[12] = resp[11 + offset]
        write_cmd[13] = resp[12 + offset]
        for i in range(12):
            write_cmd[14 + i] = resp[13 + offset + i]
        for i in range(6):
            write_cmd[49 + i] = resp[48 + offset + i]
        write_cmd[56] = resp[55 + offset]

        device.write(bytes(write_cmd))
        time.sleep(0.05)

        print(f"[✓] 轮询率切换: {RATE_NAMES.get(current_rate, '?')} → {RATE_NAMES.get(rate_index, '?')}")
        notify("鼠标轮询率", f"已切换至 {RATE_NAMES.get(rate_index, '?')}")
        return True

    except Exception as e:
        print(f"[!] HID 通信失败: {e}")
        return False
    finally:
        device.close()


# ============ 游戏进程检测 ============

def is_game_running():
    """检测是否有游戏进程在运行"""
    try:
        result = subprocess.run(
            ['tasklist', '/FO', 'CSV', '/NH'],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        output = result.stdout.upper()
        for name in GAME_PROCESS_NAMES:
            if name.upper() in output:
                return True
        return False
    except Exception:
        return False


# ============ 监控线程 ============

def monitor_loop():
    """监控游戏进程的后台线程"""
    global current_state
    vid, pid, path = dev_info

    while not stop_event.is_set():
        game_running = is_game_running()

        if game_running and current_state == "idle":
            print(f"[游戏启动] 切换到 {RATE_NAMES[RATE_GAMING]}...")
            set_report_rate(vid, pid, path, RATE_GAMING)
            current_state = "gaming"
            if tray_icon:
                tray_icon.icon = create_tray_icon_image("gaming")
                tray_icon.title = f"鼠标轮询率 - 游戏模式 ({RATE_NAMES[RATE_GAMING]})"

        elif not game_running and current_state == "gaming":
            print(f"[游戏退出] 切换到 {RATE_NAMES[RATE_IDLE]}...")
            set_report_rate(vid, pid, path, RATE_IDLE)
            current_state = "idle"
            if tray_icon:
                tray_icon.icon = create_tray_icon_image("idle")
                tray_icon.title = f"鼠标轮询率 - 闲置 ({RATE_NAMES[RATE_IDLE]})"

        stop_event.wait(CHECK_INTERVAL)


# ============ 托盘菜单回调 ============

def on_quit(icon, item):
    """托盘菜单: 退出"""
    global current_state
    stop_event.set()
    if current_state == "gaming" and dev_info:
        vid, pid, path = dev_info
        print("[*] 退出前恢复轮询率...")
        set_report_rate(vid, pid, path, RATE_IDLE)
    icon.stop()


def on_toggle_autostart(icon, item):
    """托盘菜单: 切换开机自启"""
    if is_autostart_enabled():
        if set_autostart(False):
            notify("鼠标轮询率", "已取消开机自启")
    else:
        if set_autostart(True):
            notify("鼠标轮询率", "已设置开机自启")


def on_status(icon, item):
    pass


def setup_tray():
    """创建系统托盘图标"""
    global tray_icon

    icon = pystray.Icon(
        name="mouse_rate",
        icon=create_tray_icon_image("idle"),
        title=f"鼠标轮询率 - 闲置 ({RATE_NAMES[RATE_IDLE]})",
        menu=pystray.Menu(
            pystray.MenuItem(
                lambda text: f"当前: {'游戏模式' if current_state == 'gaming' else '闲置'} "
                             f"({RATE_NAMES.get(RATE_GAMING if current_state == 'gaming' else RATE_IDLE, '?')})",
                on_status,
                enabled=False,
            ),
            pystray.MenuItem(
                lambda text: f"开机自启: {'✓ 已开启' if is_autostart_enabled() else '✗ 未开启'}",
                on_toggle_autostart,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", on_quit),
        ),
    )
    tray_icon = icon
    return icon


def main():
    global dev_info, monitor_thread

    # 加载配置
    load_config()

    # 修正自启路径（exe 被移动后路径会失效）
    ensure_autostart_path()

    # 查找设备
    dev_info = find_mouse_device()
    if not dev_info:
        notify("鼠标轮询率", "未找到鼠标设备!")
        print("[!] 未找到鼠标设备 (usage=0x10, usagePage=0xFF01)")
        sys.exit(1)

    vid, pid, _ = dev_info
    print(f"[✓] 找到鼠标设备: VID=0x{vid:04X} PID=0x{pid:04X}")
    print(f"[*] 监控中... 游戏中→{RATE_NAMES[RATE_GAMING]} 闲置→{RATE_NAMES[RATE_IDLE]}")

    # 启动监控线程
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()

    # 启动托盘 (主线程, 阻塞)
    tray = setup_tray()
    tray.run()


if __name__ == '__main__':
    main()
