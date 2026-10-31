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
from kurisu_quotas import (effective_limits, attempt_limit, counts as quota_counts,
                           record_standing_authorization, extend_quota, ensure_quota)
from kurisu_background import evaluate_native_frames, scan_source_background
from kurisu_iteration_policy import submission_allowed,correction_usage
from kurisu_spec_revisions import has_source,current_spec_attempts,attempt_is_current,spec_iteration_decision

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / 'pet-packs/kurisu'
STATE = PACK / 'library.json'
ACTIVE = {'queued', 'submitting', 'pending', 'processing'}


def now():
    return datetime.now(timezone.utc).isoformat()


def save(state):
    state['updated_at'] = now()
    state['production_coverage']={
        'source_action_count':sum(bool(a.get('reused') or a.get('reused_origin_history')
            or any(t.get('source_file') for t in a.get('attempts',[]))) for a in state['actions']),
        'approved_count':sum(a.get('status')=='approved' for a in state['actions']),
        'active_generation_count':sum(a.get('status') in {'generating','submission_uncertain'} for a in state['actions']),
        'target':106}
    if any(a.get('spec_revision_id') for a in state['actions']):
        for action in state['actions']:
            if not action.get('spec_revision_id'):continue
            decision=spec_iteration_decision(action,correction_usage(action),'submit')
            action.setdefault('spec_revision',{}).update(current_paid_attempt_count=len(current_spec_attempts(action)),
                current_corrective_rounds_used=decision.get('current_spec_corrective_rounds'),
                historical_usage_integrity=decision.get('current_spec_corrective_rounds') is not None)
        historical=state['production_coverage']['source_action_count']
        current=sum(has_source(a,current=True) for a in state['actions'])
        state['production_coverage'].update(historical_source_action_count=historical,
            current_spec_source_action_count=current,superseded_only_source_action_count=historical-current,
            note='Historical raw files remain; superseded research sources do not complete the new programmer specifications.')
    temp = STATE.with_suffix('.next.json')
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
    temp.replace(STATE)
    if STATE == PACK / 'library.json':
        lines = ['# 红莉栖 106 条动作生产清单', '',
                 f"新调用：{calls(state)} / {state['limits']['total_calls']}。状态以 library.json 为准。", '',
                 '| ID | 分类 | 动作 | 批次 | 状态 | 调用 | 任务 |', '|---|---|---|---|---|---|---|']
        for a in state['actions']:
            tasks = '<br>'.join((t.get('task_id') or '提交待核对')+('（旧规格：'+t.get('spec_action_name',a['name'])+'）' if not attempt_is_current(a,t) else '') for t in a['attempts'])
            if not tasks:
                tasks = ('早期样片已撤回，见 production.json' if a.get('reused_origin_history') else
                         '复用早期样片' if a.get('reused') else '尚未调用')
            lines.append(f"| {a['id']} | {a['group']} | {a['name']} | {a.get('batch','—')} | {a['status']} | {len(a['attempts'])}"+('（当前规格'+str(len(current_spec_attempts(a)))+'）' if a.get('spec_revision_id') else '')+f" | {tasks} |")
        (PACK/'ACTIONS.md').write_text('\n'.join(lines)+'\n')


def load():
    return json.loads(STATE.read_text())


def calls(state):
    return quota_counts(state)['calls']


def can_submit(state, action):
    model = action.get('next_model_id', state.get('model_id'))
    limits, used = effective_limits(state), quota_counts(state)
    return (submission_allowed(state,action)
            and used['calls'] < limits['total_calls']
            and len(action['attempts']) < attempt_limit(state, action.get('id'))
            and (model == state.get('model_id') or used['other_model_calls'] < limits['other_model_calls'])
            and (not (action['attempts'] or action.get('reused_origin_history'))
                 or used['repairs'] < limits['repair_calls']))


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


from kurisu_short_prompts import prompt_for


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
            'quota_usage': quota_counts(state), 'effective_limits': effective_limits(state),
            'standing_authorization_id': state.get('standing_authorization',{}).get('id'),
            'diagnostic_attempt_count': len(state.get('diagnostic_attempts', [])),
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
        background = source_green_background(raw,attempt.get('chroma_background','green'))
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        attempt['processing_error'] = 'Green-background validation could not finish: ' + str(exc)
        action['status'] = 'awaiting_review'; save(state); return
    attempt['source_background'] = background
    if not background['passed']:
        attempt['processing_error'] = ('Source must use uniform saturated '+attempt.get('chroma_background','green')+' in every frame; '
            f"background failed on {background['failed_frame_count']} of {background['frames']} frames")
        action['status'] = 'awaiting_review'; save(state); return
    attempt.pop('processing_error', None)
    if attempt.get('chroma_background')=='blue':
        attempt['processing_error']='Blue source validated; dedicated eye-preserving blue matte must be reviewed before acceptance'
        action['status']='awaiting_review';save(state);return
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
    """Check the actual pixel boundary; semantic/foreground QA remains separate."""
    return evaluate_native_frames(frames)


