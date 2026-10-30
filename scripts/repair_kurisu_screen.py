#!/usr/bin/env python3
"""Neutralize accidental green UI pixels before keying a reviewed laptop clip.

Edits only green patches in the waist-level screen during the open-screen phase;
the source model result is retained. This is local video matte repair, not generation.
"""
import argparse
import shutil
import subprocess
import tempfile
import numpy as np
from kurisu_library import load,save,production_lock,PACK,ROOT,convert,now
from build_pet_pack import probe,read_frame


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',required=True);p.add_argument('--key-high',type=float,default=65)
    args=p.parse_args()
    with production_lock():
        s=load();a=next(a for a in s['actions'] if a['id']==args.action)
        assert a['status']=='awaiting_review' and 'laptop' in a['direction'].lower()
        t=a['attempts'][-1];source=PACK/t['source_file'];video=probe(source,shutil.which('ffprobe'))['streams'][0]
        w,h=video['width'],video['height'];corrected=source.with_name(source.stem+'-screen-repaired.mp4')
        partial=corrected.with_suffix('.partial.mp4');changed=0;count=0
        with tempfile.TemporaryFile() as errors:
            decoder=subprocess.Popen(['ffmpeg','-v','error','-i',str(source),'-t','10','-vf','fps=24','-f','rawvideo','-pix_fmt','rgb24','-'],stdout=subprocess.PIPE,stderr=errors)
            encoder=subprocess.Popen(['ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{w}x{h}','-r','24','-i','-','-an','-c:v','libx264','-crf','16','-pix_fmt','yuv420p',str(partial)],stdin=subprocess.PIPE,stderr=errors)
            try:
                while data:=read_frame(decoder.stdout,w*h*3):
                    frame=np.frombuffer(data,np.uint8).reshape(h,w,3).copy()
                    if 72<=count<=180:
                        region=frame[int(.48*h):int(.76*h),int(.40*w):int(.62*w)]
                        values=region.astype(np.int16);red,green,blue=values[...,0],values[...,1],values[...,2]
                        mask=(red>80)&(blue>80)&(green>np.maximum(red,blue)+12)
                        neutral=(red+blue)//2
                        region[...,0][mask]=np.clip(neutral[mask]-4,0,255)
                        region[...,1][mask]=np.clip(neutral[mask],0,255)
                        region[...,2][mask]=np.clip(neutral[mask]+8,0,255)
                        changed+=int(mask.sum())
                    encoder.stdin.write(frame.tobytes());count+=1
            except BaseException:
                decoder.terminate();encoder.terminate();raise
            finally:
                decoder.stdout.close();encoder.stdin.close();decoder.wait();encoder.wait()
            if decoder.returncode or encoder.returncode:
                errors.seek(0);raise RuntimeError(errors.read().decode(errors='replace'))
        assert count==240 and changed>0
        partial.replace(corrected)
        output=source.parent/(a['name']+'.webm')
        report=convert(corrected,output,shutil.which('ffmpeg'),shutil.which('ffprobe'),ROOT/'temp/kurisu/render',True,12,args.key_high)
        t['local_edit']={'type':'neutralize_accidental_green_screen_pixels','frames':[72,180],
            'normalized_roi':[.40,.48,.62,.76],'pixels_changed':changed,'source_file':str(corrected.relative_to(PACK)),
            'reason':'Keep the laptop screen opaque while removing chroma-key spill; lower key threshold removes green cast shadow',
            'edited_at':now()}
        t['candidate_file']=str(output.relative_to(PACK));t['report']=report;t.pop('processing_error',None);save(s)
        print({'action':a['id'],'local_pixels_repaired':changed,'model_calls_added':0})


if __name__=='__main__':main()
