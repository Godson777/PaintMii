# PaintMii

Automates drawing images in "Tomodachi Life: Living the Dream" using a [SwiCC](https://github.com/knflrpn/SwiCC_RP2040) or [2wiCC](https://github.com/knflrpn/2wiCC) device controller. This tool allows you to convert PNG images into in-game artwork automatically.

**This tool is not 100% complete; there are still a few things I'd like to change or add, but as it stands right now, it works just fine.**

> [!NOTE]
> This was tested using the Welcome Version of Living the Dream. I do not have a copy of the full game at the moment. To my understanding, the Mii creator is identical between the full game and Welcome Version, so I expect things to *just work*. Please alert me if something goes wrong.

> [!IMPORTANT]
> Tomodachi Life does not natively have semi-transparent colors; it is ***EXTREMELY*** recommended that you ensure that whatever image you are using does not make use of them, otherwise you may get some unexpected results in your import. (Alternatively, you could use `--quantize` to not only reduce the number of colors in your image, but also remove any semi-transparent pixels.)

> [!WARNING]
> **There are a couple of limitations with PaintMii:**
> 1. Tomodachi Life runs at 30FPS on Switch; as such, the game can only receive inputs so fast. PaintMii presses and releases buttons at roughly 35ms, which is slightly slower than the time it takes to render a single frame at 30FPS (roughly 33ms). Because of frame rate limitations, images may take a while to recreate. [For example: the crunch bar I showcased with a earlier build of PaintMii took roughly 2+ hours.](https://x.com/GodsonTM_/status/2046443974798287077?s=20)
> 2. Due to using the D-Pad for all of its inputs, it is impossible to be 100% accurate with the color range. It's *theoretically* possible to send left stick inputs to reach 100% color accuracy but I feel it's unneccessary to pursue it. As it stands, PaintMii is already able to get *very* close to a target color to the point that it's hardly noticable.

## Requirements

- A [SwiCC](https://github.com/knflrpn/SwiCC_RP2040) or [2wiCC](https://github.com/knflrpn/2wiCC) device connected to your Nintendo Switch
- A Nintendo Switch with "Tomodachi Life: Living the Dream" installed

## Installation

1. Download the executable for your OS in the [releases page](https://github.com/Godson777/PaintMii/releases)
2. Connect your SwiCC/2wiCC device to your computer

## Usage

### Basic Usage

```bash
PaintMii <image.png>
```

### Advanced Options

```bash
PaintMii <image.png> [options]
```

**Options:**
- `--timing MS` - Button press/release timing in milliseconds (default: 35)
- `--quantize N` - Quantize image to N colors before drawing (1-32, uses dithering by default)
- `--snap [N]` - Snap to game's 84-color palette (optionally limit to N colors, uses dithering by default)
- `--no-dither` - Disable dithering for flat colors (use with `--quantize` or `--snap`)
- `--preview FILE` - Save a preview of the processed image showing what colors will be drawn
- `--dry-run` - Show estimate without connecting to device
- `--test-connection` - Test device connection and exit (no image required)

> [!NOTE]
> You realistically shouldn't have to manually adjust timing, but it's available in case you're experiencing dropped inputs which will lead to a desync. The default 35ms timing is optimized for the Switch's 30 FPS paint mode.

### Examples

```bash
# Test device connection first
PaintMii --test-connection

# Paint an image with default settings (256×256 canvas)
PaintMii myimage.png

# Paint with 16 colors
PaintMii myimage.png --quantize 16

# Snap to game palette with flat colors (no dithering)
PaintMii myimage.png --snap --no-dither

# Quantize to 8 colors with flat colors
PaintMii myimage.png --quantize 8 --no-dither --preview flat_preview.png

# Snap to game palette and save a preview
PaintMii myimage.png --snap --preview preview.png

# Preview quantized colors before painting
PaintMii myimage.png --quantize 32 --preview preview.png --dry-run

# Preview before painting (dry run)
PaintMii myimage.png --dry-run

# Slower painting speed (50ms timing)
PaintMii myimage.png --timing 50
```

### Color Processing & Preview

When you use `--quantize` or `--snap`, PaintMii reduces or adjusts the colors in your image:

- **`--quantize N`** - Reduces your image to N colors using median cut quantization with Floyd-Steinberg dithering by default
- **`--snap [N]`** - Maps colors to the game's built-in 84-color palette with dithering (optionally limited to N colors)
- **`--no-dither`** - Disables dithering for flat, solid colors. Useful for pixel art or when you want clear color boundaries instead of gradients

**Dithering vs Flat Colors:**
- **With dithering** (default): Creates smooth gradients by mixing pixels of different colors. Better for photos and images with color transitions.
- **Without dithering** (`--no-dither`): Uses solid color blocks. Better for pixel art, logos, and images where you want sharp, defined edges.

Use `--preview <filename>` to save a copy of the processed image **after** color reduction. This shows you exactly what colors will be drawn in the game, helping you decide if you need to adjust the quantization level or dithering settings.

Example workflow:
```bash
# Test different quantization levels and preview results
PaintMii myimage.png --quantize 16 --preview preview_16.png --dry-run
PaintMii myimage.png --quantize 32 --preview preview_32.png --dry-run
PaintMii myimage.png --snap 24 --preview preview_snap.png --dry-run

# Compare dithered vs flat colors
PaintMii myimage.png --snap --preview dithered.png --dry-run
PaintMii myimage.png --snap --no-dither --preview flat.png --dry-run

# Once satisfied, paint with your chosen settings
PaintMii myimage.png --quantize 32
```

## Supported Image Formats

- PNG
- JPG/JPEG
- BMP
- Other formats supported by PIL

## Troubleshooting

**Device not detected:**
- Run `PaintMii --test-connection` to verify device connectivity
- Ensure the SwiCC/2wiCC is properly connected to both your PC and Nintendo Switch (or Switch 2)
- Verify the console is powered on
- Try unplugging and replugging the USB cable

## Contributing

You are more than welcome to submit issues or pull requests to improve the project. I'm sure there's still plenty of room for optimization. (For example, the painting algorithm I chose is probably not the best one, but was the one I thought worked the best for how I wanted it to work.)

## Notes

- The paint editor has resolution limitations; images may be automatically resized
- Drawing time depends on image complexity, color count, and timing settings
- Use `--dry-run` to estimate painting time before committing to the full operation

## Credits

- KnFLrPn - Creator/Author of the [SwiCC](https://github.com/knflrpn/SwiCC_RP2040) and [2wiCC](https://github.com/knflrpn/2wiCC)
- Tomodachi Life community