def source_green_background(raw,color='green'):
    return scan_source_background(raw,color)


def tick(client, state=None, submit=True, skip_actions=()):
    """Poll/refill metadata only; local media work belongs to QueueRunner."""
    from kurisu_queue import poll_originals,submit_one
    poll_originals(client,skip_actions)
    if submit:
        for _ in range(6):
            if not submit_one(client,skip_actions):break
    fresh=load()
    if state is not None:
        state.clear();state.update(fresh)
    return status(fresh)


def review(state, action_id, verdict, reason, motion_mode=None, prepared=None):
    a = next(a for a in state['actions'] if a['id'] == action_id)
    if a.get('human_action_hold',{}).get('active') is True:
        raise PermissionError('Human deferred this action/version; do not replace or re-review it automatically')
    if a.get('spec_revision_id') and (not a['attempts'] or not attempt_is_current(a,a['attempts'][-1])):
        raise ValueError('Old specification media cannot satisfy the current specification review')
    allowed = {'awaiting_review', 'generation_failed', 'processing_failed'}
    if verdict == 'reject':
        allowed.add('awaiting_source_review')
    assert a['status'] in allowed
    attempt = a['attempts'][-1]
    attempt['review'] = {'verdict': verdict, 'reason': reason, 'reviewed_at': now()}
    if verdict == 'pass':
        assert attempt.get('candidate_file') and not attempt.get('processing_error')
        if attempt.get('source_background') is not None:
            assert attempt['source_background']['passed'], 'Source background failed the all-frame green gate'
        if attempt.get('processing_claim_history'):
            assert attempt.get('source_quality',{}).get('processing_clearance')=='allow_mild_color_and_green_key', 'Independent source clearance is required'
            assert attempt['source_quality'].get('source_sha256')==attempt.get('source_sha256'), 'Independent source clearance hash changed'
            media=attempt.get('report',{}).get('verification',{})
            assert (media.get('width'),media.get('height'),media.get('fps'),media.get('frames'),media.get('audio_streams'))==(640,360,24,240,0), 'Local media specification failed'
            assert media.get('all_frames_have_alpha') and media.get('background_clear'), 'Alpha/background verification is required'
        if motion_mode is not None:
            assert a['group']=='移动' and motion_mode in {'front-left-front','continuous-left-profile'}
            a['motion_mode']=motion_mode;attempt['review']['motion_mode']=motion_mode
        for key in ['quality_hold','automatic_playback_hold']:
            if key in a:a.setdefault('resolved_quality_holds',[]).append({'kind':key,**a.pop(key),'resolved_at':now(),'resolution':'Operator passed the reviewed replacement'})
        source = PACK / attempt['candidate_file']; target = PACK / 'pet/kurisu-animation' / (a['name'] + '.webm')
        poster = PACK / 'previews/library' / (a['id'] + '.png'); poster.parent.mkdir(exist_ok=True)
        if prepared:
            Path(prepared['media']).replace(target);Path(prepared['report']).replace(target.with_suffix('.report.json'))
            Path(prepared['poster']).replace(poster);attempt['alpha_contact']=prepared['alpha_contact'];digest=prepared['sha256']
        else:
            shutil.copy2(source,target);shutil.copy2(source.with_suffix('.report.json'),target.with_suffix('.report.json'))
            digest=hashlib.sha256(target.read_bytes()).hexdigest();write_alpha_contact(a,attempt,target)
            subprocess.run(['ffmpeg','-y','-v','error','-c:v','libvpx-vp9','-i',str(target),'-frames:v','1',str(poster)],check=True)
        a.update({'status':'approved','file':str(target.relative_to(PACK)),'sha256':digest,'poster':str(poster.relative_to(PACK))})
    else:
        a['status'] = 'rejected' if can_submit(state,a) else 'exhausted'
    save(state)


