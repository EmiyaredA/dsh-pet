import unittest
import numpy as np
from build_pet_pack import key_green
from repair_kurisu_lid import RearLidMatte


class RearLidTests(unittest.TestCase):
    def test_ui_is_removed_while_hands_and_every_pixel_outside_lid_are_preserved(self):
        reference=np.full((768,1344,3),(0,255,0),np.uint8)
        reference[60:650,450:900]=[140,55,45]
        reference[408:574,538:780]=20
        reference[412:570,542:776]=[70,76,82]
        frame=reference.copy()
        frame[430:555,555:765]=[40,70,100]
        frame[480:520,610:665]=[235,235,220]
        frame[407:422,558:579]=[245,195,165]
        original=frame.copy();result=RearLidMatte(reference)(frame,100)
        self.assertLess(np.ptp(result[490,630,:3]),20)
        self.assertGreater(int(result[490,630,3]),250)
        np.testing.assert_array_equal(result[415,565,:3],[245,195,165])
        outside=np.ones(frame.shape[:2],bool);outside[408:574,538:780]=False
        np.testing.assert_array_equal(result[outside],key_green(frame,12,65)[outside])
        np.testing.assert_array_equal(frame,original)


if __name__=='__main__':unittest.main()
