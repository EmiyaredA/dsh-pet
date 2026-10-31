"""Conservative GREEN-screen RGB decontamination; Alpha is never edited."""
import cv2
import numpy as np


def despill_auburn_collar(rgba):
    """Remove yellow-green contamination from dark auburn silhouette colors.

    A G > max(R,B) test misses mustard spill. Limit the correction to the
    4-pixel alpha collar and low-blue auburn colors. White lace, fair skin,
    pink accessories and blue eyes cannot enter this material predicate.
    """
    out=rgba.copy();rgb=rgba[...,:3].astype(np.float32);alpha=rgba[...,3]
    depth=cv2.distanceTransform((alpha>127).astype(np.uint8),cv2.DIST_L2,3)
    material=(rgb[...,0]>60)&(rgb[...,0]>rgb[...,1]+15)&(rgb[...,0]>rgb[...,2]+30)&(rgb[...,2]<120)
    target=rgb[...,2]+.30*(rgb[...,0]-rgb[...,2])
    chosen=(alpha>8)&(depth<=4)&material&(rgb[...,1]>target+8)
    amount=rgb[...,1]-target
    if chosen.any() and float(amount[chosen].max())>40:
        raise ValueError('Green boundary decontamination would exceed the 40-level RGB bound')
    out[...,1][chosen]=np.rint(target[chosen]).astype(np.uint8)
    return out,{'changed_pixels':int(chosen.sum()),'max_green_correction':float(amount[chosen].max()) if chosen.any() else 0,
        'alpha_changed':False,'per_face_or_eye_edits':False}
