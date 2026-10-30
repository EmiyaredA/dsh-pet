#!/usr/bin/env python3
"""Replace a103's impossible back-cover UI with its own observed gray lid surface.

No model calls. Tracks the lid only, protects overlapping hands, keeps the original
outline/hinge and applies the existing green-matte pipeline to all 240 frames.
"""
import io
import json
import shutil
import subprocess
import cv2
import numpy as np
from PIL import Image
from build_pet_pack import key_green
from kurisu_library import PACK,ROOT,load,save,production_lock,convert,now,calls


def lid_region(rgb):
    h,w=rgb.shape[:2];v=rgb.astype(np.int16);r,g,b=[v[...,i] for i in range(3)]
    mask=((v.min(2)>35)&(v.max(2)<200)&(b>=r-12)&(g>=r-15)).astype(np.uint8)
    roi=np.zeros((h,w),np.uint8);roi[int(.495*h):int(.77*h),int(.383*w):int(.607*w)]=1
    mask*=roi
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    for c in sorted(contours,key=cv2.contourArea,reverse=True):
        _,_,cw,ch=cv2.boundingRect(c)
        if cv2.contourArea(c)>12000 and 160<cw<300 and 50<ch<195:
            full=np.zeros_like(mask);cv2.drawContours(full,[c],-1,1,cv2.FILLED)
            return cv2.boxPoints(cv2.minAreaRect(c)).astype(np.float32),full
    return None,None


class RearLidMatte:
    name='green_difference_with_tracked_plain_rear_lid'

    def __init__(self,reference):
        quad,mask=lid_region(reference)
        if quad is None:raise ValueError('Clean gray reference lid not found')
        self.reference_quad=quad;self.edits=[];self.pixels=0
        # Fit only the original, plain gray interior; the finger at the rim is excluded.
        inside=cv2.erode(mask,np.ones((17,17),np.uint8)).astype(bool)
        v=reference.astype(np.int16);inside&=(np.ptp(v,axis=2)<35)&(v.min(2)>40)
        yy,xx=np.where(inside);design=np.column_stack([np.ones(len(xx)),xx,yy])
        self.coefficients=np.linalg.lstsq(design,reference[inside],rcond=None)[0]
        h,w=reference.shape[:2];y,x=np.mgrid[:h,:w]
        self.surface=np.clip(np.stack([np.ones_like(x),x,y],axis=2)@self.coefficients,35,180).astype(np.uint8)

    def __call__(self,rgb,index):
        quad,mask=lid_region(rgb);frame=rgb.copy();h,w=rgb.shape[:2]
        if quad is not None:
            transform=cv2.getPerspectiveTransform(self.reference_quad,quad)
            surface=cv2.warpPerspective(self.surface,transform,(w,h),flags=cv2.INTER_LINEAR)
            v=rgb.astype(np.int16);r,g,b=[v[...,i] for i in range(3)]
            skin=((r>150)&(r-g>12)&(g-b>5)).astype(np.uint8)
            skin=cv2.dilate(skin,np.ones((5,5),np.uint8))
            mask&=(1-skin)
            opacity=np.minimum(cv2.distanceTransform(mask,cv2.DIST_L2,3)/1.5,1)[...,None]
            frame=np.rint(frame*(1-opacity)+surface*opacity).astype(np.uint8)
            self.pixels+=int(mask.sum());self.edits.append({'frame':index,'quad':quad.round(2).tolist()})
        # An untracked data display must fail instead of being silently delivered.
        v=frame.astype(np.int16);r,g,b=[v[...,i] for i in range(3)]
        blue=(b-r>24)&(g-r>12)&(b<200)&(g<190)
        # Inspection confirms the source UI is off by frame 162. During folding,
        # the blouse's blue shadows enter this ROI and are not screen content.
        if index<=161 and int(blue[int(.495*h):int(.74*h),int(.40*w):int(.60*w)].sum())>100:
            raise ValueError(f'Unremoved or untracked screen content in frame {index}')
        return key_green(frame,12,65)


if __name__=='__main__':
    with production_lock():
        s=load();before=calls(s);a=next(a for a in s['actions'] if a['id']=='a103')
        assert a['status']=='exhausted' and len(a['attempts'])==2
        t=a['attempts'][-1];source=PACK/t['source_file']
        png=subprocess.check_output(['ffmpeg','-v','error','-ss','2','-i',str(source),'-frames:v','1','-f','image2pipe','-vcodec','png','-'])
        reference=np.asarray(Image.open(io.BytesIO(png)).convert('RGB'))
        matte=RearLidMatte(reference);candidate=source.parent/(a['name']+'.webm')
        report=convert(source,candidate,shutil.which('ffmpeg'),shutil.which('ffprobe'),ROOT/'temp/kurisu/render',True,frame_matte=matte,lossless=True)
        if not matte.edits:raise ValueError('No lid surfaces repaired')
        tracking=source.parent/'rear-lid-tracking.json';tracking.write_text(json.dumps(matte.edits,indent=2)+'\n')
        if t.get('local_edit'):t.setdefault('previous_local_edits',[]).append(t['local_edit'])
        t['local_edit']={'type':matte.name,'reference_source_frame':48,'reference_time_seconds':2,
            'frames_repaired':len(matte.edits),'pixels_repaired':matte.pixels,'tracking_file':str(tracking.relative_to(PACK)),
            'reason':'User identified impossible screen information on the rear lid; reconstruct only the same-video gray exterior surface, preserving hands, outline and hinge',
            'edited_at':now(),'new_model_calls':0}
        t['report']=report;t['candidate_file']=str(candidate.relative_to(PACK));t.pop('processing_error',None)
        a['status']='awaiting_review';assert calls(s)==before;save(s)
        print(json.dumps({'action':'a103','repaired_frames':len(matte.edits),'new_model_calls':0}))
