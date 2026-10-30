#!/usr/bin/env python3
"""Key green videos into aligned 640x360 VP9-alpha desktop-pet clips.

Requires Python 3, numpy and FFmpeg with libvpx-vp9. All paths are explicit;
no Windows-only tools, model calls, source overwrites or user-config changes.
"""
from __future__ import annotations

import argparse
from collections import deque
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

import numpy as np

WIDTH, HEIGHT, FPS = 640, 360, 24
TARGET_HEIGHT, FEET_Y = 270, 330


def key_green(rgb: np.ndarray, low: float = 12, high: float = 110) -> np.ndarray:
    """Soft green-difference matte; preserve white lace, red hair and blue eyes."""
    if not 0 <= low < high <= 255:
        raise ValueError('Key thresholds must satisfy 0 <= low < high <= 255')
    color = rgb.astype(np.float32)
    other = np.maximum(color[..., 0], color[..., 2])
    excess = color[..., 1] - other
    background = np.clip((excess - low) / (high - low), 0, 1)
    background = background * background * (3 - 2 * background)
    alpha = np.rint((1 - background) * 255).astype(np.uint8)
    # Remove residual green spill without altering non-green foreground colors.
    color[..., 1] = np.minimum(color[..., 1], other + 4)
    rgba = np.dstack((np.clip(color, 0, 255).astype(np.uint8), alpha))
    rgba[alpha == 0, :3] = 0
    return rgba


def read_frame(stream, length: int) -> bytes:
    data = bytearray()
    while len(data) < length:
        chunk = stream.read(length - len(data))
        if not chunk:
            break
        data.extend(chunk)
    if data and len(data) != length:
        raise RuntimeError('Decoder returned a truncated frame')
    return bytes(data)


def measure(alpha: np.ndarray) -> dict:
    ys, xs = np.where(alpha > 127)
    if not len(xs):
        raise ValueError('No foreground remains after keying')
    return {'box': [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1],
            'center_x': float(np.median(xs)), 'height': int(ys.max() - ys.min()) + 1,
            'feet_y': int(ys.max()) + 1}


def alignment(samples: list[dict], union: list[int], source_size: tuple[int, int]) -> dict:
    standing_height = float(np.median([x['height'] for x in samples]))
    center_x = float(np.median([x['center_x'] for x in samples]))
    feet_y = float(np.median([x['feet_y'] for x in samples]))
    scale = TARGET_HEIGHT / standing_height
    sw, sh = [max(2, round(x * scale / 2) * 2) for x in source_size]
    sx, sy = sw / source_size[0], sh / source_size[1]
    x, y = round(WIDTH / 2 - center_x * sx), round(FEET_Y - feet_y * sy)
    box = [x + union[0] * sx, y + union[1] * sy,
           x + union[2] * sx, y + union[3] * sy]
    if box[0] < 8 or box[1] < 8 or box[2] > WIDTH - 8 or box[3] > HEIGHT - 8:
        raise ValueError(f'Animation would clip after alignment: {box}; inspect source')
    return {'scaled_size': [sw, sh], 'offset': [x, y], 'content_box': box,
            'standing_height': standing_height, 'standing_center_x': center_x,
            'standing_feet_y': feet_y, 'target_height': TARGET_HEIGHT, 'target_feet_y': FEET_Y}


