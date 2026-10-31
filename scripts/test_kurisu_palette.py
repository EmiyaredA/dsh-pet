import unittest
import numpy as np
from build_pet_pack import key_green
from repair_kurisu_palette import IDENTITY,TemporalPaletteMatte,fit_palette_transform,material_masks,transform_rgb,compose_palette_track,canonical_palette_anchor


def fixture():
    x=np.full((160,240,3),(0,255,0),np.uint8)
    x[20:145,80:160]=[145,65,50]
    x[25:40,95:145]=[240,240,242]
    x[95:135,95:145]=[50,48,52]
    # Modest gradients prevent a rank-deficient three-color toy fit.
    for y in range(40,90):x[y,95:145]=[130+y//3,55+y//9,45+y//12]
    return x


class TemporalPaletteTests(unittest.TestCase):
    def test_global_anchor_composition_matches_sequential_rgb_algebra(self):
        first=IDENTITY.copy();first[:3]*=.97;first[3]=[.01,.02,0]
        anchor=IDENTITY.copy();anchor[:3]*=1.01;anchor[3]=[0,-.01,.01]
        combined=compose_palette_track(np.array([first]),anchor)[0]
        color=np.array([.5,.3,.2])
        np.testing.assert_allclose(color@combined[:3]+combined[3],(color@first[:3]+first[3])@anchor[:3]+anchor[3],atol=1e-6)

    def test_canonical_anchor_uses_one_global_fit_and_does_not_change_output_geometry(self):
        reference=fixture();rgba=key_green(reference)
        source=reference.copy();mask=rgba[...,3]>245
        source[mask]=np.clip(source[mask].astype(float)*[.99,1.02,.99]+[0,3,0],0,255).astype(np.uint8)
        matrix,record=canonical_palette_anchor(source,rgba)
        corrected=transform_rgb(source,matrix)
        self.assertFalse(record['output_geometry_warped']);self.assertFalse(record['per_material_output_edits'])
        self.assertLess(float(np.abs(corrected.astype(float)-reference)[mask].mean()),3)
        np.testing.assert_array_equal(corrected[0,0],source[0,0])

    def test_dark_neutral_green_cast_is_removed_without_changing_black_or_colored_materials(self):
        pixels=np.array([[[45,53,46],[30,30,30],[8,20,50],
                          [90,45,40],[230,180,155],[0,255,0]]],np.uint8)
        result=transform_rgb(pixels,IDENTITY)
        self.assertLessEqual(float(result[0,0,1])-(float(result[0,0,0])+float(result[0,0,2]))/2,1.5)
        np.testing.assert_array_equal(result[:,1:],pixels[:,1:])
        rgba=TemporalPaletteMatte(np.array([IDENTITY]),despill=False)(pixels,0)
        np.testing.assert_array_equal(rgba[...,3],key_green(pixels)[...,3])

    def test_identity_anchor_neutralizes_green_lace_without_changing_other_materials(self):
        pixels=np.array([[[220,235,222],[242,242,244],[150,65,50],
                          [240,190,170],[75,105,180],[0,255,0]]],np.uint8)
        result=transform_rgb(pixels,IDENTITY)
        self.assertLessEqual(float(result[0,0,1])-(float(result[0,0,0])+float(result[0,0,2]))/2,2)
        np.testing.assert_array_equal(result[:,1:],pixels[:,1:])
        rgba=TemporalPaletteMatte(np.array([IDENTITY]),despill=False)(pixels,0)
        np.testing.assert_array_equal(rgba[...,3],key_green(pixels)[...,3])

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
