#!/usr/bin/env python3
"""Composite selected decoded Alpha frames for human edge and motion review."""
import argparse
from pathlib import Path
import subprocess
from PIL import Image, ImageDraw


def contact(path, output):
    selected = [0,48,96,144,192,239]
    expression = '+'.join('eq(n\\,'+str(i)+')' for i in selected)
    raw = subprocess.check_output(['ffmpeg','-v','error','-c:v','libvpx-vp9','-i',str(path),
        '-vf','select='+expression,'-fps_mode','passthrough','-pix_fmt','rgba','-f','rawvideo','-'])
    size = 640*360*4
    assert len(raw) == len(selected)*size
    result = Image.new('RGB',(6*256,3*144))
    for i in range(6):
        frame = Image.frombytes('RGBA',(640,360),raw[i*size:(i+1)*size])
        for j,color in enumerate(['#fafafa','#171821','#cccccc']):
            bg = Image.new('RGBA',frame.size,color)
            if j==2:
                draw = ImageDraw.Draw(bg)
                for y in range(0,360,20):
                    for x in range(0,640,20):
                        if (x//20+y//20)%2:
                            draw.rectangle((x,y,x+19,y+19),fill='#eeeeee')
            bg.alpha_composite(frame)
            result.paste(bg.convert('RGB').resize((256,144)),(i*256,j*144))
    output.parent.mkdir(parents=True,exist_ok=True)
    result.save(output)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args();contact(args.input,args.output)
