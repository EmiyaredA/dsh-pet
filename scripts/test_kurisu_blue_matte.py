"""Synthetic protection tests only; no real clip repair or video decoding."""
from dataclasses import FrozenInstanceError
from io import BytesIO
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import kurisu_blue_matte as blue


class FakeDecoder:
    def __init__(self, data, code=0):
        self.stdout = BytesIO(data)
        self.code, self.done, self.killed = code, False, False

    def wait(self):
        self.done = True
        return self.code

    def poll(self):
        return self.code if self.done or self.killed else None

    def kill(self):
        self.killed = True


class BlueMatteTests(unittest.TestCase):
    def profile(self, source_sha256=None):
        return blue.BlueProfile((0, 0, 255), (0, 0, 255), (0, 0, 255), source_sha256)

    def borders(self):
        return np.full((240, 32, 3), (0, 0, 255), np.uint8)

    def test_synthetic_card_preserves_green_leaf_blue_violet_iris_lace_and_hair(self):
        colors = np.array([[0, 0, 255], [28, 150, 54], [65, 82, 181],
                           [84, 68, 155], [247, 245, 250], [151, 63, 54],
                           [24, 23, 28], [225, 181, 155]], np.uint8)
        # A real 2D card, with each swatch repeated: no spatial/semantic masks.
        card = np.repeat(np.repeat(colors[None], 7, 0), 9, 1)
        original = card.copy()
        result = blue.key_blue(card, self.profile())
        self.assertTrue((result[:, :9, 3] == 0).all())
        self.assertTrue((result[:, 9:, 3] == 255).all())
        np.testing.assert_array_equal(result[:, 9:, :3], original[:, 9:])
        np.testing.assert_array_equal(card, original)

    def test_green_prop_is_opaque_including_bright_saturated_green(self):
        rgb = np.array([[[0, 255, 0], [0, 190, 30], [70, 140, 45]]], np.uint8)
        rgba = blue.key_blue(rgb, self.profile())
        np.testing.assert_array_equal(rgba[..., :3], rgb)
        self.assertEqual(rgba[..., 3].tolist(), [[255, 255, 255]])

    def test_opaque_blue_channel_is_never_globally_limited(self):
        rgb = np.array([[[65, 82, 181], [100, 110, 250], [247, 245, 250]]], np.uint8)
        rgba = blue.key_blue(rgb, self.profile())
        np.testing.assert_array_equal(rgba[..., :3], rgb)
        self.assertTrue((rgba[..., 3] == 255).all())
        self.assertGreater(int(rgba[0, 0, 2]), int(max(rgb[0, 0, :2])) + 4)

    def test_alpha_has_fixed_soft_transition_and_only_soft_blue_is_changed(self):
        rgb = np.array([[[0, 0, 255], [64, 0, 255], [87, 0, 240], [110, 0, 255]]], np.uint8)
        rgba = blue.key_blue(rgb, self.profile())
        self.assertEqual(rgba[0, :2, 3].tolist(), [0, 0])
        self.assertTrue(0 < rgba[0, 2, 3] < 255)
        self.assertEqual(int(rgba[0, 3, 3]), 255)
        np.testing.assert_array_equal(rgba[0, 2, :2], rgb[0, 2, :2])
        self.assertLess(int(rgba[0, 2, 2]), int(rgb[0, 2, 2]))
        np.testing.assert_array_equal(rgba[0, 3, :3], rgb[0, 3])
        self.assertTrue((rgba[rgba[..., 3] == 0, :3] == 0).all())

    def test_backdrop_color_collision_is_explicit_not_semantically_repainted(self):
        # A true blue foreground identical to the backdrop cannot survive this
        # ordinary key: visual QA must reject such a source, not invent an iris.
        same_blue = np.full((2, 2, 3), (0, 0, 255), np.uint8)
        self.assertTrue((blue.key_blue(same_blue, self.profile()) == 0).all())

    def test_global_native_median_min_max_come_from_original_border_pixels(self):
        borders = self.borders()
        borders[1, 2] = [20, 8, 244]
        borders[239, 3] = [0, 0, 230]
        profile, scan = blue.profile_from_native_borders(borders, source_sha256='a' * 64)
        self.assertEqual(profile.background_rgb, (0, 0, 255))
        self.assertEqual(profile.background_rgb_min, (0, 0, 230))
        self.assertEqual(profile.background_rgb_max, (20, 8, 255))
        self.assertEqual(scan['background_rgb_median'], [0, 0, 255])
        self.assertTrue(scan['passed'])
        self.assertFalse(scan['enclosed_background_and_foreground_verified'])
        self.assertTrue((blue.key_blue(borders, profile)[..., 3] == 0).all())

    def test_invalid_background_missing_frames_or_float_resampling_reject(self):
        for borders in [self.borders()[:239], self.borders().astype(float),
                        np.full((240, 32, 3), (0, 255, 0), np.uint8)]:
            with self.subTest(shape=borders.shape, dtype=borders.dtype), self.assertRaises(ValueError):
                blue.profile_from_native_borders(borders)

    def test_good_boundary_scan_outside_fixed_radius_does_not_trigger_threshold_search(self):
        borders = self.borders()
        borders[0, 0] = [35, 35, 220]
        # sqrt(3*35^2)<64 passes; slightly more variation across time may pass
        # the backdrop gate but must fail the fixed color radius, never retune.
        borders[239] = [20, 20, 235]
        borders[239, 0] = [55, 55, 200]
        with self.assertRaisesRegex(ValueError, 'fixed transparent radius'):
            blue.profile_from_native_borders(borders)

    def test_profile_is_immutable_and_rejects_unapproved_thresholds(self):
        profile = blue.BlueProfile([0, 0, 255], [0, 0, 255], [0, 0, 255])
        self.assertIsInstance(profile.background_rgb, tuple)
        with self.assertRaises(FrozenInstanceError):
            profile.high = 120
        for kw in [{'low': 12}, {'high': 111}, {'background_rgb': (0, float('nan'), 255)},
                   {'source_sha256': 'bad'}]:
            args = dict(background_rgb=(0, 0, 255), background_rgb_min=(0, 0, 255), background_rgb_max=(0, 0, 255))
            args.update(kw)
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                blue.BlueProfile(**args)

    def test_conversion_uses_shared_strict_pipeline_lossless_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'source.mp4', Path(folder) / 'candidate.webm'
            source.write_bytes(b'synthetic source identity')
            profile = self.profile(blue.sha256_file(source))
            captured = {}
            def convert(*args, **kwargs):
                captured.update(args=args, kwargs=kwargs)
                rgb = np.array([[[65, 82, 181], [0, 0, 255]]], np.uint8)
                captured['rgba'] = kwargs['frame_matte'](rgb, 239)
                return {'alignment': {'target_height': 270, 'target_feet_y': 330},
                        'verification': {'frames': 240, 'all_frames_have_alpha': True}}
            with patch.object(blue, 'convert', side_effect=convert) as call:
                report = blue.normal_blue_candidate(source, output, folder, {'video_duration_seconds': 10}, profile=profile)
            self.assertEqual(call.call_count, 1)
            self.assertIs(captured['args'][5], False)
            self.assertEqual(set(captured['kwargs']), {'frame_matte', 'lossless'})
            self.assertIs(captured['kwargs']['lossless'], True)
            self.assertEqual(captured['rgba'][0, :, 3].tolist(), [255, 0])
            np.testing.assert_array_equal(captured['rgba'][0, 0, :3], [65, 82, 181])
            saved = json.loads(output.with_suffix('.report.json').read_text())
            self.assertEqual(saved['blue_source_processing']['source_sha256'], profile.source_sha256)
            self.assertEqual(report['verification']['frames'], 240)
            self.assertTrue(saved['blue_source_processing']['final_visual_review_required'])
            self.assertFalse(saved['blue_source_processing']['semantic_segmentation_used'])

    def test_short_or_unknown_video_and_unbound_or_wrong_source_profile_never_convert(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source.mp4'; source.write_bytes(b'original')
            good = self.profile(blue.sha256_file(source))
            with patch.object(blue, 'convert') as call:
                for seconds in [9.999, None, True, float('nan'), float('inf'), '10']:
                    with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                        blue.normal_blue_candidate(source, Path(folder) / 'out.webm', folder,
                            {'video_duration_seconds': seconds}, profile=good)
                for profile in [self.profile(), self.profile('a' * 64)]:
                    with self.assertRaises(ValueError):
                        blue.normal_blue_candidate(source, Path(folder) / 'out.webm', folder,
                            {'video_duration_seconds': 10}, profile=profile)
                call.assert_not_called()

    def test_shared_geometry_or_verification_failure_is_not_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source.mp4'; source.write_bytes(b'original')
            with patch.object(blue, 'convert', side_effect=ValueError('Residual translucent background')) as call:
                with self.assertRaisesRegex(ValueError, 'Residual'):
                    blue.normal_blue_candidate(source, Path(folder) / 'out.webm', folder,
                        {'video_duration_seconds': 10}, profile=self.profile(blue.sha256_file(source)))
                self.assertEqual(call.call_count, 1)
            self.assertFalse((Path(folder) / 'out.report.json').exists())

    def test_native_profile_scan_streams_original_boundary_without_resizing(self):
        frames = np.full((240, 4, 8, 3), (0, 0, 255), np.uint8)
        # Foreground color is intentionally irrelevant to the boundary profile.
        frames[:, 1:3, 2:6] = [65, 82, 181]
        process = FakeDecoder(frames.tobytes())
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'synthetic'; source.write_bytes(b'identity')
            with patch.object(blue.subprocess, 'check_output', return_value=b'{"streams":[{"width":8,"height":4}]}'), \
                 patch.object(blue.subprocess, 'Popen', return_value=process) as decoder:
                profile, scan = blue.scan_blue_profile(source)
        command = decoder.call_args.args[0]
        self.assertEqual(command[command.index('-vf') + 1], 'fps=24')
        self.assertNotIn('scale', ' '.join(command))
        self.assertIn('-xerror', command)
        self.assertEqual(profile.background_rgb, (0, 0, 255))
        self.assertEqual(scan['native_size'], [8, 4])
        self.assertEqual(scan['source_sha256'], profile.source_sha256)
        self.assertTrue(process.done)
        self.assertTrue(process.stdout.closed)

    def test_native_profile_scan_rejects_truncated_decoder_failure_and_source_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'synthetic'; source.write_bytes(b'identity')
            for data, code, error in [(bytes(13), 0, ValueError),
                                      (bytes(12), 1, subprocess.CalledProcessError)]:
                process = FakeDecoder(data, code)
                with patch.object(blue.subprocess, 'check_output', return_value=b'{"streams":[{"width":2,"height":2}]}'), \
                     patch.object(blue.subprocess, 'Popen', return_value=process):
                    with self.assertRaises(error):
                        blue.scan_blue_profile(source)
                self.assertTrue(process.stdout.closed)
                self.assertTrue(process.done)
            process = FakeDecoder(np.full((240, 2, 2, 3), (0, 0, 255), np.uint8).tobytes())
            with patch.object(blue.subprocess, 'check_output', return_value=b'{"streams":[{"width":2,"height":2}]}'), \
                 patch.object(blue.subprocess, 'Popen', return_value=process), \
                 patch.object(blue, 'sha256_file', side_effect=['a' * 64, 'b' * 64]):
                with self.assertRaisesRegex(ValueError, 'changed during native scan'):
                    blue.scan_blue_profile(source)


if __name__ == '__main__':
    unittest.main()
