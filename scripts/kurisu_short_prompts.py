"""Compact H3 Ref2VA prompts: six sections, one action, one digital matte."""
import re

NO_PROPS={'待机','转向','拖拽','点击回应'}
GESTURES={'原地轻步行走','原地小跑','伸懒腰','打哈欠','原地打盹','打盹被惊醒','整理围裙','整理猫耳发箍','屈膝女仆礼','抱臂轻哼','歪头疑惑','原地转圈展示','惊讶后整理仪态','捧脸发呆','轻快女仆舞','扶额无语','认真反驳','工作状态-托腮推理','工作状态-抱臂等确认'}


def prompt_for(action,direction,prepared_reference=False):
    # Costume colors come from the image; keeping a lengthy color/negative list
    # out of the text avoids competing background instructions.
    direction=re.sub(r'\bwhite\b','ivory',direction,flags=re.I).strip()
    moving=action['group']=='移动'
    empty=action['group'] in NO_PROPS or action['name'] in GESTURES
    props='Her hands stay empty.' if empty else 'Named miniature props stay below her eyes, retrieved and stowed behind her body.'
    if moving:
        gesture={'原地轻步行走':'Walk in place with alternating side-view steps.','原地小跑':'Jog in place with quick alternating side-view steps and small bent-arm swings.','抱笔记本侧身挪步':'Hold a small closed gray laptop at waist height and take tiny side-view steps in place.'}.get(action['name'],direction)
        timeline=('00:00.000 to 00:02.000: pivot from front into strict SCREEN-LEFT profile. '
            '00:02.000 to 00:08.000: '+gesture+' Nose, torso, knees and both shoe tips point LEFT; the far eye is naturally occluded. Horizontal center stays fixed. '
            '00:08.000 to 00:09.000: stop and turn smoothly to front. 00:09.000 to 00:10.000: hold the reference stance with empty hands.')
    else:
        timeline=('00:00.000 to 00:02.000: reference front stance; prepare the gesture or prop. '
            '00:02.000 to 00:07.000: '+direction+' '
            '00:07.000 to 00:09.000: lower hands and stow each prop smoothly. '
            '00:09.000 to 00:10.000: hold the reference front stance with empty hands.')
    laptop=(' A laptop screen and keyboard face HER; its plain matte gray exterior back lid faces the camera. The closed prop is a rigid clamshell with a hinge.' if 'laptop' in direction.lower() or 'laptop' in timeline.lower() else '')
    return f'''subject_definitions:
<Subject 1> is the human chibi Kurisu maid in <Picture 1>, with fabric costume ears on her headband. Preserve her auburn hair, blue-violet eyes, costume, large round head and short plump body. Her rear silhouette consists solely of long hair and skirt. NO tail.

summary:
[reference generation] One 10-second full-body animation of <Subject 1> against a flat saturated GREEN digital matte, RGB(0,255,0).

retention_analysis:
<Subject 1> ([Shot 1]): fully_preserved identity, proportions and painted palette.
<Picture 1> ([Shot 1]): fully_preserved character, wide framing, opening and ending posture.

detailed_description:
[Shot 1] 00:00.000 to 00:10.000. Fixed eye-level orthographic camera; center the complete figure at reference scale: ear tips at 20%, standing soles at 85% of frame height. Character colors remain exactly the reference under uniform neutral illumination. Painted highlights stay fixed. Only the named action is animated; NO added light effects or symbols. Every background pixel stays the same flat saturated GREEN RGB(0,255,0) throughout, including spaces between hair locks and around hands and shoes. Wide green margins surround the figure and props. A separate digital matte, delicate outlines and soft 2D cel shading. {props}{laptop}

{timeline}

overall_soundscape:
Silence.

non_diegetic_music:
N/A.
'''
