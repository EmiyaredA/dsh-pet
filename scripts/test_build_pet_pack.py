"""Regression checks for destructive matte errors and frame geometry."""
import io
import unittest

import numpy as np

from build_pet_pack import alignment, key_green, read_frame,verify_endpoint_geometry


class MatteTests(unittest.TestCase):
    def test_neutral_endpoints_reject_model_zoom_and_baseline_drift(self):
        self.assertEqual(verify_endpoint_geometry([200,60,430,330],[200,61,430,329])['feet_delta_px'],-1)
        for last in [[190,35,445,346],[200,60,430,340]]:
            with self.assertRaisesRegex(ValueError,'Neutral endpoints'):
                verify_endpoint_geometry([200,60,430,330],last)

    def test_green_removed_while_white_hair_eyes_and_dark_clothes_survive(self):
        rgb = np.array([[[0, 255, 0], [247, 245, 250], [151, 63, 54],
                         [65, 82, 181], [24, 23, 28]]], dtype=np.uint8)
        rgba = key_green(rgb)
        self.assertEqual(rgba[0, :, 3].tolist(), [0, 255, 255, 255, 255])
        np.testing.assert_array_equal(rgba[0, 1:, :3], rgb[0, 1:])

    def test_soft_edges_and_spill(self):
        rgba = key_green(np.array([[[80, 140, 85]]], dtype=np.uint8))
        self.assertGreater(int(rgba[0, 0, 3]), 0)
        self.assertLess(int(rgba[0, 0, 3]), 255)
        self.assertLessEqual(int(rgba[0, 0, 1]), 89)

    def test_animation_that_would_clip_is_rejected(self):
        samples = [{'height': 100, 'center_x': 100, 'feet_y': 150}]
        with self.assertRaisesRegex(ValueError, 'would clip'):
            alignment(samples, [0, 0, 300, 200], (320, 180))

    def test_truncated_frame_is_not_silently_accepted(self):
        with self.assertRaisesRegex(RuntimeError, 'truncated'):
            read_frame(io.BytesIO(b'123'), 4)


if __name__ == '__main__':
    unittest.main()
