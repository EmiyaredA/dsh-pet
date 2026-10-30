#!/usr/bin/env python3
"""Bounded, resumable FPL video production. Each tick performs one explicit pass.

Use the FPL SDK on PYTHONPATH. No database/config access, implicit model retries,
or unattended visual approval. `review` records the operator's visual judgement.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import numpy as np
from uuid import uuid4
from contextlib import contextmanager

from build_pet_pack import convert

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / 'pet-packs/kurisu'
STATE = PACK / 'library.json'
ACTIVE = {'queued', 'submitting', 'pending', 'processing'}


def now():
    return datetime.now(timezone.utc).isoformat()


def save(state):
    state['updated_at'] = now()
    temp = STATE.with_suffix('.next.json')
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
    temp.replace(STATE)
    if STATE == PACK / 'library.json':
        lines = ['# 红莉栖 106 条动作生产清单', '',
                 f"新调用：{calls(state)} / {state['limits']['total_calls']}。状态以 library.json 为准。", '',
                 '| ID | 分类 | 动作 | 批次 | 状态 | 调用 | 任务 |', '|---|---|---|---|---|---|---|']
        for a in state['actions']:
            tasks = '<br>'.join(t.get('task_id','提交待核对') for t in a['attempts']) or '复用'
            lines.append(f"| {a['id']} | {a['group']} | {a['name']} | {a.get('batch','—')} | {a['status']} | {len(a['attempts'])} | {tasks} |")
        (PACK/'ACTIONS.md').write_text('\n'.join(lines)+'\n')


def load():
    return json.loads(STATE.read_text())


def calls(state):
    return sum(len(a['attempts']) for a in state['actions'])


def can_submit(state, action):
    model = action.get('next_model_id', state.get('model_id'))
    other_calls = sum(t.get('model_id', state.get('model_id')) != state.get('model_id')
                      for a in state['actions'] for t in a['attempts'])
    attempt_limit = state.get('action_attempt_limits',{}).get(action.get('id'),2)
    return (calls(state) < state['limits']['total_calls'] and len(action['attempts']) < attempt_limit
            and (model == state.get('model_id') or other_calls < state['limits'].get('other_model_calls', 2))
            and (not action['attempts'] or sum(max(0, len(a['attempts']) - 1)
                 for a in state['actions']) < state['limits']['repair_calls']))


@contextmanager
def production_lock():
    path = STATE.with_suffix('.lock')
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        owner = json.loads(path.read_text())
        try:
            os.kill(owner['pid'], 0)
        except PermissionError:
            raise RuntimeError('Another production command is running with different sandbox permissions')
        except ProcessLookupError:
            path.unlink()
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        else:
            raise RuntimeError('Another production command is running')
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump({'pid': os.getpid(), 'created_at': now()}, out)
        yield
    finally:
        path.unlink(missing_ok=True)


def prompt_for(action, direction, prepared_reference=False):
    moving = action['group'] == '移动'
    no_props = action['group'] in {'待机', '转向', '拖拽', '点击回应'} or action['name'] in {
        '原地轻步行走', '原地小跑', '伸懒腰', '打哈欠', '原地打盹', '打盹被惊醒',
        '整理围裙', '整理猫耳发箍', '屈膝女仆礼', '抱臂轻哼', '歪头疑惑',
        '原地转圈展示', '惊讶后整理仪态', '捧脸发呆', '轻快女仆舞',
        '扶额无语', '认真反驳', '工作状态-托腮推理', '工作状态-抱臂等确认',
        }
    timing = ('From 00:00.000 to 00:00.500 hold the neutral FRONT stance, then pivot into a strict '
              'SCREEN-LEFT side profile by 00:02.000, preparing only an expressly named prop. '
              'From 00:02.000 to 00:08.000 perform the following SIDE-VIEW treadmill gait, accelerating gently '
              'at the start and stopping by 00:08.000: ' if moving else
              'From 00:00.000 to 00:01.000 hold the exact calm front standing pose. '
              'From 00:01.000 to 00:02.000 prepare the small gesture or take the compact prop '
              'from behind the body. From 00:02.000 to 00:07.000 perform this clear action: ')
    if no_props and not moving:
        timing = ('From 00:00.000 to 00:02.000 hold the neutral empty-handed stance. '
                  'From 00:02.000 to 00:07.000 perform ONLY this body gesture: ')
    prop = ('Both hands remain EMPTY throughout. There are NO props, cards, signs, books, '
            'notebooks, badges, tools or other objects in this shot.' if no_props else
            'Only props expressly named in the action are allowed. '
            'Props use ivory, gray, muted red, pink, amber or blue; never green. Keep them miniature '
            'and centered in front of the waist, below the face where possible. The face, both ears '
            'and shoes stay visible. Confine any expressly requested spark effect to the tiny prop; '
            'it never lights the character. Do not invent other effects, animals or objects.')
    finish = ('From 00:08.000 to 00:09.000 stop the side-view steps, pivot from SCREEN-LEFT profile '
              'back to the original FRONT standing stance, stow any explicitly named prop and lower both hands.'
              if moving else 'From 00:07.000 to 00:09.000 smoothly finish the gesture, lower the hands and face forward. '
              'Any explicitly requested props are completely stowed; no new object is introduced.')
    reference_description = (
        '<Picture 1> is the sole character and body-proportion reference, prepared by proportional '
        'scaling of the approved original onto a green canvas, without changing any character detail. '
        'PRESERVE THIS EXACT WIDE FRAMING: the ear tips are at 20% frame height, the soles at 85%, '
        'and the body center at 50% frame width. Keep the broad empty green margins throughout. '
        'Do not crop the image, enlarge the figure to fill the frame or elongate the body. '
        'The neutral FRONT posture in this image is the beginning and ending pose.'
        if prepared_reference else
        '<Picture 1> is the sole character and body-proportion reference, defining the neutral FRONT '
        'standing posture for the beginning and end. Use it for identity and relative anatomical '
        'proportions; its tight framing is NOT the target composition. Draw the same complete figure '
        'smaller within a wider uniform digital #00FF00 matte. Do not reference a character sheet or elongate the body.')
    laptop_geometry=('PHYSICAL LAPTOP ORIENTATION: whenever she uses the laptop, its screen and keyboard face HER. '
        'The camera sees only the plain matte gray EXTERIOR BACK LID and rear hinge. Never render a screen, '
        'data, interface, keyboard, webcam or glowing logo on that outward-facing back cover. '
        'When she carries the closed laptop, show a rigid gray metal clamshell with hinge and side vents, never paper pages.'
        if 'laptop' in direction.lower() else '')
    return f'''subject_definitions:
<Subject 1> is the SINGLE approved HUMAN chibi girl Kurisu wearing a maid costume and a detachable cat-ear HEADBAND in <Picture 1>. Her anatomy is entirely HUMAN; the two black fabric triangles with pink interiors are costume accessories on the white lace headband, not animal body parts. Preserve the exact large round head, short slightly plump body and limbs, chestnut-auburn long hair, blue-violet eyes and two pink bows. Preserve the black-and-white frilled maid dress, white puff sleeves and bib, pink neck ribbon and zigzag trim, gray belt and silver buckle, dark stockings and black shoes. The back ends at the skirt and hair; NO animal tail or other appendage exists. NO silver hair clips.
{reference_description}

summary:
[reference generation] A single locked-off full-body 10-second 2D desktop-pet sprite shot of <Subject 1>. The specific action is: {direction} {prop} Return to the identical clean front standing pose, with a fixed palette on a solid digital green matte.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - retain the exact approved identity, rounded squat proportions, hair and eye colors, complete headwear, costume layers and shoes. Only the specified gesture, expression and temporary props change.
<Picture 1> ([Shot 1] opening and ending pose target): fully_preserved - same neutral front posture, relaxed hands, open eyes and small closed smile, and relative body proportions. Place the whole figure at the smaller target scale with ear tips at 20% and soles at 85% of frame height; extend the empty digital green area around it.

detailed_description:
Match the delicate dark outlines and soft 2D cel shading in <Picture 1>, like a clean game animation sprite. [Shot 1] A single fixed eye-level orthographic full-body view lasts exactly 10 seconds. Keep the character centered with ear tips near 20% frame height and soles near 85%, leaving generous empty margins for hands, hair and props. Maintain the approved large head and short round body. Do not translate the entire figure horizontally, travel toward the camera, zoom, pan, cut, reframe or change body scale. Turning and stepping happen in place around the same body axis; the runtime will move the desktop window separately.

BACKGROUND THROUGHOUT [Shot 1], 00:00.000–00:10.000: a perfectly flat, fully saturated digital RGB (0,255,0), #00FF00 chroma-key green matte occupies EVERY background pixel in EVERY frame. Preserve this green behind the figure AND inside all visible negative spaces between hair locks, arms, body, props and skirt. These empty gaps remain green when they open or close. The first frame, all action frames and the final frame have exactly the same green. Never replace it with white, off-white, gray, black, blue, transparency, a checkerboard, a floor or a studio backdrop. No fade, background transition, gradient, cast shadow or background texture. The green is a digital compositing layer; it does not illuminate the subject.

Use FIXED PALETTE COLORS and constant neutral even frontal illumination on the CHARACTER ONLY in every frame. Chestnut hair, pale skin, neutral white lace, charcoal clothes, pink bows and blue-violet eyes keep their original hues and brightness. Existing painted highlights stay attached to surfaces. No colored illumination, green reflection, green edge spill, moving light, rainbow wash, animated highlights, body glow, lens flare, bokeh, floating hearts, symbols or unsolicited particles. White lace remains opaque neutral white and is distinct from the saturated green in the surrounding hair gaps. Neutral subject lighting must never become a white background.

{timing}{direction}

{prop}

{laptop_geometry}

{finish} From 00:09.000 through 00:10.000 hold EXACTLY the opening calm FRONT standing pose: eyes open, tiny closed smile, arms relaxed, hands empty and both shoes level on the original baseline. Hair, frills and headwear settle to their opening outlines. No prop, animal, particle or extra object remains. Use smooth natural easing, structurally correct hands and stable costume details. All content remains inside the central safe area, at least 10% from every frame edge. Do not draw any readable text, labels, digits, logos, captions or watermarks.

overall_soundscape:
Silent. No speech, breath, footsteps, ambient sound or sound effects.

non_diegetic_music:
N/A. No music.
'''


def initialize():
    if STATE.exists():
        raise ValueError('Library exists; resume it rather than initialize again')
    previous = json.loads((PACK / 'production.json').read_text())
    groups = json.loads((PACK / 'action-groups.json').read_text())
    directions = json.loads((PACK / 'action-directions.json').read_text())
    actions = []
    for gi, (group, names) in enumerate(groups.items()):
        assert len(directions[group]) == len(names)
        for index, name in enumerate(names):
            ordinal = len(actions) + 1
            reused = name in ['待机呼吸', '点击回应-傲娇']
            action = {'id': f'a{ordinal:03d}', 'name': name, 'group': group,
                      'category_id': f'kurisu-group-{gi:02d}',
                      'node_id': ('idle' if name == '待机呼吸' else 'tsundere') if reused else f'kurisu-a{ordinal:03d}',
                      'status': 'approved' if reused else 'planned', 'reused': reused,
                      'attempts': [], 'direction': directions[group][index]}
            prompt_path = PACK / 'prompts/library' / (action['id'] + '.txt')
            prompt_path.parent.mkdir(exist_ok=True)
            prompt_path.write_text(prompt_for(action, action['direction']))
            action['prompt_file'] = str(prompt_path.relative_to(PACK))
            if reused:
                delivery = next(d for d in previous['deliveries'] if Path(d['file']).stem == name)
                action['file'] = delivery['file']; action['sha256'] = delivery['sha256']
                action['delivery_asset_id'] = delivery['fpl_asset_id']
            actions.append(action)
    assert len(actions) == 106 and len({a['name'] for a in actions}) == 106
    priority = ['转向', '拖拽', '点击回应', '移动', '工作状态', '余额', '碎碎念',
                '日常小动作', '研究与玩耍', '饮食', '时节', '吐槽与思考']
    pending = sorted([a for a in actions if not a['reused']], key=lambda a: (priority.index(a['group']), a['id']))
    for i, a in enumerate(pending):
        a['batch'] = i // 12 + 1; a['queue_order'] = i
    state = {'schema_version': 1, 'project_id': previous['fpl']['project_id'],
             'reference_asset_id': previous['assets']['candidate-maid-cat-ears']['fpl_asset_id'],
             'reference_sha256': previous['assets']['candidate-maid-cat-ears']['sha256'],
             'model_id': previous['video_settings']['model_id'], 'model_slug': 'minimax_h3_zm_nono',
             'limits': {'total_calls': 130, 'repair_calls': 26, 'attempts_per_action': 2,
                        'concurrent_tasks': 2, 'other_model_calls': 2},
             'excluded_models': ['doubao-seedance-2-0-260128', 'U17-9图1视频3音频V1-api', 'U06-9图3音频-V5'],
             'created_at': now(), 'stage': 'initialized', 'actions': actions}
    save(state)
    previous['full_library'] = {'state_file': 'library.json', 'target_actions': 106, 'new_actions': 104, 'call_limit': 130}
    previous['stage'] = 'expanding_library'
    (PACK / 'production.json').write_text(json.dumps(previous, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(status(state), ensure_ascii=False))


def status(state):
    counts = {}
    for a in state['actions']:
        counts[a['status']] = counts.get(a['status'], 0) + 1
    return {'stage':state.get('stage'),'blocker':state.get('blocker'),
            'states': counts, 'calls': calls(state), 'limit': state['limits']['total_calls'],
            'awaiting_review': [{'id': a['id'], 'name': a['name'], 'contact': a['attempts'][-1].get('contact')}
                                for a in state['actions'] if a['status'] == 'awaiting_review']}


def setup(client, state):
    canvas = client.visual.get_canvas(project_id=state['project_id'])
    nodes = [n.model_dump(mode='json', exclude_none=True) for n in canvas.nodes]
    existing = {n['id'] for n in nodes}
    categories = [c.model_dump(mode='json') for c in canvas.categories]
    known = {c['id'] for c in categories}
    for a in state['actions']:
        if a['category_id'] not in known:
            categories.append({'id': a['category_id'], 'name': a['group'], 'groups': []}); known.add(a['category_id'])
        if a['node_id'] in existing:
            continue
        i = int(a['id'][1:])
        nodes.append({'id': a['node_id'], 'kind': 'video', 'title': a['name'],
                      'category_id': a['category_id'], 'position': {'x': (i % 8) * 430, 'y': 1700 + (i // 8) * 360},
                      'generation_draft': {'model_id': state['model_id'], 'mode': 'reference', 'duration': 10,
                         'ratio': '16:9', 'resolution': '768p', 'prompt': (PACK / a['prompt_file']).read_text(),
                         'reference_asset_ids': [state['reference_asset_id']]}})
    client.visual.put_canvas(project_id=state['project_id'], body={'expected_revision': canvas.revision,
        'nodes': nodes, 'edges': [e.model_dump(mode='json', exclude_none=True) for e in canvas.edges], 'categories': categories})
    state['stage'] = 'producing'; state['canvas_setup_complete'] = True; save(state)


def prepare_result(client, state, action, attempt):
    folder = PACK / 'source/library' / action['id'] / ('attempt-' + str(len(action['attempts'])))
    folder.mkdir(parents=True, exist_ok=True)
    raw = folder / (action['name'] + '.mp4')
    if not raw.exists():
        partial = raw.with_suffix('.download')
        with client.files.download_file(asset_id=attempt['result_asset_id']) as data:
            data.save(partial)
        partial.replace(raw)
    attempt['source_file'] = str(raw.relative_to(PACK)); save(state)
    contact = ROOT / 'temp/kurisu/library/review' / (action['id'] + '-attempt-' + str(len(action['attempts'])) + '.png')
    contact.parent.mkdir(parents=True, exist_ok=True)
    if not contact.exists():
        select = '+'.join('eq(n\\,' + str(n) + ')' for n in list(range(0, 240, 24)) + [239])
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(raw), '-vf',
            f'fps=24,select={select},scale=320:-2,tile=4x3:nb_frames=11:padding=4:color=white',
            '-frames:v', '1', str(contact)], check=True)
    attempt['contact'] = str(contact); save(state)
    # The supplier sometimes substitutes white after an initially green frame.
    # Inspect every decoded frame BEFORE any conversion or acceptance; never
    # hide a failed background behind the former white-matte fallback.
    try:
        background = source_green_background(raw)
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        attempt['processing_error'] = 'Green-background validation could not finish: ' + str(exc)
        action['status'] = 'awaiting_review'; save(state); return
    attempt['source_background'] = background
    if not background['passed']:
        attempt['processing_error'] = ('Source must use uniform saturated green in every frame; '
            f"background failed on {background['failed_frame_count']} of {background['frames']} frames")
        action['status'] = 'awaiting_review'; save(state); return
    attempt.pop('processing_error', None)
    clip = folder / (action['name'] + '.webm')
    if not clip.exists():
        try:
            report = convert(raw, clip, shutil.which('ffmpeg'), shutil.which('ffprobe'), ROOT / 'temp/kurisu/render', False)
            attempt['report'] = report
        except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
            attempt['processing_error'] = str(exc)
    else:
        attempt['report'] = json.loads(clip.with_suffix('.report.json').read_text())
    if clip.exists():
        attempt['candidate_file'] = str(clip.relative_to(PACK))
        write_alpha_contact(action,attempt,clip)
    action['status'] = 'awaiting_review'; save(state)


def write_alpha_contact(action,attempt,clip):
    digest=hashlib.sha256(clip.read_bytes()).hexdigest()[:12]
    contact=ROOT/'temp/kurisu/library/review'/(action['id']+'-alpha-'+digest+'.png')
    if not contact.exists():
        subprocess.run([sys.executable,str(ROOT/'scripts/kurisu_review_contact.py'),str(clip),str(contact)],check=True)
    attempt['alpha_contact']=str(contact)


def green_background_frames(frames):
    """Every frame must retain one flat saturated green border, with codec tolerance.

    The reduced outer border is outside the mandated 10% content-safe area.
    This is a source-background gate, separate from silhouette/edge visual QA.
    """
    if frames.ndim != 4 or frames.shape[-1] != 3 or not len(frames):
        raise ValueError('No complete RGB source frames')
    rgb=frames.astype(np.int16)
    border=np.concatenate([rgb[:,0],rgb[:,-1],rgb[:,:,0],rgb[:,:,-1]],axis=1)
    bg=np.median(border,axis=1)
    saturated=(border[...,1]>=180)&(border[...,0]<=100)&(border[...,2]<=100)&(
        border[...,1]-np.maximum(border[...,0],border[...,2])>=100)
    flat=np.abs(border-bg[:,None,:]).max(axis=(1,2))<=35
    stable=np.abs(bg-bg[0]).max(axis=1)<=24
    good=saturated.all(axis=1)&flat&stable
    bad=np.flatnonzero(~good)
    return {'method':'all_frame_saturated_green_border_v1','passed':bool(len(frames)==240 and good.all()),
        'frames':len(frames),'failed_frame_count':len(bad),'failed_frames':bad.tolist(),
        'background_rgb_min':bg.min(axis=0).tolist(),'background_rgb_max':bg.max(axis=0).tolist(),
        'expected_frames':240,'expected_background':'#00FF00','white_matte_fallback':False}


def source_green_background(raw):
    # H3 may include a few extra encoder tail frames. Match the existing
    # converter's first ten seconds, then inspect every one of its 240 frames.
    data=subprocess.check_output(['ffmpeg','-v','error','-i',str(raw),'-t','10','-an',
        '-vf','fps=24,scale=64:36:flags=area','-f','rawvideo','-pix_fmt','rgb24','-'])
    frame_size=64*36*3
    if not data or len(data)%frame_size:raise ValueError('Incomplete source background scan')
    return green_background_frames(np.frombuffer(data,np.uint8).reshape(-1,36,64,3))


def tick(client, state, submit=True, skip_actions=()):
    pid = state['project_id']
    for a in state['actions']:
        if a['id'] in skip_actions or a['status'] != 'generating':
            continue
        attempt = a['attempts'][-1]
        if not attempt.get('task_id'):
            known = set(attempt['previous_task_ids'])
            found = [t for t in client.generation.list_generation_tasks(project_id=pid, canvas_node_id=a['node_id']).items if t.id not in known]
            if len(found) != 1:
                raise RuntimeError(f"{a['id']} uncertain submission; do not resubmit")
            attempt['task_id'] = found[0].id; save(state)
        task = client.generation.get_generation_task(task_id=attempt['task_id'])
        attempt.update({'status': task.status, 'provider_task_id': task.provider_task_id,
                        'result_asset_id': task.result_asset_id, 'error': task.error_message})
        save(state)
        if task.status == 'completed':
            prepare_result(client, state, a, attempt)
        elif task.status in {'failed', 'cancelled'}:
            a['status'] = 'generation_failed'; save(state)
    uncertain = [a for a in state['actions'] if a['status']=='generation_failed' and a['attempts']
                 and a['attempts'][-1].get('provider_task_id')
                 and 'ConnectError' in (a['attempts'][-1].get('error') or '')]
    if uncertain:
        state['stage']='blocked_task_reconciliation'
        state['blocker']={'reason':'Provider accepted tasks but FPL polling failed with ConnectError. Remote outcomes unknown; no new submissions until reconciled.',
                          'actions':[a['id'] for a in uncertain], 'updated_at':now()}
        save(state)
        return
    if not submit:
        return
    if state.get('production_hold'):
        raise RuntimeError('Production is held for a recorded quality problem; resolve the hold before new paid submissions')
    if state.get('stage')=='blocked_task_reconciliation':
        raise RuntimeError('Reconcile remote task outcomes and explicitly resume before submitting new work')
    live = client.generation.list_generation_tasks(project_id=pid, page_size=100).items
    active = sum(t.status in ACTIVE for t in live)
    unsettled = [a for a in state['actions'] if a['id'] not in skip_actions and not a['reused'] and a['status'] not in {'approved', 'exhausted'}]
    if not unsettled:
        return
    priority = {aid:i for i,aid in enumerate(state.get('priority_ids',[]))}
    candidates = sorted([a for a in unsettled if a['status'] == 'planned'],
                        key=lambda a:(a['batch'],priority.get(a['id'],len(priority)+a['queue_order'])))
    for a in candidates:
        if active >= state['limits'].get('concurrent_tasks',2) or not can_submit(state, a):
            break
        prompt = (PACK / a['prompt_file']).read_text()
        if a['attempts']:
            prompt += '\nAdditional correction: ' + a['repair_instruction'] + '\n'
        canvas = client.visual.get_canvas(project_id=pid)
        previous = client.generation.list_generation_tasks(project_id=pid, canvas_node_id=a['node_id']).items
        model_id = a.get('next_model_id', state['model_id'])
        model = next(m for m in client.generation.generation_options().models if m.id == model_id)
        if model.slug in state['excluded_models']:
            raise ValueError('Excluded model cannot be used')
        caps = model.video_capabilities
        if not (caps and 'reference' in caps.supported_modes and caps.reference_limits.get('image', 0) >= 1
                and caps.supports_prompt and caps.duration_min <= 10 <= caps.duration_max
                and '16:9' in caps.resolution_ratios.get('768p', [])):
            raise ValueError('Selected model cannot satisfy the approved video specification')
        attempt = {'started_at': now(), 'status': 'submission_started', 'model_id': model_id, 'model_slug': model.slug,
                   'reference_asset_id':state['reference_asset_id'],'reference_sha256':state['reference_sha256'],
                   'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(), 'previous_task_ids': [t.id for t in previous]}
        a['attempts'].append(attempt); a['status'] = 'generating'; save(state)
        snapshot = PACK / 'prompts/library' / (a['id'] + '-attempt-' + str(len(a['attempts'])) + '.txt')
        snapshot.write_text(prompt); attempt['prompt_file'] = str(snapshot.relative_to(PACK)); save(state)
        task = client.generation.create_generation_task(project_id=pid, body={'kind': 'video',
            'model_id': model_id, 'mode': 'reference', 'prompt': prompt,
            'duration': 10, 'ratio': '16:9', 'resolution': '768p', 'reference_asset_ids': [state['reference_asset_id']],
            'canvas_node_id': a['node_id'], 'expected_canvas_revision': canvas.revision})
        attempt.update({'task_id': task.id, 'status': task.status}); save(state); active += 1
        print(json.dumps({'submitted': a['id'], 'name': a['name'], 'task': task.id, 'calls': calls(state)}, ensure_ascii=False), flush=True)


def review(state, action_id, verdict, reason):
    a = next(a for a in state['actions'] if a['id'] == action_id)
    assert a['status'] in {'awaiting_review', 'generation_failed'}
    attempt = a['attempts'][-1]
    attempt['review'] = {'verdict': verdict, 'reason': reason, 'reviewed_at': now()}
    if verdict == 'pass':
        assert attempt.get('candidate_file') and not attempt.get('processing_error')
        if attempt.get('source_background') is not None:
            assert attempt['source_background']['passed'], 'Source background failed the all-frame green gate'
        source = PACK / attempt['candidate_file']; target = PACK / 'pet/kurisu-animation' / (a['name'] + '.webm')
        shutil.copy2(source, target); shutil.copy2(source.with_suffix('.report.json'), target.with_suffix('.report.json'))
        a.update({'status': 'approved', 'file': str(target.relative_to(PACK)), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
        write_alpha_contact(a,attempt,target)
        poster = PACK / 'previews/library' / (a['id'] + '.png'); poster.parent.mkdir(exist_ok=True)
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-c:v', 'libvpx-vp9', '-i', str(target), '-frames:v', '1', str(poster)], check=True)
        a['poster'] = str(poster.relative_to(PACK))
    else:
        a['status'] = 'rejected' if can_submit(state,a) else 'exhausted'
    save(state)


def withdraw(state, action_id, reason):
    a = next(a for a in state['actions'] if a['id'] == action_id)
    assert a['status'] == 'approved' and not a.get('reused')
    record = {k:a.get(k) for k in ['file','sha256','poster','delivery_asset_id','delivery_node_id']}
    record.update({'withdrawn_at':now(),'reason':reason,'review':a['attempts'][-1].get('review')})
    a.setdefault('withdrawn_approvals',[]).append(record)
    a['attempts'][-1]['review']={'verdict':'withdrawn','reason':reason,'reviewed_at':now()}
    a['status'] = 'rejected' if can_submit(state,a) else 'exhausted'
    save(state)
    old=PACK/record['file']
    archive=PACK/'source/library/withdrawn'/a['id']/record['sha256'][:16]
    archive.mkdir(parents=True,exist_ok=True)
    for path in [old,old.with_suffix('.report.json')]:
        if path.exists():shutil.move(str(path),archive/path.name)
    record['archive_file']=str((archive/old.name).relative_to(PACK))
    for k in ['file','sha256','poster','delivery_asset_id','delivery_node_id','delivery_upload_started']:
        a.pop(k,None)
    save(state)


def retry(state, action_id, instruction):
    a = next(a for a in state['actions'] if a['id'] == action_id)
    assert a['status'] in {'rejected', 'generation_failed', 'exhausted'} and can_submit(state, a)
    a['repair_instruction'] = instruction; a['status'] = 'planned'; save(state)


def recover(client, state):
    """Resume polling the same paid task; this never appends an attempt."""
    unresolved=[]
    for aid in state.get('blocker',{}).get('actions',[]):
        a=next(a for a in state['actions'] if a['id']==aid)
        attempt=a['attempts'][-1]
        task=client.generation.get_generation_task(task_id=attempt['task_id'])
        if task.status=='failed' and task.can_retry_materialization:
            task=client.generation.retry_materialization(task_id=task.id)
            attempt.setdefault('recoveries',[]).append({'at':now(),'task_id':task.id,
                'provider_task_id':task.provider_task_id,'kind':'resume_original_task'})
        attempt.update(status=task.status,error=task.error_message,result_asset_id=task.result_asset_id)
        if task.status in ACTIVE or task.status=='completed':
            assert task.id==attempt['task_id'] and task.provider_task_id==attempt['provider_task_id']
            a['status']='generating'
        elif 'ConnectError' in (task.error_message or ''):
            unresolved.append(aid)
        else:
            a['status']='generation_failed'
        save(state)
    if not unresolved:
        state.setdefault('resolved_blockers',[]).append(state.pop('blocker',{}))
        state['stage']='producing';save(state)
    else:
        raise RuntimeError('Original-task recovery is not available yet; no new generation submitted')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'setup', 'tick', 'watch', 'status', 'recover', 'review', 'withdraw', 'retry'])
    parser.add_argument('--action'); parser.add_argument('--verdict', choices=['pass', 'reject'])
    parser.add_argument('--reason')
    parser.add_argument('--no-submit', action='store_true', help='Only recover/poll existing tasks')
    parser.add_argument('--skip-action',action='append',default=[],help='Leave another operator action untouched; its calls and active tasks still count toward every global limit')
    parser.add_argument('--model-id', help='Optional alternate model for one authorized retry')
    args = parser.parse_args()
    if args.command == 'status':
        print(json.dumps(status(load()), ensure_ascii=False)); return
    with production_lock():
        execute(args)


def execute(args):
    if args.command == 'init':
        initialize(); return
    state = load()
    if args.command == 'review':
        assert args.action and args.verdict and args.reason
        review(state, args.action, args.verdict, args.reason)
    elif args.command == 'withdraw':
        assert args.action and args.reason
        withdraw(state,args.action,args.reason)
    elif args.command == 'retry':
        assert args.action and args.reason
        if args.model_id:
            action = next(a for a in state['actions'] if a['id'] == args.action)
            action['next_model_id'] = args.model_id
        retry(state, args.action, args.reason)
    else:
        from future_props_lab.desktop import desktop_client
        from future_props_lab.cli import capability
        with desktop_client() as client:
            caps = capability(client)
            required = ['visual.get_canvas', 'visual.put_canvas', 'visual.apply_canvas_operations',
                        'generation.create_generation_task', 'generation.list_generation_tasks',
                        'generation.get_generation_task', 'files.download_file', 'files.upload_file']
            assert all(x in caps['operations'] for x in required)
            if args.command == 'setup':
                assert not state.get('canvas_setup_complete'); setup(client, state)
            elif args.command == 'recover':
                assert 'generation.retry_materialization' in caps['operations']
                recover(client,state)
            else:
                assert state.get('canvas_setup_complete')
                while True:
                    tick(client, state, submit=not args.no_submit,skip_actions=args.skip_action)
                    if (args.command != 'watch' or any(a['id'] not in args.skip_action and a['status'] in {'awaiting_review','generation_failed'} for a in state['actions'])
                            or not any(a['id'] not in args.skip_action and a['status']=='generating' for a in state['actions'])):
                        break
                    time.sleep(30)
    print(json.dumps(status(state), ensure_ascii=False))


if __name__ == '__main__':
    main()
