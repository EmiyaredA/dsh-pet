"""Conservative repair of white matte islands enclosed by Kurisu's auburn hair.

Only narrow, lateral, hair-surrounded islands qualify. White costume, eyes,
headwear and neutral props are deliberately protected. Works on existing RGBA
so previously inspected local repairs are retained.
"""
import cv2
import numpy as np


def clear_hair_islands(rgba):
    result=rgba.copy()
    rgb=rgba[...,:3].astype(np.int16); alpha=rgba[...,3]
    yy,xx=np.where(alpha>127)
    if not len(xx):return result,0
    left,right,top,bottom=xx.min(),xx.max(),yy.min(),yy.max()
    width=max(1,right-left);height=max(1,bottom-top)
    white=(rgb.min(2)>220)&(np.ptp(rgb,axis=2)<35)&(alpha>240)
    hair=(rgb[...,0]-rgb[...,1]>20)&(rgb[...,0]-rgb[...,2]>15)&(rgb[...,0]>60)&(rgb[...,0]<240)
    count,labels,stats,centers=cv2.connectedComponentsWithStats(white.astype(np.uint8))
    holes=np.zeros(alpha.shape,np.uint8)
    radius=max(2,round(height/90))
    kernel=np.ones((2*radius+1,2*radius+1),np.uint8)
    for i in range(1,count):
        x,y,w,h,area=stats[i];cx,cy=centers[i]
        nx=(cx-left)/width;ny=(cy-top)/height
        if not ((nx<.30 or nx>.70) and .20<ny<.84):continue
        if not 3<=area<=width*height*.004:continue
        # White cuffs/apron folds are wider than the thin background slivers.
        if w>1.05*h or w>width*.075:continue
        component=(labels==i).astype(np.uint8)
        ring=(cv2.dilate(component,kernel)>0)&(~component.astype(bool))&(alpha>200)&(~white)
        if not ring.any() or float(hair[ring].mean())<.55:continue
        holes|=component
    if not holes.any():return result,0
    # Include only the immediately adjacent neutral antialias fringe.
    fringe=(rgb.min(2)>165)&(np.ptp(rgb,axis=2)<35)
    holes|=(cv2.dilate(holes,np.ones((3,3),np.uint8))>0)&fringe
    distance=cv2.distanceTransform(1-holes,cv2.DIST_L2,3)
    factor=np.clip(distance/1.25,0,1)
    new_alpha=np.rint(alpha*factor).astype(np.uint8)
    edge=(new_alpha>0)&(new_alpha<alpha)
    color=rgb.astype(np.float32)
    # Remove the white contribution only from the newly exposed boundary.
    ratio=np.divide(new_alpha,alpha,out=np.ones(alpha.shape,np.float32),where=alpha>0)
    color[edge]=(color[edge]-255*(1-ratio[edge,None]))/ratio[edge,None]
    result[...,:3]=np.clip(color,0,255).astype(np.uint8)
    result[...,3]=new_alpha
    result[new_alpha==0,:3]=0
    return result,int(holes.sum())
