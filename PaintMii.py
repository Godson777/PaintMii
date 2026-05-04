"""
Tomodachi Life: Living the Dream - Auto Painter
Automates drawing images in the game's paint editor using a SwiCC or 2wiCC device.

Requirements:
    pip install pyserial pillow rich

Usage:
    python PaintMii.py <image.png> [options]

Options:
    --timing MS         Hold/gap timing in ms (default: 35)
    --quantize N        Quantize image to N colors before drawing (1-100)
    --dry-run           Show estimate without connecting to device
"""

import argparse
import colorsys
import signal
import sys
import time
from datetime import datetime

import serial
import serial.tools.list_ports
from PIL import Image
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

console = Console()

# ============================================================
# Device detection
# ============================================================

SWICC_VID      = 0x2E8A
SWICC_PIDS     = [0x000A, 0x0005]
SWICC_KEYWORDS = ['swicc', 'pico', 'raspberry pi']

def find_controller_port():
    """Scan serial ports for a SwiCC or 2wiCC device. Returns (port, device_type) or (None, None)."""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if port.vid == SWICC_VID and port.pid in SWICC_PIDS:
            return port.device, "auto"
        desc = (port.description or '').lower()
        mfr  = (port.manufacturer or '').lower()
        if any(kw in desc or kw in mfr for kw in SWICC_KEYWORDS):
            return port.device, "auto"
    return None, None

def detect_device_type(ser):
    """Send ID command and detect whether device is SwiCC or 2wiCC."""
    ser.write(b"+ID \n")
    time.sleep(0.3)
    response = ser.read_all().decode(errors='ignore').strip()
    if "+2wiCC" in response:
        return "2wicc"
    if "+SwiCC" in response:
        return "swicc"
    console.print("[bold red]Error:[/bold red] Device did not respond to ID command.")
    console.print("       Ensure the SwiCC/2wiCC is connected/plugged into the Switch/Switch 2,")
    console.print("       and that the console is powered on.")
    sys.exit(1)

# ============================================================
# Controller abstraction layer
# ============================================================

class Controller:
    """
    Abstracts SwiCC and 2wiCC differences behind a common interface.
    """

    BTN_Y  = 0x01
    BTN_B  = 0x02
    BTN_A  = 0x04
    BTN_X  = 0x08
    BTN_L  = 0x10
    BTN_R  = 0x20
    BTN_ZL = 0x40
    BTN_ZR = 0x80

    DPAD_UP         = 0
    DPAD_UP_RIGHT   = 1
    DPAD_RIGHT      = 2
    DPAD_DOWN_RIGHT = 3
    DPAD_DOWN       = 4
    DPAD_DOWN_LEFT  = 5
    DPAD_LEFT       = 6
    DPAD_UP_LEFT    = 7
    DPAD_NEUTRAL    = 8

    def __init__(self, ser, device_type, hold_ms=35, gap_ms=35):
        self.ser     = ser
        self.device  = device_type
        self.hold_ms = hold_ms
        self.gap_ms  = gap_ms

    def send(self, buttons=0, dpad=8):
        """Send immediate controller state."""
        if self.device == "swicc":
            self._send_swicc(buttons, dpad)
        else:
            self._send_2wicc(buttons, dpad)

    def _send_swicc(self, buttons, dpad):
        state = f"00{buttons:02X}{dpad:02X}"
        self.ser.write(f"+IMM {state}\n".encode())

    def _send_2wicc(self, buttons, dpad):
        b1 = 0
        b2 = 0
        b3 = 0
        if buttons & self.BTN_Y:  b1 |= 0x01
        if buttons & self.BTN_X:  b1 |= 0x02
        if buttons & self.BTN_B:  b1 |= 0x04
        if buttons & self.BTN_A:  b1 |= 0x08
        if buttons & self.BTN_R:  b1 |= 0x40
        if buttons & self.BTN_ZR: b1 |= 0x80
        if buttons & self.BTN_L:  b3 |= 0x40
        if buttons & self.BTN_ZL: b3 |= 0x80
        dpad_map = {
            self.DPAD_UP:         0x02,
            self.DPAD_UP_RIGHT:   0x06,
            self.DPAD_RIGHT:      0x04,
            self.DPAD_DOWN_RIGHT: 0x05,
            self.DPAD_DOWN:       0x01,
            self.DPAD_DOWN_LEFT:  0x09,
            self.DPAD_LEFT:       0x08,
            self.DPAD_UP_LEFT:    0x0A,
            self.DPAD_NEUTRAL:    0x00,
        }
        b3 |= dpad_map.get(dpad, 0x00)
        state = f"{b1:02X}{b2:02X}{b3:02X}"
        self.ser.write(f"+QD {state}\n".encode())

    def neutral(self):
        self.send()

    def press(self, buttons=0, dpad=8, hold_ms=None, gap_ms=None):
        hold = hold_ms if hold_ms is not None else self.hold_ms
        gap  = gap_ms  if gap_ms  is not None else self.gap_ms
        self.send(buttons, dpad)
        time.sleep(hold / 1000)
        self.neutral()
        time.sleep(gap / 1000)

    def move(self, dpad_dir, count, hold_ms=None, gap_ms=None):
        if count <= 0:
            return
        hold = hold_ms if hold_ms is not None else self.hold_ms
        gap  = gap_ms  if gap_ms  is not None else self.gap_ms
        self.neutral()
        time.sleep(gap / 1000)
        for _ in range(count):
            self.send(dpad=dpad_dir)
            time.sleep(hold / 1000)
            self.neutral()
            time.sleep(gap / 1000)

    def move_2d(self, dx, dy):
        if dx == 0 and dy == 0:
            return
        steps_diagonal = min(abs(dx), abs(dy))
        remaining_x    = abs(dx) - steps_diagonal
        remaining_y    = abs(dy) - steps_diagonal
        if   dx > 0 and dy < 0: diag = self.DPAD_UP_RIGHT
        elif dx > 0 and dy > 0: diag = self.DPAD_DOWN_RIGHT
        elif dx < 0 and dy > 0: diag = self.DPAD_DOWN_LEFT
        elif dx < 0 and dy < 0: diag = self.DPAD_UP_LEFT
        else:                    diag = self.DPAD_NEUTRAL
        if steps_diagonal > 0:
            self.move(diag, steps_diagonal)
        if remaining_x > 0:
            self.move(self.DPAD_RIGHT if dx > 0 else self.DPAD_LEFT, remaining_x)
        if remaining_y > 0:
            self.move(self.DPAD_DOWN if dy > 0 else self.DPAD_UP, remaining_y)

    def draw_run(self, dpad_dir, count):
        if count <= 0:
            return
        for _ in range(count):
            self.send(self.BTN_A, dpad_dir)
            time.sleep(self.hold_ms / 1000)
            self.send(self.BTN_A, self.DPAD_NEUTRAL)
            time.sleep(self.gap_ms / 1000)
        self.neutral()
        time.sleep(self.gap_ms / 1000)

# ============================================================
# Graceful interrupt handling
# ============================================================

_controller_ref = None

def _signal_handler(sig, frame):
    console.print("\n\n[bold red]Interrupted![/bold red] Sending neutral state and exiting...")
    if _controller_ref is not None:
        try:
            _controller_ref.neutral()
        except Exception:
            pass
    sys.exit(0)

signal.signal(signal.SIGINT, _signal_handler)

# ============================================================
# Canvas navigation
# ============================================================

CANVAS_WIDTH  = 256
CANVAS_HEIGHT = 256

def move_to(ctrl, target_x, target_y, cursor_pos, simulate=False):
    target_x = max(0, min(CANVAS_WIDTH  - 1, target_x))
    target_y = max(0, min(CANVAS_HEIGHT - 1, target_y))
    dx = target_x - cursor_pos[0]
    dy = target_y - cursor_pos[1]
    if dx == 0 and dy == 0:
        return
    ctrl.neutral()
    if not simulate:
        time.sleep(ctrl.gap_ms / 1000)
    else:
        ctrl.elapsed_ms += ctrl.gap_ms
    if dy > 0:
        ctrl.move(ctrl.DPAD_DOWN, dy)
        cursor_pos[1] = target_y
    elif dy < 0:
        ctrl.move(ctrl.DPAD_UP, abs(dy))
        cursor_pos[1] = target_y
    if dx > 0:
        ctrl.move(ctrl.DPAD_RIGHT, dx)
        cursor_pos[0] = target_x
    elif dx < 0:
        ctrl.move(ctrl.DPAD_LEFT, abs(dx))
        cursor_pos[0] = target_x

