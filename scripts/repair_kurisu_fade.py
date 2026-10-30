#!/usr/bin/env python3
"""Remove an observed leading fade by holding the first clean neutral frame.

This is an explicit local edit, never a model retry. Keeps exactly 240 frames.
"""
import argparse
import shutil
import subprocess
from kurisu_library import load, save, production_lock, PACK, ROOT, convert, now


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',required=True);p.add_argument('--frames',required=True,type=int)
    args=p.parse_args()
    if not 0 < args.frames <= 24:
        p.error('Only an inspected leading fade shorter than one second can be repaired')
    with production_lock():
        state=load();a=next(a for a in state['actions'] if a['id']==args.action)
        assert a['status']=='awaiting_review'
        t=a['attempts'][-1];source=PACK/t['source_file']
        corrected=source.with_name(source.stem+'-opening-repaired.mp4')
        partial=corrected.with_suffix('.partial.mp4')
        subprocess.run(['ffmpeg','-y','-v','error','-i',str(source),'-an','-vf',
            f'fps=24,trim=start_frame={args.frames},setpts=PTS-STARTPTS,tpad=start={args.frames}:start_mode=clone',
            '-frames:v','240','-c:v','libx264','-crf','16','-pix_fmt','yuv420p',str(partial)],check=True)
        partial.replace(corrected)
        candidate=PACK/t['candidate_file']
        report=convert(corrected,candidate,shutil.which('ffmpeg'),shutil.which('ffprobe'),ROOT/'temp/kurisu/render',True)
        t['local_edit']={'type':'hold_clean_opening_frame','frames':args.frames,
            'reason':'Observed model-generated leading brightness fade during neutral opening only',
            'edited_at':now(),'source_file':str(corrected.relative_to(PACK))}
        t['report']=report;t.pop('processing_error',None);save(state)


if __name__=='__main__':main()
