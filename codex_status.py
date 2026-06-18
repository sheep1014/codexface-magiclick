import math
import sys
import time

import displayio
import supervisor
import terminalio
from adafruit_display_text import label
from magiclick import MagiClick
from mochi_gesture import FlipExit

try:
    from adafruit_ble import BLERadio
    from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
    from adafruit_ble.services.nordic import UARTService

    BLE_AVAILABLE = True
except ImportError:
    BLE_AVAILABLE = False


mc = MagiClick()
flip_exit = FlipExit(mc.imu)
display = mc.display
display.brightness = 1.0
display.auto_refresh = False

W = display.width
H = display.height

BG = 0
BG_DARK = 1
FEATURE = 2
ACCENT = 3
WARN = 4
SWEAT = 5

palette = displayio.Palette(6)

COLOR_KEYS = ("bg", "feature", "accent", "title", "warn", "sweat")
DEFAULT_THEME = {
    "bg": 0xEC7E1D,
    "feature": 0x161311,
    "accent": 0xA95010,
    "title": 0xF7C28E,
    "warn": 0xFFD166,
    "sweat": 0xA3E6FF,
}
current_theme = dict(DEFAULT_THEME)

bitmap = displayio.Bitmap(W, H, len(palette))
tile_grid = displayio.TileGrid(bitmap, pixel_shader=palette)
group = displayio.Group()
group.append(tile_grid)

title_label = label.Label(terminalio.FONT, text="CODEX", color=DEFAULT_THEME["title"])
title_label.anchor_point = (0.0, 0.0)
title_label.anchored_position = (6, 6)
group.append(title_label)

link_label = label.Label(terminalio.FONT, text="", color=DEFAULT_THEME["title"])
link_label.anchor_point = (1.0, 0.0)
link_label.anchored_position = (W - 6, 6)
group.append(link_label)

info_label = label.Label(terminalio.FONT, text="", color=DEFAULT_THEME["feature"])
info_label.anchor_point = (0.5, 0.0)
info_label.anchored_position = (W / 2, H - 16)
group.append(info_label)

display.root_group = group

VALID_MODES = ("idle", "working", "attention", "blocked", "off")
MODE_INDEX = {name: idx for idx, name in enumerate(VALID_MODES)}

current_mode = "idle"
info_text = ""
serial_buffer = ""
ble_buffer = ""
last_frame = time.monotonic()
frame = 0
ble = None
ble_uart = None
ble_advertisement = None


if BLE_AVAILABLE:
    try:
        ble = BLERadio()
        ble.name = "CodexFace"
        ble_uart = UARTService()
        ble_advertisement = ProvideServicesAdvertisement(ble_uart)
        ble.start_advertising(ble_advertisement)
    except Exception:
        ble = None
        ble_uart = None
        ble_advertisement = None


def clamp(value, low, high):
    return max(low, min(high, value))


def darken(color, factor=0.84):
    red = int(((color >> 16) & 0xFF) * factor)
    green = int(((color >> 8) & 0xFF) * factor)
    blue = int((color & 0xFF) * factor)
    return (red << 16) | (green << 8) | blue


def color_to_hex(color):
    return "#%06X" % (color & 0xFFFFFF)


def parse_hex_color(value):
    value = value.strip()
    if value.startswith("#"):
        value = value[1:]
    if len(value) != 6:
        return None
    try:
        return int(value, 16)
    except ValueError:
        return None


def apply_theme():
    palette[BG] = current_theme["bg"]
    palette[BG_DARK] = darken(current_theme["bg"])
    palette[FEATURE] = current_theme["feature"]
    palette[ACCENT] = current_theme["accent"]
    palette[WARN] = current_theme["warn"]
    palette[SWEAT] = current_theme["sweat"]
    title_label.color = current_theme["title"]
    link_label.color = current_theme["title"]
    info_label.color = current_theme["feature"]


def set_theme_value(name, color):
    if name not in COLOR_KEYS or color is None:
        return False
    current_theme[name] = color
    apply_theme()
    return True


def reset_theme():
    for key in COLOR_KEYS:
        current_theme[key] = DEFAULT_THEME[key]
    apply_theme()


def palette_line():
    parts = ["%s=%s" % (name, color_to_hex(current_theme[name])) for name in COLOR_KEYS]
    return "PALETTE\t" + "\t".join(parts)


def apply_palette_tokens(tokens):
    changed = False
    for token in tokens:
        if "=" not in token:
            continue
        name, raw = token.split("=", 1)
        name = name.strip().lower()
        color = parse_hex_color(raw)
        if name in COLOR_KEYS and color is not None:
            current_theme[name] = color
            changed = True
    if changed:
        apply_theme()
    return changed


def fill(color):
    bitmap.fill(color)


