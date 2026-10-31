"""Ordinary, fixed-profile BLUE color key; no semantic or palette repair.

The profile comes from the native one-pixel boundary of all 240 source frames.
Its thresholds are fixed before conversion, never searched against real footage.
Opaque matte pixels retain their source RGB bytes; only soft edges may lose blue
spill. This cannot protect foreground matching the backdrop color, infer eyes,
or repair source defects. Independent source and final visual review remain
required. VP9's YUV conversion/rescaling can change encoded RGB; byte preservation
here describes the RGB frame matte before the shared encoder/alignment.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile

import numpy as np

from build_pet_pack import convert
from kurisu_background import evaluate_borders, native_border, _read_frame

WORKER_VERSION = 'normal_blue_rgb_distance_v1'
PROCESSING_PROFILE = 'h3_u24_normal_blue_key_no_palette'
KEY_LOW, KEY_HIGH = 64.0, 110.0


@dataclass(frozen=True)
class BlueProfile:
    background_rgb: tuple[float, float, float]
    background_rgb_min: tuple[int, int, int]
    background_rgb_max: tuple[int, int, int]
    source_sha256: str | None = None
    low: float = KEY_LOW
    high: float = KEY_HIGH

    def __post_init__(self):
        vectors = [np.asarray(x, dtype=float) for x in
                   (self.background_rgb, self.background_rgb_min, self.background_rgb_max)]
        if any(x.shape != (3,) or not np.isfinite(x).all() or
               (x < 0).any() or (x > 255).any() for x in vectors):
            raise ValueError('BLUE profile requires finite three-channel RGB values')
        median, minimum, maximum = vectors
        if (minimum > median).any() or (median > maximum).any():
            raise ValueError('BLUE profile RGB median must lie inside min/max')
        if (minimum[2] < 180 or maximum[:2].max() > 100 or
                minimum[2] - maximum[:2].max() < 100):
            raise ValueError('BLUE profile is not a saturated blue background')
        if (self.low, self.high) != (KEY_LOW, KEY_HIGH):
            raise ValueError('Only the fixed BLUE distance profile 64/110 is supported')
        if self.source_sha256 is not None and (len(self.source_sha256) != 64 or
                any(c not in '0123456789abcdef' for c in self.source_sha256)):
            raise ValueError('Invalid BLUE profile source SHA256')
        for name, vector in zip(('background_rgb', 'background_rgb_min', 'background_rgb_max'), vectors):
            object.__setattr__(self, name, tuple(vector.tolist()))


def profile_from_native_borders(borders, *, source_sha256=None):
    """Freeze one global median, never a frame-varying or foreground fit."""
    border = np.asarray(borders)
    if border.dtype != np.uint8:
        raise ValueError('Native borders must contain original uint8 RGB pixels')
    scan = evaluate_borders(border, 'blue')
    if not scan['passed']:
        raise ValueError('All 240 native BLUE boundary frames must pass')
    pixels = border.reshape(-1, 3)
    median = np.median(pixels, axis=0)
    distances = np.linalg.norm(pixels.astype(np.float32) - median, axis=1)
    if float(distances.max()) > KEY_LOW:
        raise ValueError('Native BLUE boundary exceeds the fixed transparent radius')
    profile = BlueProfile(tuple(median.tolist()), tuple(pixels.min(0).tolist()),
                          tuple(pixels.max(0).tolist()), source_sha256)
    scan.update(background_rgb_median=list(profile.background_rgb),
                boundary_rgb_min=list(profile.background_rgb_min),
                boundary_rgb_max=list(profile.background_rgb_max),
                maximum_distance_from_global_median=float(distances.max()),
                blue_matte_profile=asdict(profile))
    return profile, scan


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def scan_blue_profile(source, ffmpeg='ffmpeg', ffprobe='ffprobe'):
    """Explicit decoder operation; schedule in an available media decoder slot."""
    source = Path(source)
    source_sha = sha256_file(source)
    info = json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height', '-of', 'json', str(source)]))
    streams = info.get('streams', [])
    if len(streams) != 1:
        raise ValueError('Expected one native BLUE source video')
    width, height = streams[0].get('width'), streams[0].get('height')
    if not (type(width) is int and type(height) is int and min(width, height) >= 2):
        raise ValueError('Invalid native BLUE source dimensions')
    command = [ffmpeg, '-v', 'error', '-xerror', '-err_detect', 'explode', '-noautorotate',
        '-i', str(source), '-t', '10', '-an', '-vf', 'fps=24', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
    borders = []
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
        try:
            while data := _read_frame(process.stdout, width * height * 3):
                borders.append(native_border(np.frombuffer(data, np.uint8).reshape(height, width, 3)))
            code = process.wait()
            if code:
                errors.seek(0)
                raise subprocess.CalledProcessError(code, command, stderr=errors.read())
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()
    if source_sha != sha256_file(source):
        raise ValueError('BLUE source changed during native scan')
    profile, scan = profile_from_native_borders(borders, source_sha256=source_sha)
    scan.update(source_sha256=source_sha, native_size=[width, height],
                measurement='native_one_pixel_outer_boundary_no_spatial_resampling')
    return profile, scan


def key_blue(rgb: np.ndarray, profile: BlueProfile) -> np.ndarray:
    """RGB Euclidean distance only; no channel-swap/global blue limiting."""
    if not isinstance(profile, BlueProfile):
        raise ValueError('A fixed BLUE profile is required')
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[-1] != 3:
        raise ValueError('Expected a native uint8 RGB frame')
    color = rgb.astype(np.float32)
    distance = np.linalg.norm(color - np.asarray(profile.background_rgb, np.float32), axis=2)
    alpha = np.clip((distance - profile.low) / (profile.high - profile.low), 0, 1)
    alpha = np.rint(alpha * alpha * (3 - 2 * alpha) * 255).astype(np.uint8)
    rgba = np.dstack((rgb, alpha))
    soft = (alpha > 0) & (alpha < 255)
    # Ordinary blue spill subtraction on soft pixels only. R/G stay unchanged.
    a = alpha[soft].astype(np.float32) / 255
    recovered_blue = (color[..., 2][soft] - (1 - a) * profile.background_rgb[2]) / a
    rgba[..., 2][soft] = np.rint(np.clip(np.minimum(recovered_blue, color[..., 2][soft]), 0, 255)).astype(np.uint8)
    rgba[alpha == 0, :3] = 0
    return rgba


def normal_blue_candidate(source, output, work_dir, timing, *, profile,
                          ffmpeg='ffmpeg', ffprobe='ffprobe'):
    """One initial conversion, shared strict geometry/240-frame verification.

    This utility neither checks approval nor claims/commits ledger work. Its
    caller must enforce source ALLOW, original task identity and slot ownership.
    A failure is returned to the caller, never retried with another threshold.
    """
    seconds = timing.get('video_duration_seconds')
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 10:
        raise ValueError('BLUE source video must establish at least 10 seconds; no repeat/time stretch')
    if not isinstance(profile, BlueProfile) or profile.source_sha256 is None:
        raise ValueError('BLUE profile must be bound to a native-scanned source SHA256')
    source = Path(source)
    if sha256_file(source) != profile.source_sha256:
        raise ValueError('BLUE profile source SHA256 mismatch')
    def matte(rgb, frame_index):
        return key_blue(rgb, profile)
    matte.name = WORKER_VERSION
    report = convert(source, Path(output), ffmpeg, ffprobe, Path(work_dir), False,
                     frame_matte=matte, lossless=True)
    report['blue_source_processing'] = {
        'worker_version': WORKER_VERSION, 'processing_profile': PROCESSING_PROFILE,
        'source_sha256': profile.source_sha256, 'source_timing': timing,
        'blue_profile': asdict(profile), 'global_palette_fitting': False,
        'white_classifier_used': False, 'semantic_segmentation_used': False,
        'individual_skin_eye_edits': False, 'geometry_warped': False,
        'short_phase_loop_used': False, 'opaque_matte_rgb_preserved': True,
        'spill_correction': 'blue_channel_only_on_0_lt_alpha_lt_255',
        'new_model_calls': 0, 'final_visual_review_required': True,
        'limitations': ['Foreground within the BLUE color radius is indistinguishable from backdrop.',
                        'Native boundary scan does not certify enclosed background or foreground.',
                        'RGB preservation is before shared scaling and YUV encoding.']}
    Path(output).with_suffix('.report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report
