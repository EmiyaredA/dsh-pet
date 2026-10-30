import unittest
import numpy as np
from kurisu_hair_matte import clear_hair_islands,despill_boundary


class HairMatteTests(unittest.TestCase):
    def test_enclosed_lateral_sliver_removed_but_white_costume_eyes_and_hat_survive(self):
        x=np.zeros((360,640,4),np.uint8)
        x[60:330,210:430]=[150,65,55,255]
        # Headband, eye and sleeve whites do not have the hair-hole geometry.
        x[65:82,250:390]=[247,247,247,255]
        x[155:173,270:290]=[247,247,247,255]
        x[240:251,253:270]=[247,247,247,255]
        x[210:285,300:350]=[247,247,247,255]
        x[145:170,225:231]=[250,250,250,255]
        original=x.copy();result,count=clear_hair_islands(x)
        self.assertGreater(count,100)
        self.assertEqual(int(result[155,228,3]),0)
        for y,px in [(72,300),(163,280),(245,260),(250,325)]:
            np.testing.assert_array_equal(result[y,px],original[y,px])
        np.testing.assert_array_equal(x,original)

    def test_neutral_outlined_prop_is_not_mistaken_for_hair(self):
        x=np.zeros((360,640,4),np.uint8)
        x[60:330,210:430]=[50,50,50,255]
        x[145:170,225:231]=[250,250,250,255]
        result,count=clear_hair_islands(x)
        self.assertEqual(count,0)
        np.testing.assert_array_equal(result,x)

    def test_boundary_green_despill_preserves_interior_and_original_alpha(self):
        x=np.zeros((100,100,4),np.uint8)
        x[20:80,20:80]=[150,60,50,255]
        x[20:23,20:80]=[150,125,55,180]
        result,count=despill_boundary(x)
        self.assertGreater(count,0)
        self.assertLess(int(result[21,45,1]),100)
        np.testing.assert_array_equal(result[...,3],x[...,3])
        np.testing.assert_array_equal(result[40:60,40:60],x[40:60,40:60])

    def test_neutral_white_and_blue_eyes_are_not_recolored(self):
        x=np.zeros((100,100,4),np.uint8)
        x[20:80,20:80]=[245,245,245,255]
        x[40:60,40:60]=[60,100,180,255]
        result,_=despill_boundary(x)
        np.testing.assert_array_equal(result,x)


if __name__=='__main__':unittest.main()
