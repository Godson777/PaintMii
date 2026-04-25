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

VAL_CORRECTION = [
    (0,   111),
    (66,  105),
    (128,  88),
    (192,  54),
    (255,   0),
]

PALETTE_SIZE = 9

slot_picker_state = [
    {"hue_pos": 0, "sat_pos": 0, "val_pos": 111}
    for _ in range(PALETTE_SIZE)
]

palette_state = {
    "slots":       [(0, 0, 0)] * PALETTE_SIZE,
    "active_slot": 0
}

picker_initialized = False

def brightness_to_val_presses(brightness):
    brightness = max(0, min(255, brightness))
    for i in range(len(VAL_CORRECTION) - 1):
        b0, p0 = VAL_CORRECTION[i]
        b1, p1 = VAL_CORRECTION[i + 1]
        if b0 <= brightness <= b1:
            t = (brightness - b0) / (b1 - b0)
            return round(p0 + t * (p1 - p0))
    return VAL_CORRECTION[-1][1]

def rgb_to_hsv_presses(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
    hue_presses = round((1 - h) * 200) % 200
    sat_presses = round(s * 212)
    val_presses = brightness_to_val_presses(round(v * 255))
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

def close_color_picker(ctrl):
    ctrl.press(ctrl.BTN_A, hold_ms=100, gap_ms=300)

def initialize_palette(ctrl, simulate=False):
    global picker_initialized
    for slot in range(PALETTE_SIZE):
        ctrl.press(ctrl.BTN_Y, hold_ms=100, gap_ms=300)
        delta = slot - palette_state["active_slot"]
        if delta > 0:
            ctrl.move(ctrl.DPAD_DOWN, delta)
        elif delta < 0:
            ctrl.move(ctrl.DPAD_UP, abs(delta))
        ctrl.press(ctrl.BTN_Y, hold_ms=100, gap_ms=500)
        if not picker_initialized:
            ctrl.press(ctrl.BTN_R, hold_ms=100, gap_ms=300)
            picker_initialized = True
        ctrl.move(ctrl.DPAD_DOWN, 111)
        close_color_picker(ctrl)
        palette_state["slots"][slot]       = (0, 0, 0)
        palette_state["active_slot"]       = slot
        slot_picker_state[slot]["hue_pos"] = 0
        slot_picker_state[slot]["sat_pos"] = 0
        slot_picker_state[slot]["val_pos"] = 111

def fill_palette_slot(ctrl, slot, r, g, b):
    ctrl.press(ctrl.BTN_Y, hold_ms=100, gap_ms=300)
    delta = slot - palette_state["active_slot"]
    if delta > 0:
        ctrl.move(ctrl.DPAD_DOWN, delta)
    elif delta < 0:
        ctrl.move(ctrl.DPAD_UP, abs(delta))
    ctrl.press(ctrl.BTN_Y, hold_ms=100, gap_ms=500)
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
# Drawing
# ============================================================

def draw_batch_snake(ctrl, grids, cursor_pos, progress=None, row_task=None, batch_pixels=0, simulate=False):
    going_right = True
    pixels_painted = 0

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

    if first_row is None:
        return

    for row_y in range(first_row, last_row + 1):
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
                    run_end = x - 1
                    all_runs.append((run_start, run_end, slot))
                else:
                    x += 1

        if not all_runs:
            if progress:
                progress.advance(row_task)
            continue

        all_runs.sort(key=lambda r: r[0], reverse=not going_right)
        move_to(ctrl, cursor_pos[0], row_y, cursor_pos, simulate=simulate)

        if going_right:
            for run_start, run_end, slot in all_runs:
                switch_to_palette_slot(ctrl, slot)
                approach = max(0, run_start - 1)
                move_to(ctrl, approach, row_y, cursor_pos, simulate=simulate)
                ctrl.draw_run(ctrl.DPAD_RIGHT, run_end - run_start + 1)
                cursor_pos[0] = run_end
            move_to(ctrl, all_runs[-1][1], row_y, cursor_pos, simulate=simulate)
        else:
            for run_start, run_end, slot in all_runs:
                switch_to_palette_slot(ctrl, slot)
                approach = min(CANVAS_WIDTH - 1, run_end + 1)
                move_to(ctrl, approach, row_y, cursor_pos, simulate=simulate)
                ctrl.draw_run(ctrl.DPAD_LEFT, run_end - run_start + 1)
                cursor_pos[0] = run_start
            move_to(ctrl, all_runs[-1][0], row_y, cursor_pos, simulate=simulate)

        going_right = not going_right
        if progress:
            pixels_in_row = sum(run_end - run_start + 1 for run_start, run_end, slot in all_runs)
            pixels_painted += pixels_in_row
            progress.update(row_task, description=f"Pixels: {pixels_painted}/{batch_pixels}")
            progress.advance(row_task, pixels_in_row)

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

def plan_palette_batches(color_pixels):
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



def calculate_time_estimate(color_pixels, batches, hold_ms=35, gap_ms=35):
    """Calculate time estimate by simulating the full draw process."""
    global picker_initialized, palette_state, slot_picker_state
    
    ctrl = MockController("2wicc", hold_ms=hold_ms, gap_ms=gap_ms)
    # Simulate the drawing without showing progress and with simulate mode enabled
    draw_image(ctrl, color_pixels, batches, show_progress=False, simulate=True)
    elapsed_min = ctrl.elapsed_ms / 1000 / 60
    
    total_pixels = sum(len(v) for v in color_pixels.values())
    total_colors = len(color_pixels)
    slots_to_fill = sum(len(batch) for batch in batches)
    
    # Convert phase times from ms to seconds and minutes
    phase_breakdown = {}
    for phase_name, ms in ctrl.phase_times.items():
        seconds = ms / 1000
        phase_breakdown[phase_name] = seconds
    
    # Reset global state after simulation
    picker_initialized = False
    palette_state = {
        "slots":       [(0, 0, 0)] * PALETTE_SIZE,
        "active_slot": 0
    }
    slot_picker_state = [
        {"hue_pos": 0, "sat_pos": 0, "val_pos": 111}
        for _ in range(PALETTE_SIZE)
    ]
    
    return {
        "total_min": elapsed_min,
        "slots": slots_to_fill,
        "colors": total_colors,
        "pixels": total_pixels,
        "batches": len(batches),
        "phase_breakdown": phase_breakdown,
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
    
    table.add_row(f"[bold]Total[/bold]",
                  f"[bold]{est['total_min']:.1f} min[/bold]")
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

def draw_image(ctrl, color_pixels, batches, est=None, show_progress=True, simulate=False):
    cursor_pos  = [128, 128]
    start_time  = datetime.now()

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

            draw_batch_snake(ctrl, grids, cursor_pos, progress_context, row_task, batch_pixels, simulate=simulate)
            
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
    batches = plan_palette_batches(color_pixels)
    est     = calculate_time_estimate(color_pixels, batches,
                                      hold_ms=args.timing, gap_ms=args.timing)

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

    draw_image(ctrl, color_pixels, batches, est)

    ser.close()

if __name__ == "__main__":
    main()