def probe(path: Path, ffprobe: str) -> dict:
    result = subprocess.run([ffprobe, '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,codec_name:format=duration', '-of', 'json', str(path)],
        check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    if not data.get('streams'):
        raise ValueError(f'No video stream: {path}')
    return data


def verify_endpoint_geometry(first_box,last_box):
    feet_delta=last_box[3]-first_box[3]
    height_delta=(last_box[3]-last_box[1])-(first_box[3]-first_box[1])
    if abs(feet_delta)>3 or abs(height_delta)>4:
        raise ValueError(f'Neutral endpoints change size/baseline: feet={feet_delta}px height={height_delta}px')
    return {'feet_delta_px':feet_delta,'height_delta_px':height_delta}


def verify_output(path: Path, ffmpeg: str, ffprobe: str | None = None) -> dict:
    metadata = json.loads(subprocess.check_output([ffprobe or shutil.which('ffprobe'), '-v', 'error',
        '-show_streams', '-show_format', '-of', 'json', str(path)]))
    streams = metadata['streams']
    video = [s for s in streams if s['codec_type'] == 'video']
    audio = [s for s in streams if s['codec_type'] == 'audio']
    if len(video) != 1 or audio or video[0]['codec_name'] != 'vp9' or video[0]['r_frame_rate'] != '24/1':
        raise ValueError('Output must have one 24fps VP9 video stream and no audio')
    if (video[0]['width'],video[0]['height'])!=(WIDTH,HEIGHT):
        raise ValueError('Output must be exactly 640x360')
    data = subprocess.run([ffmpeg, '-v', 'error', '-c:v', 'libvpx-vp9', '-i', str(path),
        '-f', 'rawvideo', '-pix_fmt', 'rgba', '-'], check=True, capture_output=True).stdout
    frame_size = WIDTH * HEIGHT * 4
    if not data or len(data) % frame_size:
        raise ValueError('Invalid decoded output frame length')
    frames = np.frombuffer(data, np.uint8).reshape(-1, HEIGHT, WIDTH, 4)
    if len(frames) != 240:
        raise ValueError('Output must decode to exactly 240 frames')
    alpha = frames[..., 3]
    if any(int(a.min()) != 0 or int(a.max()) != 255 for a in alpha):
        raise ValueError('Encoded output lost its alpha channel')
    boxes = [measure(a)['box'] for a in alpha]
    endpoints=verify_endpoint_geometry(boxes[0],boxes[-1])
    if any(b[0] < 4 or b[1] < 4 or b[2] > WIDTH - 4 or b[3] > HEIGHT - 4 for b in boxes):
        raise ValueError('Decoded foreground reaches output edge')
    for a, (left, top, right, bottom) in zip(alpha, boxes):
        if (a[:max(0,top-6)].max(initial=0) > 8 or a[min(HEIGHT,bottom+6):].max(initial=0) > 8
                or a[:, :max(0,left-6)].max(initial=0) > 8 or a[:, min(WIDTH,right+6):].max(initial=0) > 8):
            raise ValueError('Residual translucent background outside the foreground bounds')
    first, last = frames[0].astype(float), frames[-1].astype(float)
    mask = (first[..., 3] > 127) | (last[..., 3] > 127)
    return {'width': WIDTH, 'height': HEIGHT, 'fps': FPS, 'frames': len(frames),
            'duration_seconds': len(frames) / FPS, 'alpha_min': int(alpha.min()),
            'alpha_max': int(alpha.max()), 'first_box': boxes[0], 'last_box': boxes[-1],
            'audio_streams': 0, 'codec': 'vp9', 'all_frames_have_alpha': True,
            'endpoint_geometry':endpoints,
            'background_clear': True,
            'endpoint_rgba_mean_absolute_difference': float(np.abs(first - last)[mask].mean()),
            'transparent_fraction': float((alpha == 0).mean())}


def convert(source: Path, output: Path, ffmpeg: str, ffprobe: str,
            work_dir: Path | None, overwrite: bool, key_low: float = 12,
            key_high: float = 110, frame_matte=None, lossless: bool = False) -> dict:
    if output.exists() and not overwrite:
        raise FileExistsError(f'Output exists; use --overwrite intentionally: {output}')
    info = probe(source, ffprobe)
    stream = info['streams'][0]
    w, h = stream['width'], stream['height']
    if abs(w / h - 16 / 9) > .03:
        raise ValueError(f'Expected landscape 16:9 source, got {w}x{h}')
    output.parent.mkdir(parents=True, exist_ok=True)
    if work_dir:
        work_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='pet-key-', dir=work_dir) as temp:
        raw = Path(temp) / 'keyed.rgba'
        first, tail = [], deque(maxlen=5)
        union = [w, h, 0, 0]
        count = 0
        with tempfile.TemporaryFile() as errors:
            decoder = subprocess.Popen([ffmpeg, '-v', 'error', '-i', str(source), '-t', '10', '-an',
                '-vf', f'fps={FPS}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                stdout=subprocess.PIPE, stderr=errors)
            try:
                with raw.open('wb') as target:
                    while data := read_frame(decoder.stdout, w * h * 3):
                        rgb = np.frombuffer(data, np.uint8).reshape(h, w, 3)
                        rgba = frame_matte(rgb, count) if frame_matte else key_green(rgb, key_low, key_high)
                        item = measure(rgba[..., 3])
                        b = item['box']
                        union = [min(union[0], b[0]), min(union[1], b[1]),
                                 max(union[2], b[2]), max(union[3], b[3])]
                        if count < 5:
                            first.append(item)
                        tail.append(item)
                        target.write(rgba.tobytes())
                        count += 1
            except BaseException:
                if decoder.poll() is None:
                    decoder.terminate()
                raise
            finally:
                decoder.stdout.close()
                decoder.wait()
            rc = decoder.returncode
            if rc:
                errors.seek(0)
                raise RuntimeError(errors.read().decode(errors='replace'))
        if count != 240:
            raise ValueError(f'Expected approximately 10 seconds, got {count / FPS:.3f}')
        if union[0] <= 0 or union[1] <= 0 or union[2] >= w or union[3] >= h:
            raise ValueError(f'Source foreground touches frame boundary; possible cropped content: {union}')
        transform = alignment(first + list(tail), union, (w, h))
        sw, sh = transform['scaled_size']
        x, y = transform['offset']
        filters = (f'[0:v]scale={sw}:{sh},format=rgba[pet];'
                   f'color=c=black@0:s={WIDTH}x{HEIGHT}:r={FPS},format=rgba[bg];'
                   f'[bg][pet]overlay={x}:{y}:format=auto:shortest=1,format=yuva420p[out]')
        partial = output.with_name(output.stem + '.partial.webm')
        try:
            subprocess.run([ffmpeg, '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgba',
                '-s', f'{w}x{h}', '-r', str(FPS), '-i', str(raw), '-filter_complex', filters,
                '-map', '[out]', '-an', '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p',
                '-auto-alt-ref', '0', '-b:v', '0', '-crf', '0' if lossless else '30',
                '-lossless', '1' if lossless else '0', '-row-mt', '1',
                '-deadline', 'good', '-cpu-used', '4', '-threads', '4', str(partial)], check=True)
            verification = verify_output(partial, ffmpeg, ffprobe)
            partial.replace(output)
        finally:
            partial.unlink(missing_ok=True)
    report = {'source': source.name, 'output': output.name, 'source_size': [w, h],
              'key_thresholds': None if frame_matte else [key_low, key_high],
              'matte_method': getattr(frame_matte,'name','green_difference') if frame_matte else 'green_difference',
              'encoding_lossless': lossless,
              'source_content_union': union, 'alignment': transform, 'verification': verification}
    output.with_suffix('.report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path)
    parser.add_argument('--ffmpeg', default=shutil.which('ffmpeg'))
    parser.add_argument('--ffprobe', default=shutil.which('ffprobe'))
    parser.add_argument('--overwrite', action='store_true')
    parser.add_argument('--key-low', type=float, default=12)
    parser.add_argument('--key-high', type=float, default=110)
    args = parser.parse_args()
    if not args.ffmpeg or not args.ffprobe:
        parser.error('Provide --ffmpeg and --ffprobe or install them on PATH')
    for source in args.input:
        if not source.is_file():
            parser.error(f'Missing source: {source}')
        report = convert(source, args.output / (source.stem + '.webm'), args.ffmpeg,
                         args.ffprobe, args.work_dir, args.overwrite, args.key_low, args.key_high)
        print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
