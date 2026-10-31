import unittest
import numpy as np
from kurisu_bounded_edge_experiment import bounded_edge_rgb
from green_edge_despill import despill_auburn_collar

class BoundedEdgeExperimentTest(unittest.TestCase):
    def fixture(self):
        raw=np.zeros((64,64,3),np.uint8);raw[:]=[0,255,0]
        rgba=np.zeros((64,64,4),np.uint8)
        raw[4:60,4:60]=[80,80,80];rgba[4:60,4:60]=[80,80,80,255]
        raw[4:6,4:10]=[163,163,63];rgba[4:6,4:10]=[184,163,86,255]
        return raw,rgba
    def test_production_still_rejects_same_over40_case(self):
        raw,rgba=self.fixture()
        with self.assertRaisesRegex(ValueError,'40-level'):despill_auburn_collar(rgba)
    def test_bounded_candidate_caps_relative_original_not_global_input(self):
        raw,rgba=self.fixture();out,stats=bounded_edge_rgb(rgba,raw)
        self.assertTrue(np.array_equal(out[...,3],rgba[...,3]))
        self.assertTrue((out[4:6,4:10,1]==123).all())
        self.assertLessEqual(stats['final_visible_rgb_delta_max'],40)
        self.assertGreater(stats['capped_visible_pixels'],0)
    def test_semtransparent_alpha_unchanged_and_bound_applies(self):
        raw,rgba=self.fixture();rgba[5,5,3]=100
        out,_=bounded_edge_rgb(rgba,raw)
        self.assertEqual(out[5,5,3],100)
        self.assertTrue(np.array_equal(out[...,3],rgba[...,3]))
        self.assertLessEqual(abs(int(out[5,5,1])-int(raw[5,5,1])),40)
    def test_p95_cannot_be_relaxed(self):
        raw,rgba=self.fixture();rgba[4:60,4:60,:3]=[210,163,86]
        with self.assertRaisesRegex(ValueError,'p95'):bounded_edge_rgb(rgba,raw)
        with self.assertRaises(ValueError):bounded_edge_rgb(rgba,raw,max_delta=41)
    def test_unselected_skin_and_eyes_not_repainted(self):
        raw,rgba=self.fixture();raw[7,7]=[253,232,220];rgba[7,7]=[253,232,220,255]
        raw[8,8]=[70,80,160];rgba[8,8]=[70,80,160,255]
        out,_=bounded_edge_rgb(rgba,raw)
        self.assertTrue(np.array_equal(out[7,7],rgba[7,7]))
        self.assertTrue(np.array_equal(out[8,8],rgba[8,8]))

if __name__=='__main__':unittest.main()