def home(ctrl, cursor_pos, simulate=False):
    ctrl.move_2d(-128, -128)
    cursor_pos[0] = 0
    cursor_pos[1] = 0

# ============================================================
# Color picker
# ============================================================
# Empirical correction tables derived by collecting colors via emulator. (Was getting much more accurate color results compared to capture card.)
# Each table maps (predicted_value -> actual_presses_needed).
# Values are interpolated linearly between data points.

VAL_CORRECTION = [
    (  0, 111),  # Black
    ( 32, 109),  # Very dark grey
    ( 64, 105),  # Dark grey
    ( 96,  98),  # Medium dark grey
    (128,  87),  # Mid grey
    (160,  72),  # Medium light grey
    (192,  51),  # Light grey
    (224,  28),  # Very light grey
    (255,   0),  # White
]

SAT_CORRECTION = [
    (  0,   0),  # No saturation
    ( 52,  99),  # ~25% saturation
    (106, 166),  # ~50% saturation
    (159, 201),  # ~75% saturation
    (212, 212),  # Full saturation
]

HUE_CORRECTION = [
    (  0,   0),  # Pure red
    ( 17,   7),  # Pink
    ( 33,  33),  # Magenta
    ( 50,  59),  # Purple
    ( 67,  67),  # Pure blue
    ( 83,  74),  # Sky blue
    (100, 100),  # Cyan
    (117, 126),  # Cyan-green
    (133, 133),  # Pure green
    (150, 141),  # Yellow-green
    (167, 167),  # Yellow
    (183, 193),  # Orange
    (200, 200),  # Pure red (end)
]

PALETTE_SIZE = 9

# Game's built-in color palette tab — 84 colors in a 7-row x 12-col grid.
# Maps RGB -> (row, col) for direct palette navigation.
# Row 0 is the TOP row, col 0 is the LEFT column.
PALETTE_COLORS = {
    (255,255,255): (0,  0), (241,240,248): (0,  1), (240,241,248): (0,  2),
    (240,248,255): (0,  3), (240,251,244): (0,  4), (240,244,239): (0,  5),
    (244,250,239): (0,  6), (253,252,239): (0,  7), (253,243,239): (0,  8),
    (250,241,239): (0,  9), (252,237,220): (0, 10), (255,  0,  0): (0, 11),
    (235,235,235): (1,  0), (208,200,233): (1,  1), (200,205,231): (1,  2),
    (200,232,253): (1,  3), (200,241,216): (1,  4), (200,218,200): (1,  5),
    (218,238,200): (1,  6), (252,249,200): (1,  7), (252,214,200): (1,  8),
    (239,201,200): (1,  9), (229,207,177): (1, 10), (255,255,  0): (1, 11),
    (213,213,212): (2,  0), (166,146,214): (2,  1), (146,158,212): (2,  2),
    (146,214,253): (2,  3), (146,230,185): (2,  4), (146,189,148): (2,  5),
    (187,225,148): (2,  6), (250,244,146): (2,  7), (249,180,146): (2,  8),
    (226,150,146): (2,  9), (203,169,119): (2, 10), (  0,255,  0): (2, 11),
    (188,188,188): (3,  0), (101,  0,195): (3,  1), (  0, 75,190): (3,  2),
    (  0,194,252): (3,  3), (  0,218,145): (3,  4), (  0,150, 22): (3,  5),
    (146,211, 22): (3,  6), (248,240,  0): (3,  7), (247,132,  0): (3,  8),
    (213, 38,  0): (3,  9), (145, 98, 13): (3, 10), (  0,255,255): (3, 11),
    (156,156,155): (4,  0), ( 85,  0,168): (4,  1), (  0, 64,165): (4,  2),
    (  0,166,216): (4,  3), (  0,188,123): (4,  4), (  0,128, 13): (4,  5),
    (125,181, 13): (4,  6), (213,206,  0): (4,  7), (212,113,  0): (4,  8),
    (182, 34,  0): (4,  9), (119, 66,  0): (4, 10), (  0,  0,255): (4, 11),
    (114,114,114): (5,  0), ( 66,  0,132): (5,  1), (  0, 50,129): (5,  2),
    (  0,131,171): (5,  3), (  0,147, 96): (5,  4), (  0,101, 13): (5,  5),
    ( 98,142, 13): (5,  6), (168,163,  0): (5,  7), (167, 88,  0): (5,  8),
    (144, 22,  0): (5,  9), ( 93, 56, 13): (5, 10), (136,  0,255): (5, 11),
    (  0,  0,  0): (6,  0), ( 34,  0, 75): (6,  1), (  0, 22, 73): (6,  2),
    (  0, 73, 98): (6,  3), (  0, 85, 53): (6,  4), (  0, 56,  0): (6,  5),
    ( 53, 81,  0): (6,  6), ( 96, 93,  0): (6,  7), ( 96, 46,  0): (6,  8),
    ( 81, 13,  0): (6,  9), ( 53, 34, 13): (6, 10), (255,  0,195): (6, 11),
}

# Default sidebar colors and their palette positions (used for init navigation)
DEFAULT_SIDEBAR = [
    (  0,   0,   0),  # Slot 0: Black
    (255, 255, 255),  # Slot 1: White
    (145,  98,  13),  # Slot 2: Brown
    (213,  38,   0),  # Slot 3: Red
    (247, 132,   0),  # Slot 4: Yellow
    (146, 211,  22),  # Slot 5: Lt green
    (  0, 150,  22),  # Slot 6: Green
    (  0,  75, 190),  # Slot 7: Blue
    (101,   0, 195),  # Slot 8: Purple
]

def nearest_palette_color(r, g, b):
    """Find the nearest palette color to (r,g,b) by Euclidean RGB distance.
    Used to predict where the palette cursor will land after setting a color
    via the Color Range tab."""
    best = min(PALETTE_COLORS.keys(),
               key=lambda c: (c[0]-r)**2 + (c[1]-g)**2 + (c[2]-b)**2)
    return PALETTE_COLORS[best]

# Global tab state — game remembers last used tab across all slots
current_tab = "palette"  # starts on palette tab by default

# Per-slot state — palette_row/col initialized from DEFAULT_SIDEBAR positions
slot_picker_state = [
    {
        "hue_pos":     0,
        "sat_pos":     0,
        "val_pos":     111,
        "palette_row": PALETTE_COLORS[DEFAULT_SIDEBAR[slot]][0],
        "palette_col": PALETTE_COLORS[DEFAULT_SIDEBAR[slot]][1],
    }
    for slot in range(PALETTE_SIZE)
]

palette_state = {
    "slots":       list(DEFAULT_SIDEBAR),
    "active_slot": 0
}

def interpolate_correction(table, value):
    """Linearly interpolate a correction table for a given input value."""
    value = max(table[0][0], min(table[-1][0], value))
    for i in range(len(table) - 1):
        x0, y0 = table[i]
        x1, y1 = table[i + 1]
        if x0 <= value <= x1:
            t = (value - x0) / (x1 - x0)
            return round(y0 + t * (y1 - y0))
    return table[-1][1]

