"""Conservative repair of white matte islands enclosed by Kurisu's auburn hair.

Only narrow, lateral, hair-surrounded islands qualify. White costume, eyes,
headwear and neutral props are deliberately protected. Works on existing RGBA
so previously inspected local repairs are retained.
"""
import cv2
import numpy as np


def face_protection(rgb,alpha,bounds):
    """Protect pale skin semantically, rather than trusting a white/hair ring.

    A side-facing forehead is nearly white and surrounded by red bangs. Anchor
    the face to its blue iris and largest warm skin patch so it cannot become a
    background hole. Closed-eye shots retain the skin-component fallback.
    """
    left,right,top,bottom=bounds;height=max(1,bottom-top);width=max(1,right-left)
    yy,xx=np.indices(alpha.shape)
    upper=(yy>top+.20*height)&(yy<top+.62*height)&(xx>left+.10*width)&(xx<right-.10*width)&(alpha>200)
    mask=np.zeros(alpha.shape,bool)
    blue=upper&(yy<top+.56*height)&(rgb[...,2]>rgb[...,0]+15)&(rgb[...,2]>rgb[...,1]+5)&(rgb[...,2]>75)
    by,bx=np.where(blue)
    if len(bx)>=3:
        mx=max(12,round(height*.085));mt=max(20,round(height*.17));mb=max(12,round(height*.10))
        mask[max(0,by.min()-mt):min(alpha.shape[0],by.max()+mb+1),
             max(0,bx.min()-mx):min(alpha.shape[1],bx.max()+mx+1)]=True
    warm=upper&(rgb[...,1]>160)&(rgb[...,2]>140)&(rgb[...,0]-rgb[...,1]>=3)&(rgb[...,0]-rgb[...,1]<=55)&(rgb[...,0]-rgb[...,2]>=5)&(rgb[...,0]-rgb[...,2]<=100)
    n,labels,stats,_=cv2.connectedComponentsWithStats(warm.astype(np.uint8))
    if n>1:
        stat=stats[1+np.argmax(stats[1:,cv2.CC_STAT_AREA])]
        x,y,w,h,area=stat
        if area>=max(30,width*height*.001):
            mask[max(0,y-5):min(alpha.shape[0],y+h+5),max(0,x-5):min(alpha.shape[1],x+w+5)]=True
    return mask


def despill_boundary(rgba):
    """Restore edge chroma from the nearest interior of the same small surface.

    Does not recolor the face, eyes, painted highlights or interior costume.
    Includes yellow-green spill on red hair, which a G > max(R,B) clamp misses.
    """
    out=rgba.copy();rgb=rgba[...,:3].astype(np.float32);a=rgba[...,3]
    solid=(a>245).astype(np.uint8)
    interior=cv2.erode(solid,np.ones((7,7),np.uint8))
    if not interior.any():return out,0
    distance,labels=cv2.distanceTransformWithLabels(1-interior,cv2.DIST_L2,5,labelType=cv2.DIST_LABEL_PIXEL)
    points=rgb[interior>0];nearest=points[np.clip(labels-1,0,len(points)-1)]
    # Compare scale-independent green chroma, keeping luminance and other channels.
    chroma=(2*rgb[...,1]-rgb[...,0]-rgb[...,2])/np.maximum(rgb.sum(2),1)
    target=(2*nearest[...,1]-nearest[...,0]-nearest[...,2])/np.maximum(nearest.sum(2),1)
    edge=(a>8)&(distance>0)&(distance<=6)&(chroma>target+.035)
    edge&=rgb[...,1]>np.maximum(rgb[...,0],rgb[...,2])+2
    # White/gray interiors require neutral edges; hair keeps its auburn ratios.
    ratio=np.maximum(rgb[...,0]+rgb[...,2],1)/np.maximum(nearest[...,0]+nearest[...,2],1)
    # A thin white frill may have only red hair as its nearest eroded seed.
    # Never transfer that material's hue into lace: G cannot drop below R/B.
    corrected=np.minimum(rgb[...,1],np.maximum(nearest[...,1]*ratio,np.minimum(rgb[...,0],rgb[...,2])))
    out[...,1][edge]=np.rint(corrected[edge]).astype(np.uint8)
    # Thin auburn strands can be contaminated through their entire width and
    # therefore have no clean eroded seed. The approved red hair has G near B,
    # unlike a yellow-green fringe. Constrain only the narrow silhouette collar.
    depth=cv2.distanceTransform((a>127).astype(np.uint8),cv2.DIST_L2,3)
    hair_edge=(a>8)&(depth<=4)&(rgb[...,0]>rgb[...,2]+25)&(rgb[...,1]>rgb[...,2]+10)
    ceiling=rgb[...,2]+.30*(rgb[...,0]-rgb[...,2])
    hair_edge&=rgb[...,1]>ceiling
    out[...,1][hair_edge]=np.minimum(out[...,1][hair_edge],np.rint(ceiling[hair_edge])).astype(np.uint8)
    return out,int((edge|hair_edge).sum())


