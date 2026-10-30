#!/usr/bin/env python3
"""Explicitly adjust a candidate matte after inspecting its actual green level."""
import argparse
import shutil
from kurisu_library import load,save,production_lock,PACK,ROOT,convert,now


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',required=True);p.add_argument('--key-high',type=float,required=True)
    args=p.parse_args()
    with production_lock():
        s=load();a=next(a for a in s['actions'] if a['id']==args.action)
        assert a['status']=='awaiting_review'
        t=a['attempts'][-1]
        source=PACK/t.get('local_edit',{}).get('source_file',t['source_file'])
        output=source.parent/(a['name']+'.webm')
        report=convert(source,output,shutil.which('ffmpeg'),shutil.which('ffprobe'),ROOT/'temp/kurisu/render',True,12,args.key_high)
        t['report']=report;t['candidate_file']=str(output.relative_to(PACK));t.pop('processing_error',None)
        t.setdefault('matte_edits',[]).append({'at':now(),'thresholds':[12,args.key_high],
            'reason':'Inspected source uses a darker green matte; remove residual translucent background without changing foreground colors'})
        save(s)
