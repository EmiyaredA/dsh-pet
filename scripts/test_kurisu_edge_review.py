"""Independent regressions found while reviewing the edge-repair candidates."""
import unittest
import numpy as np
from kurisu_hair_matte import clear_hair_islands,despill_boundary


class IndependentEdgeReviewTests(unittest.TestCase):
    def figure(self):
        rgba=np.zeros((360,640,4),np.uint8)
        rgba[60:330,210:430]=[150,65,55,255]
        return rgba

    def test_outer_neutral_lace_does_not_borrow_red_hair_color(self):
        rgba=self.figure()
        # A thin white frill on the silhouette has no white eroded interior.
        # Its nearest opaque seed is auburn hair, but the frill is not spill.
        rgba[145:170,210:213]=[247,247,247,255]
        result,_=despill_boundary(rgba)
        np.testing.assert_array_equal(result[145:170,210:213],rgba[145:170,210:213])

    def test_boundary_despill_preserves_alpha_and_blue_eye_interior(self):
        rgba=self.figure();rgba[145:170,280:305]=[80,105,180,255]
        result,_=despill_boundary(rgba)
        np.testing.assert_array_equal(result[...,3],rgba[...,3])
        np.testing.assert_array_equal(result[145:170,280:305],rgba[145:170,280:305])

    def test_lateral_eye_white_inside_blue_iris_is_not_a_hair_hole(self):
        rgba=self.figure();rgba[140:170,220:240]=[80,105,180,255]
        rgba[145:165,225:230]=[247,247,247,255]
        result,_=clear_hair_islands(rgba)
        np.testing.assert_array_equal(result[145:165,225:230],rgba[145:165,225:230])

    def test_outer_horizontal_hair_gap_is_removed(self):
        rgba=self.figure()
        rgba[210:215,395:425]=[250,250,250,255]
        result,count=clear_hair_islands(rgba)
        self.assertGreater(count,140)
        self.assertEqual(int(result[212,410,3]),0)

    def test_white_cuff_next_to_peach_hand_is_preserved_even_with_hair_behind(self):
        rgba=self.figure()
        rgba[230:252,222:227]=[247,247,247,255]
        rgba[230:252,227:234]=[240,190,170,255]
        result,_=clear_hair_islands(rgba)
        np.testing.assert_array_equal(result[230:252,222:227],rgba[230:252,222:227])

    def test_upper_outer_hair_gap_is_not_preserved_as_a_pale_human_ear(self):
        rgba=self.figure();rgba[60:330,210:430]=[190,135,110,255]
        rgba[145:170,405:410]=[250,250,250,255]
        result,_=clear_hair_islands(rgba)
        self.assertEqual(int(result[155,407,3]),0)

    def test_pale_ear_at_inner_side_lock_is_preserved(self):
        rgba=self.figure()
        rgba[168:190,383:395]=[240,190,170,255]
        rgba[170:188,385:390]=[250,250,250,255]
        result,_=clear_hair_islands(rgba)
        np.testing.assert_array_equal(result[170:188,385:390],rgba[170:188,385:390])

    def test_nearly_white_forehead_above_side_eye_is_not_cut_out(self):
        rgba=self.figure()
        rgba[177:190,266:276]=[80,105,180,255]
        rgba[148:168,252:265]=[250,248,244,255]
        result,_=clear_hair_islands(rgba)
        np.testing.assert_array_equal(result[148:168,252:265],rgba[148:168,252:265])

    def test_peach_skin_component_is_protected_without_visible_open_eyes(self):
        rgba=self.figure()
        rgba[148:168,252:258]=[252,244,234,255]
        result,_=clear_hair_islands(rgba)
        np.testing.assert_array_equal(result[148:168,252:258],rgba[148:168,252:258])

    def test_warmed_white_outer_back_hair_gap_is_not_mistaken_for_peach_skin(self):
        rgba=self.figure()
        rgba[215:230,405:410]=[239,232,228,255]
        result,_=clear_hair_islands(rgba)
        self.assertEqual(int(result[222,407,3]),0)

    def test_frontal_pale_ear_outside_iris_span_stays_opaque(self):
        rgba=self.figure()
        rgba[175:190,278:290]=[80,105,180,255]
        rgba[175:190,345:357]=[80,105,180,255]
        rgba[166:188,385:391]=[250,250,238,255]
        # A real hair gap farther out remains removable.
        rgba[150:175,405:410]=[250,250,250,255]
        result,_=clear_hair_islands(rgba)
        np.testing.assert_array_equal(result[166:188,385:391],rgba[166:188,385:391])
        self.assertEqual(int(result[160,407,3]),0)

    def test_raised_peach_hand_outside_face_and_normal_wrist_region_survives(self):
        rgba=self.figure()
        rgba[195:215,405:410]=[252,243,231,255]
        result,_=clear_hair_islands(rgba)
        np.testing.assert_array_equal(result[195:215,405:410],rgba[195:215,405:410])

    def test_small_lower_outer_hair_gap_with_warm_antialias_ring_still_clears(self):
        rgba=self.figure()
        rgba[218:223,400:404]=[255,247,240,255]
        rgba[218:223,397:400]=[230,210,204,255]
        result,_=clear_hair_islands(rgba)
        self.assertEqual(int(result[220,402,3]),0)


if __name__=='__main__':unittest.main()
