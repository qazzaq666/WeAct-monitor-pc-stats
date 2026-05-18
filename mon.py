#!/usr/bin/env python3
"""
Show system stats (CPU, GPU, RAM, TIME) on WeAct display.

Usage:
  python show_stats.py [--interval 1.0] [--duration 60]

If duration is omitted, the script runs until interrupted.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
import argparse

from PIL import Image, ImageDraw, ImageFont
import psutil
import serial
import weact_send_image as wsi

try:
    import GPUtil
except Exception:
    GPUtil = None


def get_gpu_usage():
    if GPUtil is None:
        return None

    gpus = GPUtil.getGPUs()

    if not gpus:
        return None

    gpu = gpus[0]
    return int(gpu.load * 100)


def draw_stats_image(
    width: int,
    height: int,
    cpu: float,
    ram_pct: float,
    gpu_pct: int | None
) -> Image.Image:

    img = Image.new('RGB', (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    try:
        label_size = max(12, min(28, height // 5))

        label_font = ImageFont.truetype(
            Path(__file__).parent
            / 'res'
            / 'fonts'
            / 'SourceHanSansCN'
            / 'SourceHanSansCN-Normal.otf',
            label_size
        )

    except Exception:
        label_font = ImageFont.load_default()

    try:
        pct_size = max(10, min(22, height // 6))

        pct_font = ImageFont.truetype(
            Path(__file__).parent
            / 'res'
            / 'fonts'
            / 'SourceHanSansCN'
            / 'SourceHanSansCN-Normal.otf',
            pct_size
        )

    except Exception:
        pct_font = ImageFont.load_default()

    pad = 4
    y = pad

    labels = [
        ('CPU', cpu, (50, 200, 50)),
        ('GPU', gpu_pct, (200, 80, 80)),
        ('RAM', ram_pct, (50, 150, 250))
    ]

    bar_h = max(6, height // 20)

    for label, val, color in labels:

        draw.text(
            (pad, y),
            label,
            fill=(255, 255, 255),
            font=label_font
        )

        try:
            lw, lh = label_font.getsize(label)

        except Exception:
            bbox = draw.textbbox((0, 0), label, font=label_font)
            lw = bbox[2] - bbox[0]
            lh = bbox[3] - bbox[1]

        pct_text = f'{int(val)}%' if val is not None else 'N/A'

        try:
            tw, th = pct_font.getsize(pct_text)

        except Exception:
            bbox = draw.textbbox((0, 0), pct_text, font=pct_font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]

        bar_x = pad + lw + 8
        bar_y = y + max(0, (lh - bar_h) // 2)

        bar_right = width - pad - tw - 6
        bar_w = max(8, bar_right - bar_x)

        draw.rectangle(
            (bar_x, bar_y, bar_x + bar_w, bar_y + bar_h),
            outline=(80, 80, 80),
            fill=(30, 30, 30)
        )

        if val is not None:
            fill_w = int(
                bar_w * (max(0, min(100, val)) / 100.0)
            )

            if fill_w > 0:
                draw.rectangle(
                    (bar_x, bar_y, bar_x + fill_w, bar_y + bar_h),
                    fill=color
                )

        draw.text(
            (width - pad - tw, y),
            pct_text,
            fill=(255, 255, 255),
            font=pct_font
        )

        y += max(lh, th, bar_h) + 6

    # FREE RAM
    mem = psutil.virtual_memory()
    gb = mem.available / (1024.0 ** 3)

    footer = f'FREE {gb:.1f}GB'

    try:
        fw, fh = label_font.getsize(footer)

    except Exception:
        bbox = draw.textbbox((0, 0), footer, font=label_font)
        fw = bbox[2] - bbox[0]
        fh = bbox[3] - bbox[1]

    footer_y = max(pad, height - pad - fh - 6)

    draw.text(
        (pad, footer_y),
        footer,
        fill=(255, 255, 255),
        font=label_font
    )

    # CURRENT TIME
    current_time = datetime.now().strftime('%H:%M:%S')

    try:
        tw, th = label_font.getsize(current_time)

    except Exception:
        bbox = draw.textbbox((0, 0), current_time, font=label_font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

    draw.text(
        (width - pad - tw, footer_y),
        current_time,
        fill=(255, 255, 255),
        font=label_font
    )

    return img


def main(argv=None):

    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--interval',
        type=float,
        default=1.0
    )

    parser.add_argument(
        '--duration',
        type=float,
        default=10.0
    )

    args = parser.parse_args(argv)

    port_name, dev_type = wsi.discover_weact_port()

    if port_name is None:
        print('WeAct device not found')
        return 2

    print('Using port', port_name)

    ser = serial.Serial(
        port_name,
        1152000,
        timeout=0.5
    )

    try:
        try:
            orient = None

            ser.write(bytearray([0x02 | 0x80, 0x0A]))

            data = ser.read(4)

            if data:
                data = bytes(b for b in data if b != 0x0A)

                if len(data) >= 1:
                    orient = data[0]

        except Exception:
            orient = None

        if dev_type == 0:
            w0, h0 = 320, 480
        else:
            w0, h0 = 80, 160

        if orient is not None and orient >= 2:
            device_w, device_h = h0, w0
        else:
            device_w, device_h = w0, h0

        print(
            f'Device resolution: '
            f'{device_w}x{device_h} '
            f'(orient={orient})'
        )

        start = time.time()

        while True:

            if (
                args.duration
                and
                (time.time() - start) > args.duration
            ):
                break

            cpu = psutil.cpu_percent(interval=None)

            mem = psutil.virtual_memory()
            ram_pct = mem.percent

            gpu_pct = get_gpu_usage()

            img = draw_stats_image(
                device_w,
                device_h,
                cpu,
                ram_pct,
                gpu_pct
            )

            rgb565 = wsi.image_to_rgb565_le(img)

            wsi.send_bitmap(
                ser,
                0,
                0,
                rgb565,
                device_w,
                device_h
            )

            time.sleep(args.interval)

    finally:
        ser.close()

    return 0


if __name__ == '__main__':
    raise SystemExit(main())