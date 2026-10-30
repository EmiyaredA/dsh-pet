import unittest
import numpy as np
from build_pet_pack import measure
from stabilize_pet_camera import LinearCameraMatte


class CameraStabilizationTests(unittest.TestCase):
    def test_uniform_zoom_is_removed_but_an_intentional_middle_jump_survives(self):
        start={'height':80,'center_x':80,'feet_y':120}
        end={'height':96,'center_x':80,'feet_y':140}
        matte=LinearCameraMatte(start,end)
        last=np.zeros((160,160,4),np.uint8);last[44:140,56:104]=[120,50,40,255]
        corrected=measure(matte.align(last,239)[...,3])
        self.assertLessEqual(abs(corrected['height']-80),1)
        self.assertLessEqual(abs(corrected['feet_y']-120),1)
        middle=np.zeros_like(last);middle[32:120,58:102]=[120,50,40,255]
        jumping=measure(matte.align(middle,120)[...,3])
        self.assertGreater(120-jumping['feet_y'],7)


if __name__=='__main__':unittest.main()
