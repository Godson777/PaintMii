# PaintMii

Automates drawing images in "Tomodachi Life: Living the Dream" using a [SwiCC](https://github.com/knflrpn/SwiCC_RP2040) or [2wiCC](https://github.com/knflrpn/2wiCC) device controller. This tool allows you to convert PNG images into in-game artwork automatically.

**This tool is not 100% complete; there are still a few things I'd like to change or add, but as it stands right now, it works just fine.**

> [!NOTE]
> This was tested using the Welcome Version of Living the Dream. I do not have a copy of the full game at the moment. To my understanding, the Mii creator is identical between the full game and Welcome Version, so I expect things to *just work*. Please alert me if something goes wrong.

> [!IMPORTANT]
> Tomodachi Life does not natively have semi-transparent colors; it is ***EXTREMELY*** recommended that you ensure that whatever image you are using does not make use of them, otherwise you may get some unexpected results in your import. (Alternatively, you could use `--quantize` to not only reduce the number of colors in your image, but also remove any semi-transparent pixels.)

> [!WARNING]
> **There are a couple of limitations with PaintMii:**
> 1. Tomodachi Life runs at 30FPS; as such, the game can only receive inputs so fast. Currently, PaintMii presses and releases buttons at roughly 35ms, which is slightly slower than the time it takes to render a single frame at 30FPS (roughly 33ms). Because of this, images may take a while to recreate. [For example: the crunch bar I showcased with a earlier build of PaintMii took roughly 2+ hours.](https://x.com/GodsonTM_/status/2046443974798287077?s=20) ***There is no way to send controller inputs faster than this.***
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
- `--quantize N` - Quantize image to N colors before drawing (1-32)
- `--dry-run` - Show estimate without connecting to device

> [!NOTE]
> You realistically shouldn't have to adjust timing, but it's here in case for some odd reason you're experiencing dropped inputs which will lead into a desync.

### Examples

```bash
# Paint an image with default settings
PaintMii myimage.png

# Paint with 16 colors
PaintMii myimage.png --quantize 16

# Preview before painting (dry run)
PaintMii myimage.png --dry-run

# Slower painting speed (50ms timing)
PaintMii myimage.png --timing 50
```

## Supported Image Formats

- PNG
- JPG/JPEG
- BMP
- Other formats supported by PIL

## Troubleshooting

**Device not detected:**
- Ensure the SwiCC/2wiCC is properly connected to both your PC and Nintendo Switch (or Switch 2)
- Verify the console is powered on.

## Contributing

You are more than welcome to submit issues or pull requests to improve the project. I'm sure there's still plenty of room for optimization. (For example, the painting algorithm I chose is probably not the best one, but was the one I thought worked the best for how I wanted it to work.)

## Notes

- The paint editor has resolution limitations; images may be automatically resized
- Drawing time depends on image complexity, color count, and timing settings
- Use `--dry-run` to estimate painting time before committing to the full operation

## Credits

- KnFLrPn - Creator/Author of the [SwiCC](https://github.com/knflrpn/SwiCC_RP2040) and [2wiCC](https://github.com/knflrpn/2wiCC)
- Tomodachi Life community