def clear_hair_islands(rgba,details=None):
    result=rgba.copy()
    rgb=rgba[...,:3].astype(np.int16); alpha=rgba[...,3]
    yy,xx=np.where(alpha>127)
    if not len(xx):return result,0
    left,right,top,bottom=xx.min(),xx.max(),yy.min(),yy.max()
    width=max(1,right-left);height=max(1,bottom-top)
    face=face_protection(rgb,alpha,(left,right,top,bottom))
    white=(rgb.min(2)>220)&(np.ptp(rgb,axis=2)<35)&(alpha>240)
    hair=(rgb[...,0]-rgb[...,1]>20)&(rgb[...,0]-rgb[...,2]>15)&(rgb[...,0]>60)&(rgb[...,0]<240)
    skin=(rgb[...,0]>175)&(rgb[...,1]>125)&(rgb[...,2]>100)&(rgb[...,0]-rgb[...,1]<75)&(np.abs(rgb[...,1]-rgb[...,2])<50)
    count,labels,stats,centers=cv2.connectedComponentsWithStats(white.astype(np.uint8))
    holes=np.zeros(alpha.shape,np.uint8)
    radius=max(2,round(height/90))
    kernel=np.ones((2*radius+1,2*radius+1),np.uint8)
    for i in range(1,count):
        x,y,w,h,area=stats[i];cx,cy=centers[i]
        nx=(cx-left)/width;ny=(cy-top)/height
        if not ((nx<.30 or nx>.70) and .20<ny<.84):continue
        if not 3<=area<=width*height*.004:continue
        component=(labels==i).astype(np.uint8)
        ring=(cv2.dilate(component,kernel)>0)&(~component.astype(bool))&(alpha>200)&(~white)
        if not ring.any():continue
        hair_fraction=float(hair[ring].mean());skin_fraction=float(skin[ring].mean())
        narrow=w<=1.05*h and w<=width*.075
        # Side-facing flowing hair has horizontal negative spaces too. Allow
        # these only at the outer 20% with strong hair enclosure. White apron
        # folds have dark/neutral surrounds; eye whites have blue/skin surrounds.
        outer_horizontal=(nx<.20 or nx>.80) and ny<.78 and hair_fraction>=.70 and w<=width*.22 and h<=height*.18
        # Pale human ears sit near the inner edge of the side locks; cuffs sit
        # near hands in the lower half. Bright outer hair can itself satisfy a
        # peach-color test, so do not treat that as an ear outside the upper
        # central 60% of the figure. This preserves ears without leaving the
        # adjacent outer temple hair gap opaque white.
        skin_protected=skin_fraction>=.12 and (ny>=.58 or .20<=nx<=.80)
        median=np.median(rgb[component>0],axis=0)
        peach_protected=median[0]-median[1]>=4 and median[0]-median[2]>=8
        face_protected=bool((face&(component>0)).any())
        accepted=hair_fraction>=.55 and not (skin_protected or peach_protected or face_protected) and (narrow or outer_horizontal)
        if details is not None:
            details.append({'box':[int(x),int(y),int(w),int(h)],'area':int(area),
                'position':[float(nx),float(ny)],'hair_fraction':hair_fraction,'skin_fraction':skin_fraction,
                'skin_protected':bool(skin_protected),'peach_protected':bool(peach_protected),'face_protected':face_protected,
                'median_rgb':median.tolist(),'narrow':bool(narrow),'outer_horizontal':bool(outer_horizontal),'accepted':bool(accepted)})
        if not accepted:continue
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
