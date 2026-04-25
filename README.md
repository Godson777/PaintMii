# PaintMii

Automates drawing images in "Tomodachi Life: Living the Dream" using a [SwiCC](https://github.com/knflrpn/SwiCC_RP2040) or [2wiCC](https://github.com/knflrpn/2wiCC) device controller. This tool allows you to convert PNG images into in-game artwork automatically.

**This tool is not 100% complete, there are still a few things I'd like to change or add, but as it stands right now it works just fine.**

> [!NOTE]
> This was tested using the Welcome Version of Living the Dream. I do not have a copy of the full game at the moment. To my understanding the Mii creator is identical between the full game and Welcome Version, so I expect things to *just work*. Please alert me if something goes wrong.

> [!IMPORTANT]
> Tomodachi Life does not natively have semi-transparent colors, it is ***EXTREMELY*** recommended that you ensure that whatever image you are using does not make use of them, otherwise you may get some unexpected results in your import. (Alternatively, you could use `--quantize` to not only reduce the amount of colors in your image, but also remove any semi-transparent pixels.)
>
> Due to using the dpad for all of its inputs, it is impossible to be super accurate with the color range. If it were possible to get consistent results by sending left stick inputs, then it *could* be possible to reach full color accuracy. This would need further testing, and honestly, attempting this is rather low on my priority list at the moment.


## Requirements

- Python 3.x
- A [SwiCC](https://github.com/knflrpn/SwiCC_RP2040) or [2wiCC](https://github.com/knflrpn/2wiCC) device connected to your Nintendo Switch
- A Nintendo Switch with "Tomodachi Life: Living the Dream" installed

### Python Dependencies

```bash
pip install pyserial pillow rich
```

## Installation

1. Clone or download this repository
2. Install the required Python dependencies (see Requirements section)
3. Connect your SwiCC/2wiCC device to your computer

## Usage

### Basic Usage

```bash
python PaintMii.py <image.png>
```

### Advanced Options

```bash
python PaintMii.py <image.png> [options]
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
python PaintMii.py myimage.png

# Paint with 16 colors
python PaintMii.py myimage.png --quantize 16

# Preview before painting (dry run)
python PaintMii.py myimage.png --dry-run

# Slower painting speed (50ms timing)
python PaintMii.py myimage.png --timing 50
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
