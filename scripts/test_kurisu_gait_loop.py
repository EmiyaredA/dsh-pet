import unittest
import numpy as np
from loop_kurisu_gait import phase_indices,premult_mad


class GaitPhaseTests(unittest.TestCase):
    def test_240_frames_are_only_the_selected_phase_in_original_order(self):
        indices=phase_indices(149,20,12,240)
        self.assertEqual(len(indices),240)
        self.assertEqual(set(indices),set(range(149,169)))
        self.assertEqual(indices[:20],list(range(149,169)))
        self.assertEqual(indices[-20:],indices[:20])
        self.assertEqual(indices[19:22],[168,149,150])
        source=np.arange(240*8).reshape(240,2,4)
        selected=source[indices]
        for repeat in range(12):np.testing.assert_array_equal(selected[repeat*20:(repeat+1)*20],source[149:169])
        for params in [(-1,20,12,240),(149,100,12,240),(149,1,12,240),(149,20,0,240)]:
            with self.assertRaises(ValueError):phase_indices(*params)

    def test_motion_metric_ignores_invisible_rgb_without_ignoring_visible_motion(self):
        a=np.zeros((4,4,4),np.uint8);b=a.copy();b[...,:3]=255
        self.assertEqual(premult_mad(a,b),0)
        a[1,1]=[120,60,50,255];b[2,1]=[120,60,50,255]
        self.assertGreater(premult_mad(a,b),0)


if __name__=='__main__':unittest.main()
