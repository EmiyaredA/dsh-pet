import unittest
import numpy as np
from repair_kurisu_white import WhiteConnectedMatte,WhiteStandingMatte
from build_pet_pack import measure


class WhiteMatteTests(unittest.TestCase):
    def test_green_to_white_transition_keeps_enclosed_white_costume_opaque(self):
        matte=WhiteConnectedMatte(allow_green=True)
        for i,bg in enumerate([(0,255,0),(180,250,180),(225,250,225),(250,250,250)]):
            frame=np.full((100,100,3),bg,np.uint8)
            frame[20:85,35:56]=40;frame[23:82,38:53]=247
            result=matte(frame,i)
            self.assertEqual(int(result[0,0,3]),0)
            self.assertEqual(int(result[50,45,3]),255)
        with self.assertRaises(ValueError):matte(np.zeros((100,100,3),np.uint8),5)

    def test_green_hole_surrounded_by_hair_is_cut_out_without_erasing_white_bib(self):
        frame=np.full((100,100,3),(0,255,0),np.uint8)
        frame[20:85,30:70]=[120,40,40]
        frame[30:40,40:50]=[0,255,0]
        frame[55:70,40:60]=[245,245,245]
        result=WhiteConnectedMatte(allow_green=True)(frame,0)
        self.assertEqual(int(result[35,45,3]),0)
        self.assertEqual(int(result[60,45,3]),255)

    def test_uniform_standing_alignment_restores_size_without_stretching_costume(self):
        first=np.full((160,160,3),250,np.uint8)
        first[40:120,60:100]=[100,40,40]
        enlarged=np.full_like(first,250)
        enlarged[15:135,50:110]=[100,40,40]
        matte=WhiteStandingMatte()
        a=measure(matte(first,0)[...,3]);b=measure(matte(enlarged,1)[...,3])
        self.assertLessEqual(abs(a['height']-b['height']),1)
        self.assertLessEqual(abs(a['feet_y']-b['feet_y']),1)
        self.assertLessEqual(abs((a['box'][2]-a['box'][0])-(b['box'][2]-b['box'][0])),1)
        self.assertAlmostEqual(matte.scales[-1],2/3,places=2)

    def test_white_costume_inside_dark_outline_survives_white_background_removal(self):
        frame=np.full((100,100,3),250,np.uint8)
        frame[20:85,35:56]=40
        frame[23:82,38:53]=247
        original=frame.copy()
        result=WhiteConnectedMatte()(frame,96)
        self.assertEqual(int(result[0,0,3]),0)
        self.assertEqual(int(result[50,45,3]),255)
        self.assertEqual(result[50,45,:3].tolist(),[247,247,247])
        np.testing.assert_array_equal(frame,original)

    def test_scoped_gray_appendage_cleanup_does_not_remove_red_hair(self):
        frame=np.full((100,100,3),250,np.uint8)
        frame[20:85,35:56]=40
        frame[72:77,55:65]=75
        frame[67:72,55:65]=[140,55,45]
        plain=WhiteConnectedMatte()(frame,96)
        repair=WhiteConnectedMatte(True)
        result=repair(frame,96)
        self.assertGreater(int(plain[74,62,3]),0)
        self.assertEqual(int(result[74,62,3]),0)
        self.assertGreater(int(result[69,60,3]),0)
        self.assertGreater(repair.removed_pixels,0)


if __name__=='__main__':unittest.main()