def withdraw(state, action_id, reason):
    a = next(a for a in state['actions'] if a['id'] == action_id)
    assert a['status'] == 'approved'
    assert a.get('attempts') or a.get('reused'), 'An approval must have a campaign attempt or a recorded reused origin'
    reused = bool(a.get('reused'))
    previous_review = a['attempts'][-1].get('review') if a['attempts'] else None
    record = {k:a.get(k) for k in ['file','sha256','poster','delivery_asset_id','delivery_node_id']}
    record.update({'withdrawn_at':now(),'reason':reason,'review':previous_review,'reused_origin':reused})
    a.setdefault('withdrawn_approvals',[]).append(record)
    if a['attempts']:
        a['attempts'][-1]['review']={'verdict':'withdrawn','reason':reason,'reviewed_at':now()}
    if reused:
        # The original sample calls remain in production.json, outside the
        # later106-action campaign. Do not invent an attempt to revoke reuse.
        a.setdefault('reused_origin_history',[]).append({**record,'origin_record':'production.json'})
        a['reused']=False
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
    assert a['status'] in {'rejected', 'generation_failed', 'exhausted', 'processing_failed'} and can_submit(state, a)
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
    parser.add_argument('command', choices=['init', 'setup', 'tick', 'watch', 'status', 'recover', 'process-local', 'review', 'withdraw', 'retry', 'quota-extend', 'quota-ensure'])
    parser.add_argument('--action'); parser.add_argument('--verdict', choices=['pass', 'reject'])
    parser.add_argument('--reason')
    parser.add_argument('--no-submit', action='store_true', help='Only recover/poll existing tasks')
    parser.add_argument('--skip-action',action='append',default=[],help='Leave another operator action untouched; its calls and active tasks still count toward every global limit')
    parser.add_argument('--model-id', help='Optional alternate model for one authorized retry')
    parser.add_argument('--interval',type=int,default=5)
    parser.add_argument('--stop-when-idle',action='store_true')
    parser.add_argument('--motion-mode',choices=['front-left-front','continuous-left-profile'])
    parser.add_argument('--worker-version')
    parser.add_argument('--request-id', help='Stable, replay-safe quota adjustment ID')
    parser.add_argument('--total-add', type=int, default=0)
    parser.add_argument('--repair-add', type=int, default=0)
    parser.add_argument('--other-model-add', type=int, default=0)
    parser.add_argument('--quota-action', action='append', default=[], help='Add/ensure one further attempt for this named action')
    parser.add_argument('--calls-needed', type=int, default=0)
    parser.add_argument('--repairs-needed', type=int, default=0)
    parser.add_argument('--other-model-calls-needed', type=int, default=0)
    args = parser.parse_args()
    if args.command == 'status':
        print(json.dumps(status(load()), ensure_ascii=False)); return
    if args.command=='review':
        from kurisu_queue import review_media
        assert args.action and args.verdict and args.reason
        review_media(args.action,args.verdict,args.reason,args.motion_mode);return
    if args.command=='process-local':
        from kurisu_queue import request_local
        assert args.action and args.reason
        request_local(args.action,args.reason,args.worker_version)
    if args.command in {'tick','watch','recover','process-local'}:
        # The queue owns short reservation/CAS locks. Downloads, FFmpeg and
        # per-task SDK waits run outside them, including while quality is held.
        from kurisu_queue import run
        skip=set(args.skip_action)
        if args.action:skip.update(a['id'] for a in load()['actions'] if a['id']!=args.action)
        result=run(once=args.command!='watch',no_submit=args.no_submit or args.command in {'recover','process-local'},
            interval=args.interval,skip_actions=skip,stop_when_idle=args.stop_when_idle)
        print(json.dumps(result,ensure_ascii=False));return
    with production_lock():
        execute(args)


def execute(args):
    if args.command == 'init':
        initialize(); return
    state = load()
    if args.command in {'quota-extend', 'quota-ensure'}:
        if args.command == 'quota-extend':
            event = extend_quota(state, request_id=args.request_id, reason=args.reason,
                total_calls=args.total_add, repair_calls=args.repair_add,
                action_ids=args.quota_action, other_model_calls=args.other_model_add)
        else:
            event = ensure_quota(state, request_id=args.request_id, reason=args.reason,
                calls_needed=args.calls_needed, repairs_needed=args.repairs_needed,
                action_ids=args.quota_action, other_model_calls_needed=args.other_model_calls_needed)
        save(state)
        print(json.dumps(event, ensure_ascii=False)); return
    if args.command == 'review':
        assert args.action and args.verdict and args.reason
        review(state, args.action, args.verdict, args.reason, motion_mode=args.motion_mode)
    elif args.command == 'withdraw':
        assert args.action and args.reason
        withdraw(state,args.action,args.reason)
    elif args.command == 'retry':
        assert args.action and args.reason
        if args.model_id:
            action = next(a for a in state['actions'] if a['id'] == args.action)
            action['next_model_id'] = args.model_id
        retry(state, args.action, args.reason)
    elif args.command=='setup':
        from future_props_lab.desktop import desktop_client
        with desktop_client() as client:
            assert not state.get('canvas_setup_complete');setup(client,state)
    else:
        raise ValueError('Pipeline commands must run through the short-lock queue')
    print(json.dumps(status(state),ensure_ascii=False))


if __name__ == '__main__':
    main()