def rect(x, y, width, height, color):
    x0 = clamp(int(x), 0, W)
    y0 = clamp(int(y), 0, H)
    x1 = clamp(int(x + width), 0, W)
    y1 = clamp(int(y + height), 0, H)
    for yy in range(y0, y1):
        for xx in range(x0, x1):
            bitmap[xx, yy] = color


def circle(cx, cy, radius, color):
    cx = int(cx)
    cy = int(cy)
    radius = int(radius)
    rr = radius * radius
    for yy in range(cy - radius, cy + radius + 1):
        for xx in range(cx - radius, cx + radius + 1):
            if 0 <= xx < W and 0 <= yy < H:
                dx = xx - cx
                dy = yy - cy
                if dx * dx + dy * dy <= rr:
                    bitmap[xx, yy] = color


def line(x0, y0, x1, y1, color, thickness=1):
    x0 = int(x0)
    y0 = int(y0)
    x1 = int(x1)
    y1 = int(y1)
    thickness = int(thickness)
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        rect(x0 - thickness // 2, y0 - thickness // 2, thickness, thickness, color)
        if x0 == x1 and y0 == y1:
            break
        twice = err * 2
        if twice >= dy:
            err += dy
            x0 += sx
        if twice <= dx:
            err += dx
            y0 += sy


def draw_background(phase, dim=False):
    fill(BG_DARK if dim else BG)
    if not dim:
        shade = 2 + (phase % 14 > 6)
        rect(0, 0, W, shade, ACCENT)


def draw_eye_bar(x, y, width=12, height=28, color=FEATURE):
    rect(x, y, width, height, color)


def draw_closed_eye(x, y, width=16, slope=0):
    line(x, y, x + width, y + slope, FEATURE, 4)


def draw_flat_mouth(y, width=18):
    line(64 - width // 2, y, 64 + width // 2, y, FEATURE, 3)


def draw_small_mouth(y, mood=0):
    if mood > 0:
        line(56, y, 64, y + 2, FEATURE, 3)
        line(64, y + 2, 72, y, FEATURE, 3)
    elif mood < 0:
        line(56, y + 2, 64, y, FEATURE, 3)
        line(64, y, 72, y + 2, FEATURE, 3)
    else:
        draw_flat_mouth(y, 14)


def draw_sweat(x, y):
    circle(x, y, 3, SWEAT)
    line(x, y - 5, x - 3, y, SWEAT, 2)
    line(x, y - 5, x + 2, y - 1, SWEAT, 2)


def draw_idle(phase):
    bob = int(math.sin(phase / 18.0) * 1.0)
    blink = phase % 120 in (0, 1, 2, 3)
    draw_background(phase)
    if blink:
        draw_closed_eye(25, 59 + bob, 17, 0)
        draw_closed_eye(86, 59 + bob, 17, 0)
    else:
        draw_eye_bar(25, 40 + bob)
        draw_eye_bar(91, 40 + bob)
    draw_small_mouth(95 + bob, 0)


def draw_working(phase):
    bob = int(math.sin(phase / 16.0) * 1.0)
    scan = ((phase % 16) // 4) - 2
    draw_background(phase)
    draw_eye_bar(25, 42 + bob, 12, 27)
    draw_eye_bar(91, 42 + bob, 12, 27)
    rect(28 + scan, 49 + bob, 3, 9, BG)
    rect(94 + scan, 49 + bob, 3, 9, BG)
    draw_small_mouth(94 + bob, -1)
    rect(47, 103, 34, 3, FEATURE)


def draw_attention(phase):
    bob = int(math.sin(phase / 16.0) * 1.0)
    pulse = phase % 20
    draw_background(phase)
    draw_eye_bar(25, 42 + bob, 12, 27)
    draw_eye_bar(91, 42 + bob, 12, 27)
    rect(58, 92 + bob, 12, 3, FEATURE)
    if pulse < 10:
        rect(100, 32, 10, 10, WARN)
    else:
        rect(103, 35, 4, 4, WARN)


def draw_blocked(phase):
    bob = int(math.sin(phase / 14.0) * 1.0)
    draw_background(phase)
    draw_eye_bar(25, 44 + bob, 12, 26)
    draw_eye_bar(91, 44 + bob, 12, 26)
    draw_small_mouth(95 + bob, -1)
    if phase % 24 < 15:
        draw_sweat(107, 78 + (phase % 5))


def draw_off(phase):
    draw_background(phase, dim=True)
    drift = phase % 28
    draw_closed_eye(25, 59, 17, 0)
    draw_closed_eye(86, 59, 17, 0)
    draw_flat_mouth(95, 8)
    line(92, 27 - drift // 5, 102, 27 - drift // 5, ACCENT, 2)
    line(102, 27 - drift // 5, 94, 35 - drift // 5, ACCENT, 2)
    line(94, 35 - drift // 5, 104, 35 - drift // 5, ACCENT, 2)


def draw_face(mode, phase):
    if mode == "idle":
        draw_idle(phase)
    elif mode == "working":
        draw_working(phase)
    elif mode == "attention":
        draw_attention(phase)
    elif mode == "blocked":
        draw_blocked(phase)
    else:
        draw_off(phase)


def set_mode(mode):
    global current_mode
    if mode in MODE_INDEX:
        current_mode = mode
        display.brightness = 0.45 if mode == "off" else 1.0


def set_info(text):
    global info_text
    text = text.strip()
    if len(text) > 18:
        text = text[:18]
    info_text = text
    info_label.text = text


def refresh_link_label():
    if ble and ble.connected:
        link_label.text = "BT"
    else:
        link_label.text = ""


def ensure_ble_advertising():
    if ble and ble_advertisement and not ble.connected and not ble.advertising:
        try:
            ble.start_advertising(ble_advertisement)
        except Exception:
            pass


def send_ble_line(message):
    if not ble_uart or not ble or not ble.connected:
        return
    try:
        ble_uart.write((message + "\n").encode("utf-8"))
    except Exception:
        pass


def status_line():
    return "STATUS\t%s\t%s" % (current_mode, info_text)


def cycle_mode(step):
    idx = MODE_INDEX[current_mode]
    set_mode(VALID_MODES[(idx + step) % len(VALID_MODES)])


def apply_command(command, source="serial"):
    if not command:
        return

    lower = command.lower()
    if lower in MODE_INDEX:
        set_mode(lower)
        send_ble_line(status_line())
        return

    if lower.startswith("mode:"):
        mode = lower[5:].strip()
        if mode in MODE_INDEX:
            set_mode(mode)
            send_ble_line(status_line())
        return

    if lower.startswith("mode "):
        mode = lower[5:].strip()
        if mode in MODE_INDEX:
            set_mode(mode)
            send_ble_line(status_line())
        return

    if lower == "cleartext" or lower == "clear":
        set_info("")
        send_ble_line(status_line())
        return

    if lower == "palette" or lower == "colors":
        if source == "ble":
            send_ble_line(palette_line())
        return

    if lower == "palette reset" or lower == "colors reset" or lower == "resetpalette":
        reset_theme()
        send_ble_line(palette_line())
        return

    if lower.startswith("palette ") or lower.startswith("colors "):
        tokens = command.split()[1:]
        if tokens and tokens[0].lower() == "reset":
            reset_theme()
            send_ble_line(palette_line())
        elif apply_palette_tokens(tokens):
            send_ble_line(palette_line())
        return

    if lower.startswith("color "):
        parts = command.split()
        if len(parts) >= 3 and set_theme_value(parts[1].lower(), parse_hex_color(parts[2])):
            send_ble_line(palette_line())
        return

    if lower.startswith("text:"):
        set_info(command[5:])
        send_ble_line(status_line())
        return

    if lower.startswith("text "):
        set_info(command[5:])
        send_ble_line(status_line())
        return

    if lower.startswith("info:"):
        set_info(command[5:])
        send_ble_line(status_line())
        return

    if lower.startswith("info "):
        set_info(command[5:])
        send_ble_line(status_line())
        return

    if lower == "status":
        if source == "ble":
            send_ble_line(status_line())
        return

    if lower == "ping":
        if source == "ble":
            send_ble_line("PONG")


def consume_serial_command():
    global serial_buffer
    if not supervisor.runtime.serial_bytes_available:
        return
    while supervisor.runtime.serial_bytes_available:
        chunk = sys.stdin.read(1)
        if not chunk:
            break
        if chunk in ("\n", "\r"):
            command = serial_buffer.strip()
            serial_buffer = ""
            apply_command(command, "serial")
        elif 32 <= ord(chunk) <= 126 and len(serial_buffer) < 96:
            serial_buffer += chunk


def consume_ble_command():
    global ble_buffer
    if not ble or not ble_uart or not ble.connected:
        return

    waiting = ble_uart.in_waiting
    if not waiting:
        return

    chunk = ble_uart.read(waiting)
    if not chunk:
        return

    text = bytes(chunk).decode("utf-8", "ignore")
    for char in text:
        if char in ("\n", "\r"):
            command = ble_buffer.strip()
            ble_buffer = ""
            apply_command(command, "ble")
        elif 32 <= ord(char) <= 126 and len(ble_buffer) < 96:
            ble_buffer += char


apply_theme()
set_mode("idle")
refresh_link_label()
draw_face(current_mode, frame)
display.refresh()

while True:
    ensure_ble_advertising()
    refresh_link_label()
    consume_serial_command()
    consume_ble_command()

    event = mc.keys.events.get()
    if event and event.released:
        if event.key_number == 0:
            mc.exit()
        elif event.key_number == 1:
            cycle_mode(-1)
        elif event.key_number == 2:
            cycle_mode(1)

    if flip_exit.should_exit():
        mc.exit()

    now = time.monotonic()
    if now - last_frame >= 0.07:
        frame += 1
        last_frame = now
        draw_face(current_mode, frame)
        display.refresh()
