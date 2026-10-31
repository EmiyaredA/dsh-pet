"""Explicit offline experiment only. Production edge helper remains strict.

Uses supplied fixed transforms; never fits, submits, approves or changes alpha.
"""
import cv2
import numpy as np


def bounded_edge_rgb(rgba,raw,max_delta=40,p95_limit=20):
    if max_delta!=40 or p95_limit!=20:
        raise ValueError('This explicit experiment retains fixed20/40 safety limits')
    if rgba.shape[:2]!=raw.shape[:2] or rgba.shape[-1]!=4 or raw.shape[-1]!=3:
        raise ValueError('RGB and RGBA geometry mismatch')
    out=rgba.copy();rgb=rgba[...,:3].astype(np.float32);alpha=rgba[...,3]
    depth=cv2.distanceTransform((alpha>127).astype(np.uint8),cv2.DIST_L2,3)
    material=(rgb[...,0]>60)&(rgb[...,0]>rgb[...,1]+15)&(rgb[...,0]>rgb[...,2]+30)&(rgb[...,2]<120)
    target=rgb[...,2]+.30*(rgb[...,0]-rgb[...,2])
    chosen=(alpha>8)&(depth<=4)&material&(rgb[...,1]>target+8)
    desired=rgba[...,:3].astype(np.int16).copy()
    desired[...,1][chosen]=np.rint(target[chosen]).astype(np.int16)
    original=raw.astype(np.int16);visible=alpha>0
    capped=np.clip(desired,original-max_delta,original+max_delta)
    out[...,:3][visible]=np.clip(capped[visible],0,255).astype(np.uint8)
    out[alpha==0,:3]=0
    delta=np.abs(out[...,:3].astype(np.int16)-original)
    opaque=alpha>245
    p95=float(np.percentile(delta[opaque],95)) if opaque.any() else 0
    maximum=int(delta[visible].max()) if visible.any() else 0
    if p95>p95_limit or maximum>max_delta:
        raise ValueError(f'Final bounded RGB safety failed: p95={p95}, max={maximum}')
    assert np.array_equal(out[...,3],rgba[...,3])
    return out,{'edge_selected_pixels':int(chosen.sum()),'capped_visible_pixels':int((visible&(np.abs(desired-original).max(2)>max_delta)).sum()),'final_opaque_rgb_delta_p95':p95,'final_visible_rgb_delta_max':maximum,'alpha_changed':False}
