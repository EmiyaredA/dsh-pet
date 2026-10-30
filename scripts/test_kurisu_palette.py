import unittest
import numpy as np
from build_pet_pack import key_green
from repair_kurisu_palette import IDENTITY,TemporalPaletteMatte,fit_palette_transform,material_masks,transform_rgb


def fixture():
    x=np.full((160,240,3),(0,255,0),np.uint8)
    x[20:145,80:160]=[145,65,50]
    x[25:40,95:145]=[240,240,242]
    x[95:135,95:145]=[50,48,52]
    # Modest gradients prevent a rank-deficient three-color toy fit.
    for y in range(40,90):x[y,95:145]=[130+y//3,55+y//9,45+y//12]
    return x


class TemporalPaletteTests(unittest.TestCase):
    def test_identity_palette_and_source_background_survive(self):
        reference=fixture();m,record=fit_palette_transform(reference,reference,material_masks(reference))
        np.testing.assert_allclose(m,IDENTITY,atol=.005)
        np.testing.assert_array_equal(transform_rgb(reference,m),reference)
        self.assertGreater(record['fit_pixels'],100)

    def test_green_wash_restores_material_colors_without_recoloring_green_background(self):
        ref=fixture();cur=ref.copy();mask=key_green(ref)[...,3]>245
        values=cur[mask].astype(float)
        values=values*np.array([.96,1.04,.94])+np.array([0,8,0])
        cur[mask]=np.clip(values,0,255).astype(np.uint8)
        matrix,_=fit_palette_transform(cur,ref,material_masks(ref))
        result=transform_rgb(cur,matrix)
        self.assertLess(float(np.abs(result.astype(float)-ref)[mask].mean()),2)
        np.testing.assert_array_equal(result[0,0],ref[0,0])
        # Geometry comes only from the source alpha, never optical-flow warping.
        rgba=TemporalPaletteMatte(np.array([matrix]),despill=False)(cur,0)
        np.testing.assert_array_equal(rgba[...,3],key_green(cur)[...,3])


if __name__=='__main__':unittest.main()
