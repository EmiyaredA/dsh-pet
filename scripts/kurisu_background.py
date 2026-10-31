"""Source backdrop checks on the true native one-pixel outer boundary.

This tests only the backdrop boundary. Enclosed hair gaps, foreground lighting
and character anatomy still require independent source review.
"""
from __future__ import annotations
import json
import subprocess
import tempfile
import numpy as np


def native_border(frame):
    if frame.ndim != 3 or frame.shape[-1] != 3 or min(frame.shape[:2]) < 2:
        raise ValueError('No complete native RGB source frame')
    # No resize or interpolation: these are the exact decoded outer pixels.
    return np.concatenate([frame[0], frame[-1], frame[:, 0], frame[:, -1]], axis=0)


def evaluate_borders(borders, color='green', *, method=None):
    if color not in {'green', 'blue'}:
        raise ValueError('Unsupported approved chroma background')
    border = np.asarray(borders, dtype=np.int16)
    if border.ndim != 3 or border.shape[-1] != 3 or not len(border) or not border.shape[1]:
        raise ValueError('No complete RGB source borders')
    test = border if color == 'green' else border[..., [0, 2, 1]]
    bg = np.median(test, axis=1)
    saturated = ((test[..., 1] >= 180) & (test[..., 0] <= 100) & (test[..., 2] <= 100)
                 & (test[..., 1]-np.maximum(test[..., 0], test[..., 2]) >= 100))
    spatial = np.abs(test-bg[:, None]).max(axis=(1, 2))
    temporal = np.abs(bg-bg[0]).max(axis=1)
    good = saturated.all(axis=1) & (spatial <= 35) & (temporal <= 24)
    failed = np.flatnonzero(~good)
    original_bg = bg if color == 'green' else bg[:, [0, 2, 1]]
    return {'method': method or 'all_frame_saturated_'+color+'_native_border_v2',
            'passed': bool(len(border) == 240 and good.all()), 'frames': len(border),
            'expected_frames': 240, 'failed_frame_count': len(failed), 'failed_frames': failed.tolist(),
            'background_rgb_min': original_bg.min(axis=0).tolist(),
            'background_rgb_max': original_bg.max(axis=0).tolist(),
            'maximum_spatial_delta': float(spatial.max()), 'maximum_temporal_delta': float(temporal.max()),
            'thresholds': {'dominant_min': 180, 'other_channels_max': 100,
                           'dominance_min': 100, 'spatial_delta_max': 35, 'temporal_delta_max': 24},
            'expected_background': '#00FF00' if color == 'green' else '#0000FF',
            'white_matte_fallback': False, 'visual_foreground_review_required': True,
            'enclosed_background_and_foreground_verified': False}


def evaluate_native_frames(frames, color='green'):
    if frames.ndim != 4 or frames.shape[-1] != 3 or not len(frames):
        raise ValueError('No complete RGB source frames')
    # Retain only border samples, not an int16 copy of the whole decoded video.
    return evaluate_borders([native_border(frame) for frame in frames], color)


def _read_frame(stream, size):
    data = bytearray()
    while len(data) < size:
        chunk = stream.read(size-len(data))
        if not chunk:
            break
        data.extend(chunk)
    if data and len(data) != size:
        raise ValueError('Incomplete native RGB background scan frame')
    return data


def scan_source_background(source, color='green', ffmpeg='ffmpeg', ffprobe='ffprobe'):
    if color not in {'green', 'blue'}:
        raise ValueError('Unsupported approved chroma background')
    probe = json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height', '-of', 'json', str(source)]))
    streams = probe.get('streams', [])
    if not streams:
        raise ValueError('No source video stream')
    width, height = streams[0].get('width'), streams[0].get('height')
    if not (type(width) is int and type(height) is int and width >= 2 and height >= 2):
        raise ValueError('Invalid native source dimensions')
    command = [ffmpeg, '-v', 'error', '-xerror', '-err_detect', 'explode', '-noautorotate',
        '-i', str(source), '-t', '10', '-an', '-vf', 'fps=24', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
    borders = []
    # stderr goes to a bounded-on-disk stream so decoder errors cannot deadlock
    # while stdout is read a frame at a time. A nonzero decoder exit is fatal.
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
        try:
            while True:
                data = _read_frame(process.stdout, width*height*3)
                if not data:
                    break
                frame = np.frombuffer(data, np.uint8).reshape(height, width, 3)
                borders.append(native_border(frame))
            code = process.wait()
            if code:
                errors.seek(0)
                raise subprocess.CalledProcessError(code, command, stderr=errors.read())
        except BaseException:
            if process.poll() is None:
                process.kill()
            process.wait()
            raise
        finally:
            process.stdout.close()
    result = evaluate_borders(borders, color)
    result.update(native_size=[width, height], boundary_pixels_per_frame=2*(width+height),
                  measurement='native_one_pixel_outer_boundary_no_spatial_resampling',
                  sampling={'duration_seconds': 10, 'fps': 24, 'expected_frames': 240})
    return result


def legacy_proxy_source_background(source, color='green', ffmpeg='ffmpeg'):
    """Historical diagnostic only. It must never decide production acceptance."""
    data = subprocess.check_output([ffmpeg, '-v', 'error', '-i', str(source), '-t', '10', '-an',
        '-vf', 'fps=24,scale=64:36:flags=area', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'])
    size = 64*36*3
    if not data or len(data) % size:
        raise ValueError('Incomplete legacy proxy background scan')
    frames = np.frombuffer(data, np.uint8).reshape(-1, 36, 64, 3)
    result = evaluate_borders([native_border(frame) for frame in frames], color,
                             method='all_frame_saturated_'+color+'_border_v1')
    result.update(legacy_proxy_diagnostic_only=True, production_acceptance_authority=False,
                  measurement='downscaled_64x36_area_proxy_boundary_may_mix_nearby_foreground')
    return result