def rgb_to_hsv_presses(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
    hue_raw = round((1 - h) * 200) % 200
    sat_raw = round(s * 212)
    val_raw = round(v * 255)
    hue_presses = interpolate_correction(HUE_CORRECTION, hue_raw)
    sat_presses = interpolate_correction(SAT_CORRECTION, sat_raw)
    val_presses = interpolate_correction(VAL_CORRECTION, val_raw)
    return hue_presses, sat_presses, val_presses

def navigate_hue(ctrl, slot, target_hue):
    current = slot_picker_state[slot]["hue_pos"]
    diff = target_hue - current
    if diff > 0:
        for _ in range(diff):
            ctrl.press(ctrl.BTN_ZR)
    elif diff < 0:
        for _ in range(abs(diff)):
            ctrl.press(ctrl.BTN_ZL)
    slot_picker_state[slot]["hue_pos"] = target_hue

def navigate_to_color(ctrl, slot, r, g, b):
    target_hue, target_sat, target_val = rgb_to_hsv_presses(r, g, b)
    slot_state = slot_picker_state[slot]
    dsat = target_sat - slot_state["sat_pos"]
    dval = target_val - slot_state["val_pos"]
    navigate_hue(ctrl, slot, target_hue)
    if dsat > 0:
        ctrl.move(ctrl.DPAD_RIGHT, dsat)
    elif dsat < 0:
        ctrl.move(ctrl.DPAD_LEFT, abs(dsat))
    if dval > 0:
        ctrl.move(ctrl.DPAD_DOWN, dval)
    elif dval < 0:
        ctrl.move(ctrl.DPAD_UP, abs(dval))
    slot_picker_state[slot]["sat_pos"] = target_sat
    slot_picker_state[slot]["val_pos"] = target_val
    # Predict where palette cursor will land if tab is switched later
    pr, pc = nearest_palette_color(r, g, b)
    slot_picker_state[slot]["palette_row"] = pr
    slot_picker_state[slot]["palette_col"] = pc

def switch_tab(ctrl, target_tab):
    """Switch between Color Palette (L) and Color Range (R) tabs."""
    global current_tab
    if current_tab == target_tab:
        return
    if target_tab == "palette":
        ctrl.press(ctrl.BTN_L, hold_ms=100, gap_ms=300)
    else:
        ctrl.press(ctrl.BTN_R, hold_ms=100, gap_ms=300)
    current_tab = target_tab

def navigate_to_palette_color(ctrl, slot, target_row, target_col):
    """Navigate palette grid from current slot position to target and confirm."""
    cur_row = slot_picker_state[slot]["palette_row"]
    cur_col = slot_picker_state[slot]["palette_col"]
    dr = target_row - cur_row
    dc = target_col - cur_col
    # NOTE: dpad down moves DOWN in the palette grid (increasing row index)
    if dr > 0:
        ctrl.move(ctrl.DPAD_DOWN, dr)
    elif dr < 0:
        ctrl.move(ctrl.DPAD_UP, abs(dr))
    if dc > 0:
        ctrl.move(ctrl.DPAD_RIGHT, dc)
    elif dc < 0:
        ctrl.move(ctrl.DPAD_LEFT, abs(dc))
    ctrl.press(ctrl.BTN_A, hold_ms=100, gap_ms=300)
    slot_picker_state[slot]["palette_row"] = target_row
    slot_picker_state[slot]["palette_col"] = target_col

def close_color_picker(ctrl):
    ctrl.press(ctrl.BTN_A, hold_ms=100, gap_ms=300)

def initialize_palette(ctrl, simulate=False):
    global current_tab
    for slot in range(PALETTE_SIZE):
        ctrl.press(ctrl.BTN_Y, hold_ms=100, gap_ms=300)
        delta = slot - palette_state["active_slot"]
        if delta > 0:
            ctrl.move(ctrl.DPAD_DOWN, delta)
        elif delta < 0:
            ctrl.move(ctrl.DPAD_UP, abs(delta))
        ctrl.press(ctrl.BTN_Y, hold_ms=100, gap_ms=500)

        # Navigate palette tab from this slot's current default color to black (6,0)
        # current_tab starts as "palette" matching the game's default
        navigate_to_palette_color(ctrl, slot, 6, 0)

        palette_state["slots"][slot]            = (0, 0, 0)
        palette_state["active_slot"]            = slot
        slot_picker_state[slot]["hue_pos"]      = 0
        slot_picker_state[slot]["sat_pos"]      = 0
        slot_picker_state[slot]["val_pos"]      = 111
        slot_picker_state[slot]["palette_row"]  = 6
        slot_picker_state[slot]["palette_col"]  = 0

def fill_palette_slot(ctrl, slot, r, g, b):
    """Fill a palette slot — uses palette tab if color exists there, otherwise HSV range tab."""
    ctrl.press(ctrl.BTN_Y, hold_ms=100, gap_ms=300)
    delta = slot - palette_state["active_slot"]
    if delta > 0:
        ctrl.move(ctrl.DPAD_DOWN, delta)
    elif delta < 0:
        ctrl.move(ctrl.DPAD_UP, abs(delta))
    ctrl.press(ctrl.BTN_Y, hold_ms=100, gap_ms=500)

    if (r, g, b) in PALETTE_COLORS:
        target_row, target_col = PALETTE_COLORS[(r, g, b)]
        switch_tab(ctrl, "palette")
        navigate_to_palette_color(ctrl, slot, target_row, target_col)
        # Store equivalent HSV presses so range tab navigation is correct if needed later
        h_press, s_press, v_press = rgb_to_hsv_presses(r, g, b)
        slot_picker_state[slot]["hue_pos"] = h_press
        slot_picker_state[slot]["sat_pos"] = s_press
        slot_picker_state[slot]["val_pos"] = v_press
    else:
        switch_tab(ctrl, "range")
        navigate_to_color(ctrl, slot, r, g, b)
        close_color_picker(ctrl)

    palette_state["slots"][slot] = (r, g, b)
    palette_state["active_slot"] = slot

def switch_to_palette_slot(ctrl, target_slot):
    if target_slot == palette_state["active_slot"]:
        return
    ctrl.press(ctrl.BTN_Y, hold_ms=100, gap_ms=150)
    delta = target_slot - palette_state["active_slot"]
    if delta > 0:
        ctrl.move(ctrl.DPAD_DOWN, delta)
    elif delta < 0:
        ctrl.move(ctrl.DPAD_UP, abs(delta))
    ctrl.press(ctrl.BTN_A, hold_ms=100, gap_ms=150)
    palette_state["active_slot"] = target_slot

# ============================================================
# Drawing algorithms
# ============================================================

def _collect_runs_for_row(grids, row_y):
    """Collect all (run_start, run_end, slot) tuples for a given row across all grids."""
    all_runs = []
    for slot, grid in grids:
        row = grid[row_y]
        if not any(row):
            continue
        first_pixel = next(x for x in range(CANVAS_WIDTH) if row[x])
        last_pixel  = next(x for x in range(CANVAS_WIDTH - 1, -1, -1) if row[x])
        x = first_pixel
        while x <= last_pixel:
            if row[x]:
                run_start = x
                while x <= last_pixel and row[x]:
                    x += 1
                all_runs.append((run_start, x - 1, slot))
            else:
                x += 1
    return all_runs

def _draw_run_at(ctrl, cursor_pos, row_y, run_start, run_end, slot, going_right, simulate):
    """Navigate to and draw a single run. Direction determined by going_right.
    Used by snake-based algorithms where traversal direction is consistent."""
    switch_to_palette_slot(ctrl, slot)
    if going_right:
        approach = max(0, run_start - 1)
        move_to(ctrl, approach, row_y, cursor_pos, simulate=simulate)
        ctrl.draw_run(ctrl.DPAD_RIGHT, run_end - run_start + 1)
        cursor_pos[0] = run_end
    else:
        approach = min(CANVAS_WIDTH - 1, run_end + 1)
        move_to(ctrl, approach, row_y, cursor_pos, simulate=simulate)
        ctrl.draw_run(ctrl.DPAD_LEFT, run_end - run_start + 1)
        cursor_pos[0] = run_start
    cursor_pos[1] = row_y

def _draw_run_freeform(ctrl, cursor_pos, run_start, run_end, row_y, slot, simulate):
    """Navigate to and draw a single run. Direction determined per-run by
    whichever approach end is closer to the current cursor (Manhattan distance).
    Used by algorithms where runs can appear in any order across the canvas,
    such as Morton curve and component routing."""
    switch_to_palette_slot(ctrl, slot)
    left_cost  = abs(cursor_pos[0] - (run_start - 1)) + abs(cursor_pos[1] - row_y)
    right_cost = abs(cursor_pos[0] - (run_end   + 1)) + abs(cursor_pos[1] - row_y)
    if left_cost <= right_cost:
        approach = max(0, run_start - 1)
        move_to(ctrl, approach, row_y, cursor_pos, simulate=simulate)
        ctrl.draw_run(ctrl.DPAD_RIGHT, run_end - run_start + 1)
        cursor_pos[0] = run_end
    else:
        approach = min(CANVAS_WIDTH - 1, run_end + 1)
        move_to(ctrl, approach, row_y, cursor_pos, simulate=simulate)
        ctrl.draw_run(ctrl.DPAD_LEFT, run_end - run_start + 1)
        cursor_pos[0] = run_start
    cursor_pos[1] = row_y

def _find_row_bounds(grids):
    """Return (first_row, last_row) with any pixels across all grids."""
    first_row = None
    last_row  = None
    for _, grid in grids:
        for y in range(CANVAS_HEIGHT):
            if any(grid[y]):
                if first_row is None or y < first_row:
                    first_row = y
                break
    for _, grid in grids:
        for y in range(CANVAS_HEIGHT - 1, -1, -1):
            if any(grid[y]):
                if last_row is None or y > last_row:
                    last_row = y
                break
    return first_row, last_row

def _update_progress(progress, row_task, all_runs, pixels_painted, batch_pixels):
    if progress is None:
        return pixels_painted
    pixels_in_row = sum(re - rs + 1 for rs, re, _ in all_runs)
    pixels_painted += pixels_in_row
    progress.update(row_task, description=f"Pixels: {pixels_painted}/{batch_pixels}")
    progress.advance(row_task, pixels_in_row)
    return pixels_painted

# --- Algorithm 1: Interleaved Row Snake (original) ---

def draw_batch_snake(ctrl, grids, cursor_pos, progress=None, row_task=None,
                     batch_pixels=0, simulate=False, component_cache=None, batch_colors=None):
    """Row-by-row snake. All colors drawn together per row, sorted by x position."""
    going_right    = True
    pixels_painted = 0
    first_row, last_row = _find_row_bounds(grids)
    if first_row is None:
        return

    for row_y in range(first_row, last_row + 1):
        all_runs = _collect_runs_for_row(grids, row_y)
        if not all_runs:
            if progress:
                progress.advance(row_task)
            continue

        all_runs.sort(key=lambda r: r[0], reverse=not going_right)
        move_to(ctrl, cursor_pos[0], row_y, cursor_pos, simulate=simulate)

        for run_start, run_end, slot in all_runs:
            _draw_run_at(ctrl, cursor_pos, row_y, run_start, run_end, slot,
                         going_right, simulate)

        # Anchor to last drawn position
        if going_right:
            move_to(ctrl, all_runs[-1][1], row_y, cursor_pos, simulate=simulate)
        else:
            move_to(ctrl, all_runs[-1][0], row_y, cursor_pos, simulate=simulate)

        going_right    = not going_right
        pixels_painted = _update_progress(progress, row_task, all_runs,
                                          pixels_painted, batch_pixels)

# --- Algorithm 2: Region-Based Snake ---

def draw_batch_region(ctrl, grids, cursor_pos, progress=None, row_task=None,
                      batch_pixels=0, simulate=False, component_cache=None, batch_colors=None):
    """Draws each color's contiguous region completely before moving to the next.
    Better for images where colors are spatially clustered."""
    pixels_painted = 0
    first_row, last_row = _find_row_bounds(grids)
    if first_row is None:
        return

    # Process one color slot at a time, snake pattern within each
    for slot, grid in grids:
        going_right = True
        for row_y in range(first_row, last_row + 1):
            row = grid[row_y]
            if not any(row):
                continue

            runs = _collect_runs_for_row([(slot, grid)], row_y)
            if not runs:
                continue

            runs.sort(key=lambda r: r[0], reverse=not going_right)
            move_to(ctrl, cursor_pos[0], row_y, cursor_pos, simulate=simulate)

            for run_start, run_end, s in runs:
                _draw_run_at(ctrl, cursor_pos, row_y, run_start, run_end, s,
                             going_right, simulate)

            if going_right:
                move_to(ctrl, runs[-1][1], row_y, cursor_pos, simulate=simulate)
            else:
                move_to(ctrl, runs[-1][0], row_y, cursor_pos, simulate=simulate)

            going_right    = not going_right
            pixels_painted = _update_progress(progress, row_task, runs,
                                              pixels_painted, batch_pixels)

# --- Algorithm 3: Greedy Nearest-Run Hybrid ---

def draw_batch_greedy(ctrl, grids, cursor_pos, progress=None, row_task=None,
                      batch_pixels=0, simulate=False, component_cache=None, batch_colors=None):
    """On each row, greedily picks the nearest undrawn run regardless of color.
    Minimizes cursor travel for images with many interleaved colors per row."""
    going_right    = True
    pixels_painted = 0
    first_row, last_row = _find_row_bounds(grids)
    if first_row is None:
        return

    for row_y in range(first_row, last_row + 1):
        all_runs = _collect_runs_for_row(grids, row_y)
        if not all_runs:
            if progress:
                progress.advance(row_task)
            continue

        move_to(ctrl, cursor_pos[0], row_y, cursor_pos, simulate=simulate)

        # Greedily pick nearest run to current cursor position
        remaining = list(all_runs)
        drawn_runs = []
        while remaining:
            cx = cursor_pos[0]
            if going_right:
                # Pick nearest run whose approach (run_start-1) is ahead of cursor
                ahead = [r for r in remaining if r[0] - 1 >= cx]
                if ahead:
                    best = min(ahead, key=lambda r: r[0] - cx)
                else:
                    # Nothing ahead — switch direction
                    going_right = not going_right
                    best = min(remaining, key=lambda r: abs(r[1] + 1 - cx))
            else:
                ahead = [r for r in remaining if r[1] + 1 <= cx]
                if ahead:
                    best = min(ahead, key=lambda r: cx - r[1])
                else:
                    going_right = not going_right
                    best = min(remaining, key=lambda r: abs(r[0] - 1 - cx))

            remaining.remove(best)
            run_start, run_end, slot = best
            _draw_run_at(ctrl, cursor_pos, row_y, run_start, run_end, slot,
                         going_right, simulate)
            drawn_runs.append(best)

        pixels_painted = _update_progress(progress, row_task, drawn_runs,
                                          pixels_painted, batch_pixels)

# --- Algorithm 4: Run-Length Adaptive ---

# A row is considered "sparse" if its pixel density is below this threshold.
# Density = total pixels in row / span from first to last pixel.
# e.g. 5 pixels spread across 200 columns = 5/200 = 0.025 (very sparse)
#      5 pixels clustered in 5 columns    = 5/5   = 1.0   (dense)
SPARSE_DENSITY_THRESHOLD = 0.15

def _row_density(all_runs):
    """Calculate pixel density for a row's runs.
    Returns (density, total_pixels, span)."""
    if not all_runs:
        return 0.0, 0, 0
    total_pixels = sum(re - rs + 1 for rs, re, _ in all_runs)
    span = all_runs[-1][1] - all_runs[0][0] + 1
    return total_pixels / span, total_pixels, span

def _draw_sparse_row(ctrl, cursor_pos, row_y, all_runs, simulate):
    """Draw a sparse row by pressing A on each individual pixel without
    using the approach trick. Minimizes travel by just moving pixel by pixel."""
    # Sort all individual pixels across all runs by x position
    pixels = []
    for run_start, run_end, slot in all_runs:
        for x in range(run_start, run_end + 1):
            pixels.append((x, slot))

    # Sort by proximity to current cursor rather than strict left-to-right
    # so we always move in the cheapest direction
    going_right = cursor_pos[0] <= pixels[len(pixels)//2][0]
    pixels.sort(key=lambda p: p[0], reverse=not going_right)

    for px, slot in pixels:
        switch_to_palette_slot(ctrl, slot)
        move_to(ctrl, px, row_y, cursor_pos, simulate=simulate)
        # Draw single pixel with A press rather than draw_run
        ctrl.press(ctrl.BTN_A, hold_ms=ctrl.hold_ms, gap_ms=ctrl.gap_ms)

def draw_batch_adaptive(ctrl, grids, cursor_pos, progress=None, row_task=None,
                        batch_pixels=0, simulate=False, component_cache=None, batch_colors=None):
    """Classifies rows as dense or sparse based on pixel density.
    Dense rows use the greedy nearest approach for efficient run drawing.
    Sparse rows defer to a separate pass using individual pixel presses
    to avoid expensive approach travel for tiny isolated runs."""
    pixels_painted = 0
    first_row, last_row = _find_row_bounds(grids)
    if first_row is None:
        return

    dense_rows  = {}  # row_y -> all_runs
    sparse_rows = {}  # row_y -> all_runs

    # Classify all rows upfront
    for row_y in range(first_row, last_row + 1):
        all_runs = _collect_runs_for_row(grids, row_y)
        if not all_runs:
            continue
        # Sort runs left to right for density calculation
        all_runs.sort(key=lambda r: r[0])
        density, total_pixels, span = _row_density(all_runs)
        if density >= SPARSE_DENSITY_THRESHOLD:
            dense_rows[row_y] = all_runs
        else:
            sparse_rows[row_y] = all_runs

    # --- Pass 1: Draw all dense rows with greedy nearest strategy ---
    going_right = True
    for row_y in range(first_row, last_row + 1):
        if row_y not in dense_rows:
            continue

        all_runs = dense_rows[row_y]
        move_to(ctrl, cursor_pos[0], row_y, cursor_pos, simulate=simulate)

        remaining  = list(all_runs)
        drawn_runs = []
        while remaining:
            cx = cursor_pos[0]
            if going_right:
                ahead = [r for r in remaining if r[0] - 1 >= cx]
                if ahead:
                    best = min(ahead, key=lambda r: r[0] - cx)
                else:
                    going_right = not going_right
                    best = min(remaining, key=lambda r: abs(r[1] + 1 - cx))
            else:
                ahead = [r for r in remaining if r[1] + 1 <= cx]
                if ahead:
                    best = min(ahead, key=lambda r: cx - r[1])
                else:
                    going_right = not going_right
                    best = min(remaining, key=lambda r: abs(r[0] - 1 - cx))

            remaining.remove(best)
            run_start, run_end, slot = best
            _draw_run_at(ctrl, cursor_pos, row_y, run_start, run_end, slot,
                         going_right, simulate)
            drawn_runs.append(best)

        going_right    = not going_right
        pixels_painted = _update_progress(progress, row_task, drawn_runs,
                                          pixels_painted, batch_pixels)

    # --- Pass 2: Draw all sparse rows with individual pixel presses ---
    # Sort sparse rows by proximity to current cursor Y to minimize travel
    sparse_row_list = sorted(sparse_rows.keys(),
                             key=lambda y: abs(y - cursor_pos[1]))

    for row_y in sparse_row_list:
        all_runs = sparse_rows[row_y]
        move_to(ctrl, cursor_pos[0], row_y, cursor_pos, simulate=simulate)
        _draw_sparse_row(ctrl, cursor_pos, row_y, all_runs, simulate)
        pixels_painted = _update_progress(progress, row_task, all_runs,
                                          pixels_painted, batch_pixels)

# --- Algorithm 5: Component-First, Route-Second ---

def _find_connected_components(grid):
    """Find connected components in a boolean grid using BFS.
    Returns list of sets of (x,y) pixel coordinates."""
    visited    = set()
    components = []

    for y in range(CANVAS_HEIGHT):
        for x in range(CANVAS_WIDTH):
            if not grid[y][x] or (x, y) in visited:
                continue
            # BFS from this pixel
            component = set()
            queue     = [(x, y)]
            while queue:
                cx, cy = queue.pop()
                if (cx, cy) in visited:
                    continue
                if cx < 0 or cx >= CANVAS_WIDTH or cy < 0 or cy >= CANVAS_HEIGHT:
                    continue
                if not grid[cy][cx]:
                    continue
                visited.add((cx, cy))
                component.add((cx, cy))
                queue.extend([
                    (cx+1, cy), (cx-1, cy),
                    (cx, cy+1), (cx, cy-1),
                ])
            if component:
                components.append(component)

    return components

def _component_centroid(component):
    """Return average (x,y) of a component's pixels."""
    xs = [p[0] for p in component]
    ys = [p[1] for p in component]
    return sum(xs)/len(xs), sum(ys)/len(ys)

def _draw_component_snake(ctrl, cursor_pos, component, slot, simulate,
                          progress=None, row_task=None, pixels_painted=0, batch_pixels=0):
    """Draw a single connected component row by row. Uses row-level snake
    direction for coherence within each row, but freeform direction per run
    since components can be approached from any cursor position."""
    if not component:
        return pixels_painted

    min_y = min(p[1] for p in component)
    max_y = max(p[1] for p in component)

    switch_to_palette_slot(ctrl, slot)
    going_right = True

    for row_y in range(min_y, max_y + 1):
        row_pixels = sorted([p[0] for p in component if p[1] == row_y])
        if not row_pixels:
            continue

        move_to(ctrl, cursor_pos[0], row_y, cursor_pos, simulate=simulate)

        # Build runs from sorted pixels
        runs = []
        run_start = row_pixels[0]
        run_end   = row_pixels[0]
        for px in row_pixels[1:]:
            if px == run_end + 1:
                run_end = px
            else:
                runs.append((run_start, run_end))
                run_start = px
                run_end   = px
        runs.append((run_start, run_end))

        if not going_right:
            runs = list(reversed(runs))

        for rs, re in runs:
            _draw_run_freeform(ctrl, cursor_pos, rs, re, row_y, slot, simulate)

        # Update progress after each row
        row_pixels_count = sum(re - rs + 1 for rs, re in runs)
        pixels_painted += row_pixels_count
        if progress:
            progress.update(row_task, description=f"Pixels: {pixels_painted}/{batch_pixels}")
            progress.advance(row_task, row_pixels_count)

        going_right = not going_right

    return pixels_painted

def draw_batch_component(ctrl, grids, cursor_pos, progress=None, row_task=None,
                         batch_pixels=0, simulate=False, component_cache=None, batch_colors=None):
    """Split each color into connected components, order components by spatial
    proximity using bucket sort, draw each with a local snake. Best for logos,
    sprites, and images with spatially separated islands of the same color."""
    pixels_painted = 0

    # Collect all components. Use cache keyed by color if available,
    # otherwise compute via BFS.
    all_components = []
    for slot, grid in grids:
        color = batch_colors[slot] if batch_colors is not None else None
        if component_cache is not None and color is not None and color in component_cache:
            components = component_cache[color]
        else:
            components = _find_connected_components(grid)
        for comp in components:
            centroid = _component_centroid(comp)
            all_components.append((centroid, comp, slot))

    if not all_components:
        return

    # Order components by spatial proximity using bucket sort (O(N) vs O(N^2) greedy).
    # Divide canvas into BUCKET_GRID x BUCKET_GRID cells, snake through cells.
    BUCKET_GRID  = 16
    BUCKET_SIZE  = CANVAS_WIDTH // BUCKET_GRID  # 16px per bucket
    buckets      = {}
    for centroid, comp, slot in all_components:
        bx  = min(int(centroid[0] // BUCKET_SIZE), BUCKET_GRID - 1)
        by  = min(int(centroid[1] // BUCKET_SIZE), BUCKET_GRID - 1)
        key = (by, bx)
        if key not in buckets:
            buckets[key] = []
        buckets[key].append((centroid, comp, slot))

    ordered = []
    for by in range(BUCKET_GRID):
        row = range(BUCKET_GRID) if by % 2 == 0 else range(BUCKET_GRID - 1, -1, -1)
        for bx in row:
            if (by, bx) in buckets:
                ordered.extend(buckets[(by, bx)])

    for centroid, component, slot in ordered:
        pixels_painted = _draw_component_snake(
            ctrl, cursor_pos, component, slot, simulate,
            progress=progress, row_task=row_task,
            pixels_painted=pixels_painted, batch_pixels=batch_pixels
        )

# --- Algorithm 6: Tiny-Island Pass ---

# Runs with pixel count at or below this are considered "tiny islands"
TINY_ISLAND_MAX_PIXELS = 3

def draw_batch_tiny_island(ctrl, grids, cursor_pos, progress=None, row_task=None,
                            batch_pixels=0, simulate=False, component_cache=None, batch_colors=None):
    """Separates tiny runs (<=TINY_ISLAND_MAX_PIXELS pixels) into a deferred
    second pass so they don't interrupt the main traversal. The main pass uses
    greedy nearest for dense runs. Best for dithered art and quantized photos
    where isolated pixels are scattered throughout."""
    pixels_painted = 0
    first_row, last_row = _find_row_bounds(grids)
    if first_row is None:
        return

    main_runs_by_row  = {}  # row_y -> [runs]
    tiny_runs_by_row  = {}  # row_y -> [runs]

    for row_y in range(first_row, last_row + 1):
        all_runs = _collect_runs_for_row(grids, row_y)
        if not all_runs:
            continue
        main = []
        tiny = []
        for rs, re, slot in all_runs:
            if re - rs + 1 <= TINY_ISLAND_MAX_PIXELS:
                tiny.append((rs, re, slot))
            else:
                main.append((rs, re, slot))
        if main:
            main_runs_by_row[row_y] = main
        if tiny:
            tiny_runs_by_row[row_y] = tiny

    # --- Pass 1: Main runs using greedy nearest ---
    going_right = True
    for row_y in range(first_row, last_row + 1):
        if row_y not in main_runs_by_row:
            continue

        all_runs = main_runs_by_row[row_y]
        move_to(ctrl, cursor_pos[0], row_y, cursor_pos, simulate=simulate)

        remaining  = list(all_runs)
        drawn_runs = []
        while remaining:
            cx = cursor_pos[0]
            if going_right:
                ahead = [r for r in remaining if r[0] - 1 >= cx]
                if ahead:
                    best = min(ahead, key=lambda r: r[0] - cx)
                else:
                    going_right = not going_right
                    best = min(remaining, key=lambda r: abs(r[1] + 1 - cx))
            else:
                ahead = [r for r in remaining if r[1] + 1 <= cx]
                if ahead:
                    best = min(ahead, key=lambda r: cx - r[1])
                else:
                    going_right = not going_right
                    best = min(remaining, key=lambda r: abs(r[0] - 1 - cx))
            remaining.remove(best)
            rs, re, slot = best
            _draw_run_at(ctrl, cursor_pos, row_y, rs, re, slot,
                         going_right, simulate)
            drawn_runs.append(best)

        going_right    = not going_right
        pixels_painted = _update_progress(progress, row_task, drawn_runs,
                                          pixels_painted, batch_pixels)

    # --- Pass 2: Tiny islands sorted by proximity to current cursor ---
    tiny_rows = sorted(tiny_runs_by_row.keys(),
                       key=lambda y: abs(y - cursor_pos[1]))

    for row_y in tiny_rows:
        all_runs = tiny_runs_by_row[row_y]
        move_to(ctrl, cursor_pos[0], row_y, cursor_pos, simulate=simulate)
        _draw_sparse_row(ctrl, cursor_pos, row_y, all_runs, simulate)
        pixels_painted = _update_progress(progress, row_task, all_runs,
                                          pixels_painted, batch_pixels)

# --- Algorithm 7: Space-Filling Curve (Morton/Z-order) ---

def _morton_encode(x, y):
    """Encode (x,y) as a Morton code (Z-order curve index).
    Interleaves the bits of x and y."""
    def spread_bits(v):
        v &= 0xFFFF
        v = (v | (v << 8)) & 0x00FF00FF
        v = (v | (v << 4)) & 0x0F0F0F0F
        v = (v | (v << 2)) & 0x33333333
        v = (v | (v << 1)) & 0x55555555
        return v
    return spread_bits(x) | (spread_bits(y) << 1)

def draw_batch_morton(ctrl, grids, cursor_pos, progress=None, row_task=None,
                      batch_pixels=0, simulate=False, component_cache=None, batch_colors=None):
    """Traverses pixels along a Morton (Z-order) space-filling curve.
    Groups adjacent pixels into runs where possible. Best as a general-purpose
    fallback for dense or noisy images where row/column structure doesn't help,
    since Morton order maximises spatial locality at every scale."""
    pixels_painted = 0

    # Collect all pixels across all slots sorted by Morton code
    all_pixels = []  # (morton_code, x, y, slot)
    for slot, grid in grids:
        for y in range(CANVAS_HEIGHT):
            for x in range(CANVAS_WIDTH):
                if grid[y][x]:
                    all_pixels.append((_morton_encode(x, y), x, y, slot))

    if not all_pixels:
        return

    all_pixels.sort(key=lambda p: p[0])

    # Group consecutive Morton-ordered pixels into horizontal runs
    # where they happen to be on the same row and adjacent in x
    runs = []  # (y, x_start, x_end, slot)
    i = 0
    while i < len(all_pixels):
        _, x, y, slot = all_pixels[i]
        run_start = x
        run_end   = x
        j = i + 1
        # Extend run while same row, same slot, and x is consecutive
        while (j < len(all_pixels) and
               all_pixels[j][2] == y and
               all_pixels[j][3] == slot and
               all_pixels[j][1] == run_end + 1):
            run_end = all_pixels[j][1]
            j += 1
        runs.append((y, run_start, run_end, slot))
        i = j

    # Draw runs in Morton order using freeform direction selection
    for row_y, rs, re, slot in runs:
        _draw_run_freeform(ctrl, cursor_pos, rs, re, row_y, slot, simulate)

        if progress:
            pixels_painted += re - rs + 1
            progress.update(row_task, description=f"Pixels: {pixels_painted}/{batch_pixels}")
            progress.advance(row_task, re - rs + 1)

# ============================================================
# Image loading and batch planning
# ============================================================

def quantize_image(img, max_colors):
    alpha     = img.split()[3]
    rgb       = img.convert("RGB")
    quantized = rgb.quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT)
    result    = quantized.convert("RGBA")
    result.putalpha(alpha)
    return result

def load_image(path, quantize_colors=None):
    try:
        img = Image.open(path).convert("RGBA")
    except FileNotFoundError:
        console.print(f"[bold red]Error:[/bold red] Image file not found: {path}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] Could not open image: {e}")
        sys.exit(1)

    if img.width != 256 or img.height != 256:
        console.print(f"[bold red]Error:[/bold red] Image must be 256×256 pixels, got {img.width}×{img.height}.")
        console.print("       Please resize your image before using this tool.")
        sys.exit(1)

    if quantize_colors is not None:
        console.print(f"[cyan]Quantizing to {quantize_colors} colors...[/cyan]")
        img = quantize_image(img, quantize_colors)
        console.print("[green]Done.[/green]")

    color_pixels = {}
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = img.getpixel((x, y))
            if a == 0:
                continue
            color = (r, g, b)
            if color not in color_pixels:
                color_pixels[color] = []
            color_pixels[color].append((x, y))

    sorted_colors = dict(sorted(color_pixels.items(),
                                key=lambda x: len(x[1]),
                                reverse=True))
    return sorted_colors, img

def hsv_distance(a, b):
    ha, sa, va = colorsys.rgb_to_hsv(a[0]/255, a[1]/255, a[2]/255)
    hb, sb, vb = colorsys.rgb_to_hsv(b[0]/255, b[1]/255, b[2]/255)
    dh = min(abs(ha - hb), 1 - abs(ha - hb))
    ds = abs(sa - sb)
    dv = abs(va - vb)
    return dh**2 + ds**2 + dv**2

def color_centroid(pixels):
    """Return the average (x, y) position of a color's pixels."""
    xs = [p[0] for p in pixels]
    ys = [p[1] for p in pixels]
    return sum(xs) / len(xs), sum(ys) / len(ys)

def spatial_distance(centroid_a, centroid_b):
    """Euclidean distance between two canvas centroids."""
    return ((centroid_a[0] - centroid_b[0])**2 +
            (centroid_a[1] - centroid_b[1])**2) ** 0.5

def plan_palette_batches_hsv(color_pixels):
    """Sort colors by HSV proximity — minimizes color picker travel time.
    Better for images where picker navigation dominates."""
    colors = list(color_pixels.keys())
    if not colors:
        return []
    remaining = colors.copy()
    current   = min(remaining,
                    key=lambda c: colorsys.rgb_to_hsv(c[0]/255, c[1]/255, c[2]/255)[2])
    sorted_colors = []
    while remaining:
        sorted_colors.append(current)
        remaining.remove(current)
        if remaining:
            current = min(remaining, key=lambda c: hsv_distance(current, c))
    return [sorted_colors[i:i+PALETTE_SIZE] for i in range(0, len(sorted_colors), PALETTE_SIZE)]

def plan_palette_batches_spatial(color_pixels):
    """Sort colors by spatial proximity of their pixel centroids — minimizes
    cursor travel between palette switches during drawing.
    Better for images where colors are spatially clustered (real-world photos,
    pixel art with distinct regions)."""
    colors = list(color_pixels.keys())
    if not colors:
        return []

    # Compute centroid for each color
    centroids = {c: color_centroid(color_pixels[c]) for c in colors}

    # Nearest-neighbor sort starting from top-left corner (0,0)
    remaining     = colors.copy()
    current_pos   = (0.0, 0.0)
    sorted_colors = []

    while remaining:
        # Pick color whose centroid is nearest to current position
        current = min(remaining,
                      key=lambda c: spatial_distance(centroids[c], current_pos))
        sorted_colors.append(current)
        remaining.remove(current)
        current_pos = centroids[current]

    return [sorted_colors[i:i+PALETTE_SIZE] for i in range(0, len(sorted_colors), PALETTE_SIZE)]

def plan_palette_batches_intra(color_pixels):
    """HSV sort across batches to minimise picker travel, then within each batch
    reorder colors by spatial centroid proximity to minimise cursor travel
    during the drawing pass. Hybrid approach that tries to get the best of both."""
    colors = list(color_pixels.keys())
    if not colors:
        return []

    # Step 1: HSV nearest-neighbor sort to form batches
    remaining = colors.copy()
    current   = min(remaining,
                    key=lambda c: colorsys.rgb_to_hsv(c[0]/255, c[1]/255, c[2]/255)[2])
    sorted_colors = []
    while remaining:
        sorted_colors.append(current)
        remaining.remove(current)
        if remaining:
            current = min(remaining, key=lambda c: hsv_distance(current, c))
    batches = [sorted_colors[i:i+PALETTE_SIZE]
               for i in range(0, len(sorted_colors), PALETTE_SIZE)]

    # Step 2: Within each batch, reorder by spatial centroid proximity
    centroids = {c: color_centroid(color_pixels[c]) for c in colors}
    reordered_batches = []
    for batch in batches:
        if len(batch) <= 1:
            reordered_batches.append(batch)
            continue
        # Nearest-neighbor sort within the batch starting from top-left
        remaining_in_batch = batch.copy()
        current_pos        = (0.0, 0.0)
        sorted_batch       = []
        while remaining_in_batch:
            nearest = min(remaining_in_batch,
                          key=lambda c: spatial_distance(centroids[c], current_pos))
            sorted_batch.append(nearest)
            remaining_in_batch.remove(nearest)
            current_pos = centroids[nearest]
        reordered_batches.append(sorted_batch)

    return reordered_batches

def plan_palette_batches(color_pixels):
    """Returns all batch plans for simulation to compare."""
    return {
        "hsv":     plan_palette_batches_hsv(color_pixels),
        "spatial": plan_palette_batches_spatial(color_pixels),
        "intra":   plan_palette_batches_intra(color_pixels),
    }

def build_color_grid(color_pixels, color):
    grid = [[False] * CANVAS_WIDTH for _ in range(CANVAS_HEIGHT)]
    for x, y in color_pixels[color]:
        grid[y][x] = True
    return grid

# ============================================================
# Mock controller for time estimation
# ============================================================

class MockController(Controller):
    """Mock controller for time estimation. Simulates without sending actual commands."""
    
    def __init__(self, device_type, hold_ms=35, gap_ms=35):
        self.device = device_type
        self.hold_ms = hold_ms
        self.gap_ms = gap_ms
        self.elapsed_ms = 0
        self.phase_times = {}
        self.current_phase = None
    
    def start_phase(self, phase_name):
        """Start tracking a new phase."""
        if self.current_phase and self.current_phase not in self.phase_times:
            self.phase_times[self.current_phase] = 0
        self.current_phase = phase_name
        self._phase_start_ms = self.elapsed_ms
    
    def end_phase(self):
        """End the current phase and record its time."""
        if self.current_phase:
            phase_duration = self.elapsed_ms - self._phase_start_ms
            if self.current_phase not in self.phase_times:
                self.phase_times[self.current_phase] = 0
            self.phase_times[self.current_phase] += phase_duration
            self.current_phase = None
    
    def send(self, buttons=0, dpad=8):
        """Mock send - no-op."""
        pass
    
    def press(self, buttons=0, dpad=8, hold_ms=None, gap_ms=None):
        hold = hold_ms if hold_ms is not None else self.hold_ms
        gap = gap_ms if gap_ms is not None else self.gap_ms
        self.elapsed_ms += hold + gap
    
    def move(self, dpad_dir, count, hold_ms=None, gap_ms=None):
        if count <= 0:
            return
        hold = hold_ms if hold_ms is not None else self.hold_ms
        gap = gap_ms if gap_ms is not None else self.gap_ms
        self.elapsed_ms += gap + (count * (hold + gap))
    
    def move_2d(self, dx, dy):
        if dx == 0 and dy == 0:
            return
        steps_diagonal = min(abs(dx), abs(dy))
        remaining_x = abs(dx) - steps_diagonal
        remaining_y = abs(dy) - steps_diagonal
        
        if steps_diagonal > 0:
            self.move(self.DPAD_NEUTRAL, steps_diagonal)
        if remaining_x > 0:
            self.move(self.DPAD_NEUTRAL, remaining_x)
        if remaining_y > 0:
            self.move(self.DPAD_NEUTRAL, remaining_y)
    
    def draw_run(self, dpad_dir, count):
        if count <= 0:
            return
        self.elapsed_ms += (count * (self.hold_ms + self.gap_ms)) + self.gap_ms
    
    def neutral(self):
        """Mock neutral - no-op."""
        pass

# ============================================================
# Time estimation simulation
# ============================================================



def calculate_time_estimate(color_pixels, batch_plans, hold_ms=35, gap_ms=35):
    """Simulate all combinations of batch plan and drawing algorithm.
    Returns the fastest combination."""
    global current_tab, palette_state, slot_picker_state

    # Precompute connected components for every color once, reused across
    # all 21 simulation combinations. Keyed by color tuple.
    color_component_cache = {}
    for color in color_pixels:
        grid = build_color_grid(color_pixels, color)
        color_component_cache[color] = _find_connected_components(grid)

    draw_algorithms = [
        ("Interleaved Snake",    draw_batch_snake),
        ("Region Snake",         draw_batch_region),
        ("Greedy Nearest",       draw_batch_greedy),
        ("Run-Length Adaptive",  draw_batch_adaptive),
        ("Component Route",      draw_batch_component),
        ("Tiny Island Pass",     draw_batch_tiny_island),
        ("Morton Curve",         draw_batch_morton),
    ]

    batch_plan_names = {
        "hsv":     "HSV Sort",
        "spatial": "Spatial Sort",
        "intra":   "Intra-Batch Sort",
    }

    best_name     = None
    best_fn       = None
    best_batches  = None
    best_ms       = None
    best_phases   = None

    for plan_key, batches in batch_plans.items():
        for algo_name, algo_fn in draw_algorithms:
            ctrl = MockController("swicc", hold_ms=hold_ms, gap_ms=gap_ms)
            draw_image(ctrl, color_pixels, batches,
                       show_progress=False, simulate=True, draw_fn=algo_fn,
                       component_cache=color_component_cache)

            elapsed = ctrl.elapsed_ms
            combo_name = f"{batch_plan_names[plan_key]} + {algo_name}"

            if best_ms is None or elapsed < best_ms:
                best_ms      = elapsed
                best_name    = combo_name
                best_fn      = algo_fn
                best_batches = batches
                best_phases  = dict(ctrl.phase_times)

            # Reset global state between simulations
            current_tab = "palette"
            palette_state = {
                "slots":       list(DEFAULT_SIDEBAR),
                "active_slot": 0
            }
            slot_picker_state = [
                {
                    "hue_pos":     0,
                    "sat_pos":     0,
                    "val_pos":     111,
                    "palette_row": PALETTE_COLORS[DEFAULT_SIDEBAR[slot]][0],
                    "palette_col": PALETTE_COLORS[DEFAULT_SIDEBAR[slot]][1],
                }
                for slot in range(PALETTE_SIZE)
            ]

    total_pixels  = sum(len(v) for v in color_pixels.values())
    total_colors  = len(color_pixels)
    slots_to_fill = sum(len(batch) for batch in best_batches)
    phase_breakdown = {k: v / 1000 for k, v in best_phases.items()}

    return {
        "total_min":       best_ms / 1000 / 60,
        "slots":           slots_to_fill,
        "colors":          total_colors,
        "pixels":          total_pixels,
        "batches":         len(best_batches),
        "phase_breakdown": phase_breakdown,
        "algorithm_name":  best_name,
        "algorithm_fn":    best_fn,
        "best_batches":    best_batches,
    }

def print_estimate(est):
    table = Table(title="  Time Estimate Breakdown", show_header=False, box=None, padding=(0, 2))
    table.add_column("Phase", style="cyan")
    table.add_column("Time", justify="right")

    phase_breakdown = est.get("phase_breakdown", {})
    if phase_breakdown:
        for phase_name, seconds in phase_breakdown.items():
            minutes = seconds / 60
            if minutes >= 1:
                table.add_row(phase_name, f"{minutes:.1f} min ({seconds:.0f}s)")
            else:
                table.add_row(phase_name, f"{seconds:.1f}s")
        table.add_row("", "")

    table.add_row("[bold]Total[/bold]",
                  f"[bold]{est['total_min']:.1f} min[/bold]")
    table.add_row("[dim]Algorithm[/dim]",
                  f"[dim]{est.get('algorithm_name', 'Unknown')}[/dim]")
    console.print(table)

# ============================================================
# Startup sequence
# ============================================================

def controller_init(ctrl, simulate=False):
    """Claim player 1 slot on the Switch."""
    if simulate and isinstance(ctrl, MockController):
        ctrl.start_phase("Initialization")
    if not simulate:
        console.print("[cyan]Claiming Player 1 slot...[/cyan]")
    #Press A to wake up, then wait a couple seconds for the console to recognize the controller and pull up the controllers menu.
    ctrl.press(ctrl.BTN_A, hold_ms=100, gap_ms=2100)
    #Press A twice to set our controller as Player 1 and exit the controllers menu.
    ctrl.press(ctrl.BTN_A, hold_ms=100, gap_ms=500)
    #After this second A press, wait a sec for the UI to go away.
    ctrl.press(ctrl.BTN_A, hold_ms=100, gap_ms=1500)
    if not simulate:
        console.print("[green]Controller initialized as Player 1.[/green]")

def startup(ctrl, simulate=False):
    """Enter the painting screen and configure the brush."""
    if not simulate:
        console.print("[cyan]Entering painting screen...[/cyan]")
    ctrl.press(ctrl.BTN_A, hold_ms=100, gap_ms=5000)
    if not simulate:
        console.print("[cyan]Setting brush to single pixel...[/cyan]")
    #Press X to set our cursor to the toolbar, press X again to enter the brush settings.
    ctrl.press(ctrl.BTN_X, hold_ms=100, gap_ms=500)
    ctrl.press(ctrl.BTN_X, hold_ms=100, gap_ms=500)
    # Move left twice to select the single pixel brush, then confirm with A and B.
    ctrl.move(ctrl.DPAD_LEFT, 2)
    ctrl.press(ctrl.BTN_A, hold_ms=100, gap_ms=300)
    ctrl.press(ctrl.BTN_B, hold_ms=100, gap_ms=300)
    if not simulate:
        console.print("[cyan]Initializing palette (all black)...[/cyan]")
    initialize_palette(ctrl, simulate=simulate)
    if not simulate:
        console.print("[green]Setup complete![/green]")

# ============================================================
# Main drawing loop
# ============================================================

def draw_image(ctrl, color_pixels, batches, est=None, show_progress=True,
               simulate=False, draw_fn=None, component_cache=None):
    """Main drawing loop. draw_fn selects which algorithm to use."""
    if draw_fn is None:
        draw_fn = draw_batch_snake  # default fallback

    cursor_pos = [128, 128]
    start_time = datetime.now()

    if simulate and isinstance(ctrl, MockController):
        ctrl.start_phase("Initialization")
    controller_init(ctrl, simulate=simulate)
    startup(ctrl, simulate=simulate)
    if simulate and isinstance(ctrl, MockController):
        ctrl.end_phase()
    home(ctrl, cursor_pos, simulate=simulate)

    if show_progress:
        progress_context = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        )
    else:
        progress_context = None
    
    if progress_context:
        progress_context.__enter__()
        progress = progress_context
        batch_task = progress.add_task("Batch 0", total=len(batches))
        row_task   = progress.add_task("Pixels 0/0", total=1)
    else:
        batch_task = None
        row_task = None

    try:
        for batch_num, batch in enumerate(batches):
            # Start palette setup phase
            if simulate and isinstance(ctrl, MockController) and batch_num == 0:
                ctrl.start_phase("Palette Setup")
            
            # Fill palette slots for this batch
            for slot, color in enumerate(batch):
                r, g, b = color
                if progress_context:
                    progress.update(batch_task,
                        description=(
                            f"[bold]Batch {batch_num+1}/{len(batches)}[/bold] — "
                            f"filling slot {slot+1}/{len(batch)} "
                            f"[rgb({r},{g},{b})]█[/rgb({r},{g},{b})] RGB({r},{g},{b})"
                        ))
                fill_palette_slot(ctrl, slot, r, g, b)
            
            # End palette setup phase after first batch
            if simulate and isinstance(ctrl, MockController) and batch_num == 0:
                ctrl.end_phase()
            
            # Start drawing phase
            if simulate and isinstance(ctrl, MockController) and batch_num == 0:
                ctrl.start_phase("Drawing")

            # Calculate total pixels in this batch
            batch_pixels = sum(len(color_pixels[color]) for color in batch)

            # Build grids
            grids = [(slot, build_color_grid(color_pixels, color))
                     for slot, color in enumerate(batch)]

            # Draw this batch
            if progress_context:
                progress.reset(row_task)
                progress.update(row_task,
                    description=f"Batch {batch_num+1} — pixels",
                    total=batch_pixels)
                progress.update(batch_task,
                    description=f"[bold]Batch {batch_num+1}/{len(batches)}[/bold] — drawing")

            draw_fn(ctrl, grids, cursor_pos, progress_context, row_task, batch_pixels,
                    simulate=simulate, component_cache=component_cache,
                    batch_colors=batch)
            
            if progress_context:
                progress.advance(batch_task)

            elapsed = datetime.now() - start_time
            if show_progress:
                console.print(
                    f"  Batch {batch_num+1}/{len(batches)} complete — "
                    f"elapsed: {str(elapsed).split('.')[0]}"
                )
        
        # End drawing phase
        if simulate and isinstance(ctrl, MockController):
            ctrl.end_phase()

        total_elapsed = datetime.now() - start_time
        if show_progress:
            console.print(f"\n[bold green]Done![/bold green] "
                          f"Total time: [cyan]{str(total_elapsed).split('.')[0]}[/cyan]")
    finally:
        if progress_context:
            progress_context.__exit__(None, None, None)

# ============================================================
# CLI and entry point
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Tomodachi Life Auto Painter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python PaintMii.py art.png
  python PaintMii.py art.png --quantize 32
  python PaintMii.py art.png --timing 40
  python PaintMii.py art.png --dry-run
        """
    )
    parser.add_argument("image",
        help="Path to a 256×256 PNG image")
    parser.add_argument("--timing", type=int, default=35, metavar="MS",
        help="Hold/gap timing in milliseconds (default: 35)")
    parser.add_argument("--quantize", type=int, metavar="N",
        help="Quantize image to N colors (1-100) before drawing")
    parser.add_argument("--dry-run", action="store_true",
        help="Show time estimate without connecting to the device")
    return parser.parse_args()

def main():
    global _controller_ref

    args = parse_args()

    if args.quantize is not None and not (1 <= args.quantize <= 100):
        console.print("[bold red]Error:[/bold red] --quantize must be between 1 and 100.")
        sys.exit(1)

    console.rule("[bold]Tomodachi Life Auto Painter[/bold]")
    console.print(f"Image:  [cyan]{args.image}[/cyan]")
    if args.quantize:
        console.print(f"Quantize to [cyan]{args.quantize}[/cyan] colors")
    if args.timing != 35:
        console.print(f"Timing: [cyan]{args.timing}ms[/cyan]")

    color_pixels, img = load_image(args.image, quantize_colors=args.quantize)
    batch_plans = plan_palette_batches(color_pixels)

    console.print("Simulating drawing strategies, please wait...")
    est     = calculate_time_estimate(color_pixels, batch_plans,
                                      hold_ms=args.timing, gap_ms=args.timing)
    batches = est["best_batches"]

    console.print(f"\nColors: [cyan]{est['colors']}[/cyan]  "
                  f"Pixels: [cyan]{est['pixels']}[/cyan]  "
                  f"Batches: [cyan]{est['batches']}[/cyan]\n")
    print_estimate(est)

    if args.dry_run:
        console.print("\n[yellow]Dry run — no device connection made.[/yellow]")
        return

    if est["colors"] > 100:
        console.print(f"\n[bold yellow]Warning:[/bold yellow] {est['colors']} unique colors — "
                      f"estimated [bold]{est['total_min']:.0f}+ minutes[/bold].")
        console.print("   Consider [bold]--quantize 64[/bold] to speed things up.")
        if console.input("Continue anyway? [y/N]: ").strip().lower() != 'y':
            console.print("Aborted.")
            return

    # Auto-detect device
    console.print("\n[cyan]Auto-detecting device...[/cyan]")
    port, _ = find_controller_port()
    if port is None:
        console.print("[bold red]Error:[/bold red] No SwiCC or 2wiCC found.")
        console.print("       Connect your device to the Switch/Switch 2 and ensure the console is powered on.")
        sys.exit(1)
    console.print(f"Found device on [cyan]{port}[/cyan]")

    # Connect at 115200 first, then upgrade to 460800 if 2wiCC
    try:
        ser = serial.Serial(port, 115200, timeout=1)
    except serial.SerialException as e:
        console.print(f"[bold red]Error:[/bold red] Could not open {port}: {e}")
        sys.exit(1)

    time.sleep(2)

    device_type = detect_device_type(ser)
    if device_type == "2wicc":
        ser.close()
        try:
            ser = serial.Serial(port, 460800, timeout=1)
        except serial.SerialException as e:
            console.print(f"[bold red]Error:[/bold red] Could not reconnect at 2wiCC baud: {e}")
            sys.exit(1)
        time.sleep(1)

    console.print(f"Device: [cyan]{device_type.upper()}[/cyan] on [cyan]{port}[/cyan]")

    ctrl            = Controller(ser, device_type, hold_ms=args.timing, gap_ms=args.timing)
    _controller_ref = ctrl

    console.print()
    console.rule("[bold yellow]IMPORTANT[/bold yellow]")
    console.print("[bold yellow]Do NOT touch your console or any controllers from this point on.[/bold yellow]")
    console.print("[bold yellow]Doing so may desync the automation and corrupt your drawing.[/bold yellow]")
    console.rule()
    console.print()
    console.input("Hover over [bold]'Add Face Paint'[/bold] in-game, then press [bold]Enter[/bold]: ")

    draw_image(ctrl, color_pixels, batches, est, draw_fn=est.get("algorithm_fn"))

    ser.close()

if __name__ == "__main__":
    main()