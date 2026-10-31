#!/usr/bin/env python3
"""Six paid-model slots and two detached local workers, with short ledger CAS.

Downloads/transcodes/network polling never hold library.lock. Reservations count
before submission; an unknown submission is reconciled, never created again.
"""
from __future__ import annotations
import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
from uuid import uuid4
import kurisu_library as lib
from kurisu_source_qa import load_source_review,ALLOW
from kurisu_submission_errors import safe_submission_error
from kurisu_motion_reuse import assert_motion_source_reusable
from kurisu_iteration_policy import submission_priority,require_local_repair,iteration_decision
from kurisu_spec_revisions import attempt_is_current

PROTECTED={'chroma_background','task_id','provider_task_id','model_id','model_slug','started_at','prompt_file','prompt_sha256','previous_task_ids','status','reference_asset_id','reference_sha256',
    'generation_mode','first_frame_asset_id','last_frame_asset_id','first_frame_sha256','last_frame_sha256','duration','ratio','resolution','prompt_source_file','prompt_source_sha256',
    'driver_asset_id','driver_sha256','driver_review_file','driver_review_sha256','driver_source_file','expected_action','workflow_parameters',
    'expected_output','raw_duration_controlled_by_request','processing_profile','strategy','request_file','request_sha256','normalized_prompt_sha256','canvas_node_id',
    'reference_file','reference_override','reference_byte_verification',
    'reference_asset_ids','reference_asset_sha256s','spec_revision_id','spec_action_name',
    'human_retry_grant_id','human_retry_exempt_from_normal_correction','human_retry_baseline_attempt_count','human_retry_spec_fingerprint',
    'human_campaign_id','human_campaign_attempt_number','human_campaign_baseline_attempt_count','human_campaign_spec_fingerprint'}
LOCAL_READY={'awaiting_processing','awaiting_source_review'}
FRAMES_MODEL_ID='5a785fa2-385f-45a0-a62b-d955b6dd72af'
FRAMES_MODEL_SLUG='minimax_h3_lightx2v'
WAN_MODEL_ID='b217e3cd-884d-4015-a3fa-98ab7608a67e'
WAN_MODEL_SLUG='wan2.2animate-v4-motion_retargeting'
DUAL_REFERENCE_MODEL_ID='418c676d-1a59-4b3e-a716-b99de8038c71'
DUAL_REFERENCE_MODEL_SLUG='minimax_h3_zm_u24'


def wan_generation_plan(state,action,model):
    """One reviewed motion driver conditions Wan; none of H3's text controls apply."""
    cap=model.video_capabilities
    if not (model.slug==WAN_MODEL_SLUG and action.get('next_generation_mode','reference')=='reference'
            and model.slug not in state['excluded_models'] and cap and 'reference' in (cap.supported_modes or [])
            and not cap.supports_prompt and not cap.supports_duration and not cap.supports_ratio
            and cap.supports_seed and '832x464' in cap.resolutions
            and cap.reference_limits.get('image',0)>=1 and cap.reference_limits.get('video',0)>=1
            and cap.reference_video_upload_configured):
        raise ValueError('Selected Wan model cannot satisfy the approved motion-only reference workflow')
    parameters=action.get('next_workflow_parameters')
    if (not isinstance(parameters,dict) or set(parameters)!={'seed'} or type(parameters['seed']) is not int
            or not cap.seed_minimum<=parameters['seed']<=cap.seed_maximum):
        raise ValueError('Wan requires one explicit fixed seed and no other workflow parameters')
    driver=action.get('next_video_asset_id');driver_sha=action.get('next_driver_sha256')
    if not isinstance(driver,str) or not driver.strip() or driver!=driver.strip() or driver==state['reference_asset_id']:
        raise ValueError('Wan requires one formal motion driver video asset')
    if not isinstance(driver_sha,str) or not re.fullmatch(r'[0-9a-f]{64}',driver_sha):
        raise ValueError('Wan requires the verified motion driver SHA256')
    filename=action.get('next_driver_review_file')
    if not isinstance(filename,str) or not filename or Path(filename).is_absolute():
        raise ValueError('Wan requires a motion-only driver review inside the pet pack')
    review_path=(lib.PACK/filename).resolve()
    if not review_path.is_relative_to(lib.PACK.resolve()):
        raise ValueError('Motion-only driver review must remain inside the pet pack')
    review_bytes=review_path.read_bytes();review=json.loads(review_bytes)
    if not isinstance(review,dict) or not isinstance(review.get('composition'),dict):
        raise ValueError('Motion driver review must include a typed composition record')
    composition=review['composition']
    if (review.get('action_id')!=action['id'] or review.get('driver_asset_id')!=driver
            or review.get('driver_sha256')!=driver_sha or review.get('motion_clearance')!='allow_motion_transfer_only'
            or review.get('final_media_approved') is not False
            or not isinstance(review.get('expected_action'),str) or not review['expected_action'].strip()
            or not review.get('reviewer') or not review.get('reviewed_at')
            or review.get('visual_review_performed') is not True or review.get('automated_metrics_only') is not False
            or composition.get('reference_sha256')!=state['reference_sha256']
            or composition.get('matched_to_reference') is not True or composition.get('first_last_same') is not True):
        raise ValueError('Driver review does not clear this exact action, source and reference composition for motion transfer only')
    seconds=review.get('source_duration_seconds')
    if isinstance(seconds,bool) or not isinstance(seconds,(float,int)) or not math.isfinite(seconds) or not seconds>=10:
        raise ValueError('Motion driver must contain at least ten seconds; short clips cannot be looped')
    source_file=review.get('source_file')
    if not isinstance(source_file,str) or not source_file or Path(source_file).is_absolute():
        raise ValueError('Motion review must identify its verified local video')
    source=(lib.PACK/source_file).resolve()
    if not source.is_relative_to(lib.PACK.resolve()) or hashlib.sha256(source.read_bytes()).hexdigest()!=driver_sha:
        raise ValueError('Motion driver bytes changed or escaped the pet pack')
    assert_motion_source_reusable(state,lib.PACK,driver_sha,driver)
    payload={'kind':'video','model_id':model.id,'mode':'reference','resolution':'832x464',
        'reference_asset_ids':[state['reference_asset_id']],'video_asset_ids':[driver],'audio_asset_ids':[],
        'workflow_parameters':copy.deepcopy(parameters)}
    metadata={'generation_mode':'reference','strategy':'wan_motion_reference_v1','resolution':'832x464',
        'reference_asset_id':state['reference_asset_id'],'reference_sha256':state['reference_sha256'],
        'driver_asset_id':driver,'driver_sha256':driver_sha,'driver_source_file':source_file,
        'driver_review_file':filename,'driver_review_sha256':hashlib.sha256(review_bytes).hexdigest(),
        'expected_action':review['expected_action'],'workflow_parameters':copy.deepcopy(parameters),
        'raw_duration_controlled_by_request':False,'processing_profile':'wan_normal_green_key_no_palette',
        'expected_output':{'duration_seconds':10,'fps':24,'frames':240,'width':640,'height':360,
            'codec':'vp9','alpha':True,'audio_streams':0,'short_source_policy':'reject_no_repeat_or_time_stretch'}}
    return {'payload':payload,'metadata':metadata,'text':None}


def preflight_canvas_inputs(canvas,node_id,payload):
    nodes=[n.model_dump(mode='json',exclude_none=True) if hasattr(n,'model_dump') else n for n in canvas.nodes]
    node=next((n for n in nodes if n['id']==node_id),None)
    if node is None or node.get('kind')!='video':
        raise ValueError('Target video canvas node does not exist')
    inputs=[payload.get('first_frame_asset_id'),payload.get('last_frame_asset_id'),
            *payload.get('reference_asset_ids',[]),*payload.get('video_asset_ids',[]),*payload.get('audio_asset_ids',[])]
    if node.get('asset_id') and node['asset_id'] in inputs:
        raise ValueError('self_asset_reference: target node owns an input asset; use a separate production source variant')


def prepare_wan_variant(client,action_id,variant_tag):
    """Create a new production node without clearing a previous node's history."""
    if not re.fullmatch(r'wan-[a-z0-9-]{3,35}',variant_tag):
        raise ValueError('A stable Wan source variant tag is required')
    state=lib.load();action=next(a for a in state['actions'] if a['id']==action_id)
    if action['status'] in {'generating','submission_uncertain','local_processing'}:
        raise ValueError('Resolve the existing action task before changing its production node')
    model=next(m for m in client.generation.generation_options().models if m.id==WAN_MODEL_ID)
    plan=generation_plan(state,action,model)
    if plan['metadata']['strategy']!='wan_motion_reference_v1':raise ValueError('Variant requires a verified Wan production plan')
    node_id='kurisu-'+action_id+'-'+variant_tag
    canvas=client.visual.get_canvas(project_id=state['project_id'])
    nodes=[n.model_dump(mode='json',exclude_none=True) if hasattr(n,'model_dump') else copy.deepcopy(n) for n in canvas.nodes]
    existing=next((n for n in nodes if n['id']==node_id),None)
    if existing:
        preflight_canvas_inputs(canvas,node_id,plan['payload'])
    else:
        draft={key:copy.deepcopy(value) for key,value in plan['payload'].items() if key!='kind'}
        nodes.append({'id':node_id,'kind':'video','title':action['name']+' · '+variant_tag,
                      'position':{'x':int(action_id[1:])*16,'y':9500},'generation_draft':draft})
        try:
            client.visual.put_canvas(project_id=state['project_id'],body={'expected_revision':canvas.revision,'nodes':nodes,
                'edges':[e.model_dump(mode='json',exclude_none=True) if hasattr(e,'model_dump') else copy.deepcopy(e) for e in canvas.edges],
                'categories':[c.model_dump(mode='json',exclude_none=True) if hasattr(c,'model_dump') else copy.deepcopy(c) for c in canvas.categories]})
        except Exception:
            current=client.visual.get_canvas(project_id=state['project_id'])
            preflight_canvas_inputs(current,node_id,plan['payload'])
    with lib.production_lock():
        fresh=lib.load();live=next(a for a in fresh['actions'] if a['id']==action_id)
        if live['node_id']==node_id:return node_id
        if live['node_id']!=action['node_id'] or live['status']!=action['status'] or generation_plan(fresh,live,model)!=plan:
            raise RuntimeError('Action or motion inputs changed while preparing its new source variant')
        live.setdefault('node_history',[]).append({'at':lib.now(),'previous_node_id':live['node_id'],'new_node_id':node_id,
            'reason':'Wan motion input is an output of the old node; use a separate DAG production source, preserving all prior assets/history',
            'model_id':WAN_MODEL_ID,'input_payload_sha256':hashlib.sha256(json.dumps(plan['payload'],sort_keys=True).encode()).hexdigest()})
        live['node_id']=node_id;lib.save(fresh)
    return node_id


def generation_plan(state,action,model):
    """Validate all inputs before reserving a paid attempt. No SDK writes."""
    chroma=action.get('next_chroma_background','green')
    if not isinstance(chroma,str) or chroma not in {'green','blue'}:
        raise ValueError('next_chroma_background must be green or explicitly blue')
    mode=action.get('next_generation_mode','reference');cap=model.video_capabilities
    if mode not in {'reference','frames'}:
        raise ValueError('Only reference or the explicitly approved frames workflow is supported')
    if model.id!=action.get('next_model_id',state['model_id']):
        raise ValueError('Selected model changed during preflight')
    if model.id==WAN_MODEL_ID:
        plan=wan_generation_plan(state,action,model)
        plan['metadata']['chroma_background']=chroma
        if action.get('spec_revision_id'):plan['metadata'].update(spec_revision_id=action['spec_revision_id'],spec_action_name=action['name'])
        return plan
    if model.slug in state['excluded_models'] or not(cap and mode in (cap.supported_modes or []) and cap.supports_prompt
            and cap.duration_min<=10<=cap.duration_max and '16:9' in (cap.resolution_ratios or {}).get('768p',[])):
        raise ValueError('Selected model cannot satisfy the approved '+mode+' workflow')
    payload={'kind':'video','model_id':model.id,'mode':mode,'duration':10,'ratio':'16:9','resolution':'768p'}
    metadata={'generation_mode':mode,'duration':10,'ratio':'16:9','resolution':'768p','chroma_background':chroma}
    if action.get('spec_revision_id'):metadata.update(spec_revision_id=action['spec_revision_id'],spec_action_name=action['name'])
    if mode=='reference':
        if (cap.reference_limits or {}).get('image',0)<1:
            raise ValueError('Selected reference workflow does not support image references')
        dual='next_reference_asset_ids' in action
        reference_ids=action.get('next_reference_asset_ids') if dual else None
        if dual:
            if (model.id!=DUAL_REFERENCE_MODEL_ID or model.slug!=DUAL_REFERENCE_MODEL_SLUG
                    or (cap.reference_limits or {}).get('image',0)<2
                    or (getattr(cap,'reference_minimums',{}) or {}).get('image',0)>2):
                raise ValueError('Dual identical reference anchors require the approved U24 reference workflow')
            if (not isinstance(reference_ids,list) or len(reference_ids)!=2
                    or not all(isinstance(x,str) and x and x==x.strip() for x in reference_ids)
                    or len(set(reference_ids))!=2):
                raise ValueError('Dual anchors require exactly two distinct formal image asset IDs')
            if action.get('next_reference_asset_id') not in (None,reference_ids[0]):
                raise ValueError('Single and dual reference overrides conflict')
            if not action.get('next_prompt_file'):
                raise ValueError('Dual anchors require an immutable authored two-picture H3 prompt')
        reference,reference_sha=state['reference_asset_id'],state['reference_sha256']
        override=dual or any(action.get(key) is not None for key in ('next_reference_asset_id','next_reference_sha256','next_reference_file'))
        if override:
            reference=reference_ids[0] if dual else action.get('next_reference_asset_id');reference_sha=action.get('next_reference_sha256')
            filename=action.get('next_reference_file')
            if not isinstance(reference,str) or not reference.strip() or reference!=reference.strip():
                raise ValueError('Reference override requires a formal image asset ID')
            if not isinstance(reference_sha,str) or not re.fullmatch(r'[0-9a-f]{64}',reference_sha):
                raise ValueError('Reference override requires its exact SHA256')
            if not isinstance(filename,str) or not filename or Path(filename).is_absolute():
                raise ValueError('Reference override requires its local image inside the pet pack')
            source=(lib.PACK/filename).resolve()
            if not source.is_relative_to(lib.PACK.resolve()) or hashlib.sha256(source.read_bytes()).hexdigest()!=reference_sha:
                raise ValueError('Reference override image bytes changed or escaped the pet pack')
            metadata.update(reference_file=filename,reference_byte_verification='official_download_and_local_sha256_match')
        prompt_file=action.get('next_prompt_file')
        if prompt_file is not None:
            if not isinstance(prompt_file,str) or not prompt_file or Path(prompt_file).is_absolute():
                raise ValueError('Explicit H3 reference prompt must be inside the pet pack')
            source=(lib.PACK/prompt_file).resolve()
            if not source.is_relative_to(lib.PACK.resolve()):raise ValueError('Explicit H3 prompt escaped the pet pack')
            text=source.read_text()
            fields=['subject_definitions:','summary:','retention_analysis:','detailed_description:','overall_soundscape:','non_diegetic_music:']
            positions=[text.find(field) for field in fields]
            if any(p<0 for p in positions) or positions!=sorted(positions):
                raise ValueError('Explicit reference prompt must follow all six H3 Ref2VA sections')
            if len(text)>getattr(cap,'max_prompt_length',20000):raise ValueError('Explicit H3 prompt exceeds model length capability')
            metadata.update(prompt_source_file=prompt_file,prompt_source_sha256=hashlib.sha256(text.encode()).hexdigest())
        else:
            text=lib.prompt_for(action,action.get('compact_direction',action['direction']),True)
        if dual and '<Picture 2>' not in text:
            raise ValueError('Dual-anchor authored prompt must explicitly define Picture 2')
        payload['reference_asset_ids']=list(reference_ids) if dual else [reference]
        metadata.update(reference_asset_id=reference,reference_sha256=reference_sha,reference_override=override,strategy='compact_positive_ref2va_v2')
        if dual:
            metadata.update(reference_asset_ids=list(reference_ids),
                reference_asset_sha256s=[reference_sha,reference_sha],strategy='u24_dual_identical_reference_v1')
    else:
        if model.id!=FRAMES_MODEL_ID or model.slug!=FRAMES_MODEL_SLUG:
            raise ValueError('This frames model has not been approved for the internal workflow')
        if getattr(cap,'frames_require_adaptive_ratio',False):
            raise ValueError('Selected frames workflow requires adaptive ratio rather than the approved 16:9')
        first,last=(action.get(key) for key in ('next_first_frame_asset_id','next_last_frame_asset_id'))
        if not all(isinstance(x,str) and x.strip() and x==x.strip() for x in (first,last)) or first==last:
            raise ValueError('Frames requires two distinct formal first/last frame asset IDs')
        filename=action.get('next_prompt_file')
        if not isinstance(filename,str) or not filename.strip() or Path(filename).is_absolute():
            raise ValueError('Frames requires an authored FL2VA prompt file inside the pet pack')
        source=(lib.PACK/filename).resolve()
        if not source.is_relative_to(lib.PACK.resolve()):
            raise ValueError('Frames prompt must remain inside the pet pack')
        text=source.read_text()
        fields=['integrated_multimodal_description:','overall_soundscape:','non_diegetic_music:']
        positions=[text.find(field) for field in fields]
        if (not text.startswith('How the reference pictures align with the target video')
                or '0.00-second mark' not in text.split('\n',1)[0] or '10.00-second mark' not in text.split('\n',1)[0]
                or any(p<0 for p in positions) or positions!=sorted(positions)):
            raise ValueError('Frames prompt must follow the H3 base-en FL2VA alignment and three-field structure')
        payload.update(first_frame_asset_id=first,last_frame_asset_id=last)
        metadata.update(first_frame_asset_id=first,last_frame_asset_id=last,strategy='h3_fl2va_first_last_v1',
            prompt_source_file=filename,prompt_source_sha256=hashlib.sha256(text.encode()).hexdigest())
        for field in ('first_frame_sha256','last_frame_sha256'):
            if action.get('next_'+field):metadata[field]=action['next_'+field]
    if chroma=='blue' and (not action.get('next_prompt_file') or not re.search(r'RGB\s*\(\s*0\s*,\s*0\s*,\s*255\s*\)|#0000FF',text,re.I)):
        raise ValueError('Explicit blue requires an immutable authored blue-matte prompt')
    payload['prompt']=text
    return {'payload':payload,'metadata':metadata,'text':text}


def transient_local(exc):
    status=getattr(exc,'status',None) or getattr(getattr(exc,'response',None),'status_code',None)
    return (isinstance(exc,(OSError,TimeoutError,ConnectionError))
        or type(exc).__name__ in {'ConnectError','ReadTimeout','WriteTimeout','ConnectTimeout','PoolTimeout','ReadError','WriteError','RemoteProtocolError'}
        or status in {408,429} or isinstance(status,int) and status>=500)


def alive(pid):
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False
    except PermissionError:return True


def action_at(state,aid,index,task_id):
    a=next((a for a in state['actions'] if a['id']==aid),None)
    if not a or len(a['attempts'])!=index or a['attempts'][-1].get('task_id')!=task_id:return None
    return a


def snapshot(a):
    return {'action':copy.deepcopy(a),'attempt':copy.deepcopy(a['attempts'][-1]),'attempt_index':len(a['attempts'])}


def all_tasks(client,project_id,node_id=None):
    page=1;items=[]
    while True:
        args={'project_id':project_id,'page':page,'page_size':100}
        if node_id is not None:args['canvas_node_id']=node_id
        response=client.generation.list_generation_tasks(**args);items.extend(response.items)
        if len(items)>=getattr(response,'total',len(items)) or not response.items:return items
        page+=1


def model_slots(state,remote=()):
    names={t.id for t in remote if t.status in lib.ACTIVE}
    for a in state['actions']:
        if a['status'] not in {'generating','submission_uncertain'} or not a['attempts']:continue
        t=a['attempts'][-1]
        if t.get('status')=='completed':continue
        names.add(t.get('task_id') or 'reservation:'+t.get('reservation_token',a['id']))
    for t in state.get('diagnostic_attempts',[]):
        if t.get('status') in lib.ACTIVE|{'submission_started','submission_uncertain'}:
            names.add(t.get('task_id') or 'diagnostic-reservation:'+t['reservation_token'])
    return len(names)


def unresolved_submission(state):
    return (any(a['attempts'] and a['status'] in {'generating','submission_uncertain'} and not a['attempts'][-1].get('task_id')
                for a in state['actions'])
            or any(t.get('status') in {'submission_started','submission_uncertain'} and not t.get('task_id')
                   for t in state.get('diagnostic_attempts',[])))


def paid_allowed(state,action):
    if state.get('stage') in {'blocked_task_reconciliation','blocked_style_validation'} or state.get('submission_blocker'):return False
    if not state.get('production_hold'):return True
    # A hold can only be bypassed by an explicit, bounded ledger authorization.
    pilot=state.get('authorized_paid_pilot',{})
    return bool(pilot.get('approved') and not pilot.get('halted') and not pilot.get('closed') and action['id'] in pilot.get('action_ids',[])
        and lib.calls(state)<pilot.get('calls_ceiling',0))


def ranked(state):
    order={aid:i for i,aid in enumerate(state.get('priority_ids',[]))}
    return sorted((a for a in state['actions'] if a['status']=='planned' and not a.get('reused')),
        key=lambda a:(submission_priority(state,a),order.get(a['id'],len(order)),a.get('batch',99),a.get('queue_order',999)))


def note_defect(state,a,t,kind):
    """Keep hard failures; a new human breadth policy may continue other first passes."""
    cohort=t.get('release_epoch','legacy');t.setdefault('hard_source_defects',[])
    if kind not in t['hard_source_defects']:t['hard_source_defects'].append(kind)
    family=kind if kind in {'background','foreground_lighting'} else None
    if not family:return
    families=t.setdefault('hard_stop_families',[])
    if family not in families:families.append(family)
    failed=[x['id'] for x in state['actions'] if x.get('batch')==a.get('batch') and x['attempts']
        and x['attempts'][-1].get('release_epoch','legacy')==cohort and family in x['attempts'][-1].get('hard_stop_families',[])]
    if len(set(failed))>=2:
        policy=state.get('iteration_policy',{});pilot=state.get('authorized_paid_pilot',{})
        continue_others=bool(isinstance(policy,dict)
            and policy.get('continue_other_actions_after_failure') is True
            and policy.get('id') and policy.get('source')
            and type(policy.get('max_corrective_rounds_per_action')) is int
            and policy['max_corrective_rounds_per_action']==1
            and pilot.get('approved') is True and (pilot.get('first_pass_only') is True
                or (pilot.get('supplemental_retry_once') is True
                    and state.get('supplemental_retry_authorizations',{}).get(pilot.get('grant_id'),{}).get('active') is True))
            and pilot.get('source_recovery_only') is True
            and type(pilot.get('calls_ceiling')) is int
            and pilot['calls_ceiling']>=0 and pilot.get('max_per_action_this_scope')==1
            and pilot.get('release_unbounded_or_old_repairs') is False)
        event={'reason':'Two '+family+' source defects in the same production batch; source review required before new paid calls',
            'defect_family':family,'action_ids':sorted(set(failed)),'batch':a.get('batch'),'release_epoch':cohort,'since':lib.now(),'calls_at_hold':lib.calls(state),'new_calls_allowed':False}
        event['automatic_quality_halt_suppressed']=continue_others
        if continue_others:
            event.update(reason='Repeated '+family+' source defects retained; explicit human policy continues other bounded first-pass/source-only actions',
                iteration_policy_id=policy['id'],new_calls_allowed=any(x['id'] not in failed and x.get('status')=='planned'
                    and not x.get('attempts') and paid_allowed(state,x) and lib.can_submit(state,x) for x in state['actions']))
        history=state.setdefault('quality_stop_events',[])
        if not history or any(history[-1].get(k)!=event.get(k) for k in ['defect_family','action_ids','batch','release_epoch','automatic_quality_halt_suppressed','iteration_policy_id']):history.append(event)
        if continue_others:return
        if not state.get('production_hold'):state['production_hold']=event
        if state.get('authorized_paid_pilot',{}).get('id')==cohort:state['authorized_paid_pilot']['halted']=True


def commit_poll(aid,index,expected_task,remote=None,error_type=None):
    with lib.production_lock():
        state=lib.load();a=action_at(state,aid,index,expected_task)
        if not a or a['status'] not in {'generating','submission_uncertain','generation_failed'}:return False
        t=a['attempts'][-1]
        if error_type:
            n=t.get('poll_failures',0)+1;t.update(poll_failures=n,last_poll_error_type=error_type,next_poll_at=time.time()+min(60,5*2**min(n-1,4)))
        else:
            t.update(task_id=remote.id,status=remote.status,provider_task_id=remote.provider_task_id,
                result_asset_id=remote.result_asset_id,error=remote.error_message,next_poll_at=0,poll_failures=0)
            if remote.status=='completed' and remote.result_asset_id:a['status']='awaiting_processing'
            elif remote.status in {'failed','cancelled'}:a['status']='generation_failed'
            else:a['status']='generating'
            if state.get('submission_blocker',{}).get('action_id')==aid:state.pop('submission_blocker',None)
        lib.save(state);return True


def matches_reservation(remote,t):
    payload=getattr(remote,'request_payload',None)
    mode=t.get('generation_mode','reference')
    wan=t.get('strategy')=='wan_motion_reference_v1'
    if (mode=='frames' or wan or t.get('reference_asset_id')) and not payload:return False
    if payload is not None:
        text=(payload.get('prompt') or '').strip()
        if hashlib.sha256(text.encode()).hexdigest()!=t.get('normalized_prompt_sha256'):return False
        if payload.get('model_id')!=t.get('model_id'):return False
        if payload.get('mode','reference')!=mode:return False
        if mode=='reference' and t.get('reference_asset_id') and payload.get('reference_asset_ids')!=t.get('reference_asset_ids',[t['reference_asset_id']]):return False
        if t.get('canvas_node_id') and (getattr(remote,'canvas_node_id',None) or payload.get('canvas_node_id'))!=t['canvas_node_id']:return False
        if mode=='frames' and (payload.get('first_frame_asset_id')!=t.get('first_frame_asset_id')
                or payload.get('last_frame_asset_id')!=t.get('last_frame_asset_id') or payload.get('reference_asset_ids')):return False
        if wan and (text or payload.get('reference_asset_ids')!=[t['reference_asset_id']]
                or payload.get('video_asset_ids')!=[t['driver_asset_id']]
                or payload.get('workflow_parameters')!=t['workflow_parameters'] or payload.get('audio_asset_ids')
                or payload.get('resolution')!='832x464'):return False
    created=getattr(remote,'created_at',None)
    if created:
        if datetime.fromisoformat(created.replace('Z','+00:00')).timestamp()+2<datetime.fromisoformat(t['started_at']).timestamp():return False
    return True


def poll_originals(client,skip_actions=()):
    current=lib.load();jobs=[]
    for a in current['actions']:
        if a['id'] in skip_actions or not a['attempts']:continue
        t=a['attempts'][-1]
        recoverable=a['status']=='generation_failed' and t.get('provider_task_id') and any(x in (t.get('error') or '') for x in ['ConnectError','Timeout','轮询'])
        if a['status'] in {'generating','submission_uncertain'} or recoverable:jobs.append(snapshot(a))
    for job in jobs:
        a,t,index=job['action'],job['attempt'],job['attempt_index']
        if t.get('next_poll_at',0)>time.time():continue
        old=t.get('task_id')
        try:
            if not old:
                known=set(t.get('previous_task_ids',[]));found=[r for r in all_tasks(client,current['project_id'],a['node_id']) if r.id not in known and matches_reservation(r,t)]
                if not found:
                    found=[r for r in all_tasks(client,current['project_id']) if r.id not in known and matches_reservation(r,t)]
                if len(found)!=1:
                    with lib.production_lock():
                        s=lib.load();live=action_at(s,a['id'],index,None)
                        if live:
                            live['status']='submission_uncertain';s['submission_blocker']={'action_id':a['id'],'reason':'Original submission outcome ambiguous; query/reconcile only, never resubmit','at':lib.now()};lib.save(s)
                    continue
                remote=found[0]
            else:remote=client.generation.get_generation_task(task_id=old)
            if remote.status=='failed' and getattr(remote,'can_retry_materialization',False):
                remote=client.generation.retry_materialization(task_id=remote.id)
                if old and remote.id!=old:raise ValueError('Recovery changed the original task ID')
            commit_poll(a['id'],index,old,remote)
        except Exception as exc:
            commit_poll(a['id'],index,old,error_type=type(exc).__name__)


def submit_one(client,skip_actions=()):
    state=lib.load()
    if state.get('next_submission_preflight_at',0)>time.time():return False
    candidates=[a for a in ranked(state) if a['id'] not in skip_actions and paid_allowed(state,a) and lib.can_submit(state,a)]
    if not candidates:return False
    # The unresolved reservation itself serializes all canvas-create operations.
    if unresolved_submission(state):return False
    candidate=candidates[0]
    preflight_retry=iteration_decision(state,candidate,'submit')
    if not preflight_retry['allowed']:return False
    remote=all_tasks(client,state['project_id'])
    if model_slots(state,remote)>=min(6,state['limits'].get('concurrent_tasks',6)):return False
    previous=all_tasks(client,state['project_id'],candidate['node_id'])
    model_id=candidate.get('next_model_id',state['model_id'])
    model=next((m for m in client.generation.generation_options().models if m.id==model_id),None)
    if model is None:raise ValueError('Selected generation model is unavailable')
    plan=generation_plan(state,candidate,model)
    if plan['payload']['mode']=='frames':
        images={asset.id for asset in client.files.list_files(project_id=state['project_id'],media_kind='image').items if asset.media_kind=='image'}
        if not {plan['payload']['first_frame_asset_id'],plan['payload']['last_frame_asset_id']}<=images:
            raise ValueError('Both frames must be formal image assets in the existing project')
    if plan['metadata']['strategy']=='wan_motion_reference_v1':
        assets={asset.id:asset for asset in client.files.list_files(project_id=state['project_id']).items}
        for aid,kind in [(state['reference_asset_id'],'image'),(plan['metadata']['driver_asset_id'],'video')]:
            if aid not in assets or assets[aid].media_kind!=kind:
                raise ValueError('Wan inputs must be one formal project image and one video asset')
    if plan['metadata'].get('reference_override'):
        references=plan['metadata'].get('reference_asset_ids',[plan['metadata']['reference_asset_id']])
        images={asset.id:asset for asset in client.files.list_files(project_id=state['project_id'],media_kind='image').items if asset.media_kind=='image'}
        if not set(references)<=images.keys():raise ValueError('Reference override is not a formal image asset in this project')
        for reference in references:
            actual=hashlib.sha256()
            with client.files.download_file(asset_id=reference) as data:
                for chunk in data.iter_bytes():actual.update(chunk)
            if actual.hexdigest()!=plan['metadata']['reference_sha256']:
                raise ValueError('Official image bytes do not match the local reference override SHA256')
    # A read-only canvas failure is preflight, not an unknown paid submission.
    canvas=client.visual.get_canvas(project_id=state['project_id'])
    preflight_canvas_inputs(canvas,candidate['node_id'],plan['payload'])
    with lib.production_lock():
        state=lib.load();a=next(a for a in state['actions'] if a['id']==candidate['id'])
        if a['status']!='planned' or not paid_allowed(state,a) or not lib.can_submit(state,a):return False
        if model_slots(state,remote)>=min(6,state['limits'].get('concurrent_tasks',6)):return False
        if unresolved_submission(state):return False
        if generation_plan(state,a,model)!=plan:
            raise RuntimeError('Generation inputs changed during preflight; no attempt reserved')
        text=plan['text'];normalized_text=text or ''
        t={'started_at':lib.now(),'status':'submission_started','reservation_token':str(uuid4()),'submission_pid':os.getpid(),
            'model_id':model_id,'model_slug':model.slug,**plan['metadata'],
            'canvas_node_id':a['node_id'],
            'normalized_prompt_sha256':hashlib.sha256(normalized_text.strip().encode()).hexdigest(),
            'previous_task_ids':[r.id for r in previous],
            'release_epoch':(state.get('authorized_paid_pilot',{}).get('id','legacy') if state.get('production_hold') else state.get('production_release',{}).get('id','legacy'))}
        retry=iteration_decision(state,a,'submit')
        if not retry['allowed']:return False
        if retry.get('retry_metadata',{})!=preflight_retry.get('retry_metadata',{}):return False
        if retry.get('retry_authorization_sha256')!=preflight_retry.get('retry_authorization_sha256'):return False
        t.update(retry.get('retry_metadata',{}))
        a['attempts'].append(t);a['status']='generating';index=len(a['attempts'])
        state['submission_preflight_failures']=0;state['next_submission_preflight_at']=0
        if text is None:
            path=lib.PACK/'quality/generation-requests'/(a['id']+'-attempt-'+str(index)+'.json');path.parent.mkdir(parents=True,exist_ok=True)
            request_text=json.dumps({**plan['payload'],'canvas_node_id':a['node_id'],'expected_canvas_revision':canvas.revision},sort_keys=True,ensure_ascii=False,indent=2)+'\n'
            with path.open('x') as f:f.write(request_text)
            t['request_file']=str(path.relative_to(lib.PACK));t['request_sha256']=hashlib.sha256(request_text.encode()).hexdigest()
        else:
            path=lib.PACK/'prompts/library'/(a['id']+'-attempt-'+str(index)+'.txt');path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('x') as f:f.write(text)
            t['prompt_file']=str(path.relative_to(lib.PACK));t['prompt_sha256']=hashlib.sha256(text.encode()).hexdigest()
        lib.save(state)
        project=state['project_id'];node=a['node_id'];aid=a['id']
    # No ledger lock crosses network or generation submission. The reservation
    # remains visible and blocks a second producer until this CAS is committed.
    try:
        result=client.generation.create_generation_task(project_id=project,body={**plan['payload'],
            'canvas_node_id':node,'expected_canvas_revision':canvas.revision})
        commit_poll(aid,index,None,result)
    except Exception as exc:
        with lib.production_lock():
            s=lib.load();live=action_at(s,aid,index,None)
            if live:
                live['status']='submission_uncertain';live['attempts'][-1]['submission_error_type']=type(exc).__name__
                live['attempts'][-1]['submission_error']=safe_submission_error(exc)
                s['submission_blocker']={'action_id':aid,'reason':'Submission interrupted; reconcile original node before any additional paid call','at':lib.now()};lib.save(s)
        poll_originals(client)
    return True


def reclaim_dead_claims(state):
    changed=False
    for a in state['actions']:
        if not a['attempts']:continue
        t=a['attempts'][-1];claim=t.get('processing_claim')
        if claim and not alive(claim['pid']):
            t.setdefault('processing_claim_history',[]).append({**claim,'recovered_at':lib.now(),'reason':'Worker process exited; resume same paid result'})
            t.pop('processing_claim',None)
            if a['status']=='local_processing':a['status']='awaiting_processing'
            changed=True
    return changed


def local_ready(a):
    if a['status'] not in LOCAL_READY or not a['attempts']:return False
    t=a['attempts'][-1]
    if not attempt_is_current(a,t):return False
    if not t.get('task_id') or not t.get('result_asset_id') or t.get('local_retry_after',0)>time.time():return False
    if a['status']=='awaiting_source_review':
        report=lib.PACK/'quality/source-reviews'/(a['id']+'-attempt-'+str(len(a['attempts']))+'.json')
        if not report.is_file():return False
        stat=report.stat();fingerprint=f'{stat.st_mtime_ns}:{stat.st_size}'
        return fingerprint!=t.get('source_review_fingerprint')
    return True


def claim_local(skip_actions=()):
    with lib.production_lock():
        state=lib.load();changed=reclaim_dead_claims(state)
        if state.get('local_processing_hold'):
            if changed:lib.save(state)
            return None
        busy=sum(bool(a['attempts'] and a['attempts'][-1].get('processing_claim')) for a in state['actions'])
        if busy>=min(2,state['limits'].get('local_processing',2)):
            if changed:lib.save(state)
            return None
        candidates=[a for a in state['actions'] if a['id'] not in skip_actions and local_ready(a)]
        if not candidates:
            if changed:lib.save(state)
            return None
        a=sorted(candidates,key=lambda a:(a.get('batch',99),a.get('queue_order',999)))[0];t=a['attempts'][-1]
        token=str(uuid4());t['processing_claim']={'token':token,'pid':os.getpid(),'started_at':lib.now()};a['status']='local_processing';lib.save(state)
        job=snapshot(a);job['claim_token']=token;return job


def commit_processing(job,result):
    with lib.production_lock():
        s=lib.load();a=action_at(s,job['action']['id'],job['attempt_index'],job['attempt']['task_id'])
        if not a:return False
        t=a['attempts'][-1];claim=t.get('processing_claim',{})
        if claim.get('token')!=job['claim_token']:return False
        if a['status']!='local_processing':
            t.setdefault('processing_claim_history',[]).append({**claim,'finished_at':lib.now(),'discarded':'Action status changed during local work'})
            t.pop('processing_claim',None);lib.save(s);return False
        for key,expected in [('task_id',job['attempt']['task_id']),('attempt_index',job['attempt_index']),('claim_token',job['claim_token'])]:
            if key in result and result[key]!=expected:raise ValueError('Local worker response identity mismatch')
        patch=result.get('attempt_patch',{})
        if patch.get('candidate_file') and t.get('requested_worker_version') and patch.get('worker_version')!=t['requested_worker_version']:
            raise ValueError('Local worker recipe changed; stale candidate is not eligible')
        protected=PROTECTED&set(patch)
        if any(patch[key]!=t.get(key) for key in protected):raise ValueError('Media worker attempted to change immutable generation metadata')
        # A worker may echo the selected profile for its report; discard the
        # identical echo rather than letting it become an input mutation.
        patch={key:value for key,value in patch.items() if key not in protected}
        t.update(patch);t.setdefault('processing_claim_history',[]).append({**claim,'finished_at':lib.now()});t.pop('processing_claim',None)
        status=result.get('action_status','awaiting_review')
        if status not in {'awaiting_source_review','awaiting_review','processing_failed','awaiting_processing'}:raise ValueError('Invalid local worker result status')
        a['status']=status
        if result.get('hard_defect'):note_defect(s,a,t,result.get('defect_kind','source_quality'))
        lib.save(s);return True


def request_local(action_id,reason,worker_version=None):
    """Explicit same-source reprocessing, with independently cleared raw bytes.

    Old candidate metadata is archived and removed from approval eligibility.
    Reading/hashing source and writing the archive happen outside the ledger lock.
    """
    s=lib.load();a=next(a for a in s['actions'] if a['id']==action_id)
    require_local_repair(s,a)
    job=snapshot(a);t=job['attempt']
    if s.get('local_processing_hold'):raise RuntimeError('Local processing is explicitly held; no new calibration was authorized')
    assert a['status'] in {'awaiting_review','processing_failed','awaiting_source_review','awaiting_processing'}
    assert t.get('task_id') and t.get('result_asset_id') and not t.get('processing_claim')
    raw=lib.PACK/t['source_file'];digest=hashlib.sha256(raw.read_bytes()).hexdigest()
    if t.get('source_sha256') and t['source_sha256']!=digest:raise ValueError('Original source bytes changed; local reprocessing denied')
    review=load_source_review(lib.PACK,action_id,job['attempt_index'],digest)
    if review['processing_clearance']!=ALLOW:raise ValueError('Local reprocessing requires same-hash independent source ALLOW')
    old={k:t.get(k) for k in ['candidate_file','candidate_sha256','report','alpha_contact','processing_error','processing_method','worker_version']}
    history=lib.PACK/'quality/processing-history'/(action_id+'-attempt-'+str(job['attempt_index'])+'-'+str(uuid4())+'.json');history.parent.mkdir(parents=True,exist_ok=True)
    history.write_text(json.dumps({'task_id':t['task_id'],'source_sha256':digest,'processing_metadata':old,'new_model_calls':0},ensure_ascii=False,indent=2)+'\n')
    with lib.production_lock():
        fresh=lib.load();live=action_at(fresh,action_id,job['attempt_index'],t['task_id'])
        if not live or live['status']!=a['status']:raise RuntimeError('Local reprocess request became stale')
        require_local_repair(fresh,live)
        current=live['attempts'][-1]
        if current.get('processing_claim') or any(current.get(k)!=old[k] for k in ['candidate_file','candidate_sha256','processing_method','worker_version']):raise RuntimeError('Local candidate changed before reprocessing request')
        current.setdefault('local_reprocess_requests',[]).append({'at':lib.now(),'reason':reason,'history_file':str(history.relative_to(lib.PACK)),
            'requested_worker_version':worker_version,'source_sha256':digest,'new_model_calls':0})
        for key in old:current.pop(key,None)
        current.pop('local_retry_after',None);current['source_sha256']=digest;current['source_quality']=review
        if worker_version:current['requested_worker_version']=worker_version
        live['status']='awaiting_processing';lib.save(fresh)


def review_media(action_id,verdict,reason,motion_mode=None):
    """Prepare local approval artifacts outside the ledger lock; CAS last."""
    s=lib.load();a=next(a for a in s['actions'] if a['id']==action_id);job=snapshot(a);t=a['attempts'][-1]
    if not attempt_is_current(a,t):raise ValueError('Old specification candidate is not eligible for current final review')
    prepared=None
    if verdict=='pass':
        import shutil
        import subprocess
        source=lib.PACK/t['candidate_file'];folder=lib.ROOT/'temp/kurisu/review-transactions'/str(uuid4());folder.mkdir(parents=True)
        media=folder/source.name;report=folder/'media.report.json';poster=folder/'poster.png'
        shutil.copy2(source,media);shutil.copy2(source.with_suffix('.report.json'),report)
        contact_attempt=copy.deepcopy(t);lib.write_alpha_contact(a,contact_attempt,media)
        subprocess.run(['ffmpeg','-y','-v','error','-c:v','libvpx-vp9','-i',str(media),'-frames:v','1',str(poster)],check=True)
        prepared={'media':str(media),'report':str(report),'poster':str(poster),'sha256':hashlib.sha256(media.read_bytes()).hexdigest(),'alpha_contact':contact_attempt['alpha_contact']}
    with lib.production_lock():
        fresh=lib.load();live=action_at(fresh,action_id,job['attempt_index'],t.get('task_id'))
        if not live or live['status']!=job['action']['status']:raise RuntimeError('Review snapshot became stale; approval was not committed')
        if any(live['attempts'][-1].get(k)!=t.get(k) for k in ['candidate_file','candidate_sha256','processing_method','worker_version']):raise RuntimeError('Reviewed candidate changed; approval was not committed')
        lib.review(fresh,action_id,verdict,reason,motion_mode,prepared)


class QueueRunner:
    def __init__(self,client_factory,processor=None):
        self.client_factory=client_factory;self.processor=processor
        self.executor=ThreadPoolExecutor(max_workers=2);self.futures={}
    def process(self,job):
        try:
            if self.processor is None:
                from kurisu_green_worker import process_snapshot
                processor=process_snapshot
            else:processor=self.processor
            with self.client_factory() as client:
                return processor(client,job['action'],job['attempt'],job['attempt_index'],job['claim_token'])
        except Exception as exc:
            transient=transient_local(exc)
            n=job['attempt'].get('local_processing_failures',0)+1
            return {'attempt_patch':{'processing_error':'Local worker '+type(exc).__name__,'local_processing_failures':n,
                'local_retry_after':time.time()+min(60,5*2**min(n-1,4)) if transient else 0},
                'action_status':'awaiting_processing' if transient else 'processing_failed','hard_defect':False}
    def reap(self,wait=False):
        for token,(job,future) in list(self.futures.items()):
            if not wait and not future.done():continue
            result=future.result()
            try:commit_processing(job,result)
            except RuntimeError as exc:
                if 'Another production' in str(exc):continue
                raise
            self.futures.pop(token)  # A stale result is an orphan, never overwrites a newer attempt.
    def cycle(self,client,submit=True,skip_actions=()):
        try:return self._cycle(client,submit,skip_actions)
        except RuntimeError as exc:
            if 'Another production' not in str(exc):raise
            return lib.status(lib.load())
    def _cycle(self,client,submit=True,skip_actions=()):
        self.reap();poll_originals(client,skip_actions)
        # Paid slots refill BEFORE local workers start downloads or FFmpeg.
        if submit:
            try:
                for _ in range(6):
                    if not submit_one(client,skip_actions):break
            except Exception as exc:
                if not transient_local(exc):raise
                with lib.production_lock():
                    s=lib.load();n=s.get('submission_preflight_failures',0)+1
                    s.update(submission_preflight_failures=n,last_submission_preflight_error=type(exc).__name__,next_submission_preflight_at=time.time()+min(60,5*2**min(n-1,4)));lib.save(s)
        while len(self.futures)<2:
            job=claim_local(skip_actions)
            if not job:break
            self.futures[job['claim_token']]=(job,self.executor.submit(self.process,job))
        return lib.status(lib.load())
    def close(self):
        self.executor.shutdown(wait=True);deadline=time.monotonic()+60
        while self.futures:
            self.reap(wait=True)
            if not self.futures or time.monotonic()>=deadline:break
            time.sleep(.1)


def run(once=False,no_submit=False,interval=5,skip_actions=(),stop_when_idle=False):
    from future_props_lab.desktop import desktop_client
    runner=QueueRunner(desktop_client)
    try:
        with desktop_client() as client:
            while True:
                result=runner.cycle(client,submit=not no_submit,skip_actions=skip_actions)
                print(json.dumps(result,ensure_ascii=False),flush=True)
                if once:break
                state=lib.load();active=any(a['status']=='generating' for a in state['actions'])
                pending_local=not state.get('local_processing_hold') and any(local_ready(a) for a in state['actions'])
                if stop_when_idle and not active and not runner.futures and not pending_local:break
                time.sleep(max(1,min(60,interval)))
    finally:runner.close()
    return lib.status(lib.load())


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--once',action='store_true');p.add_argument('--no-submit',action='store_true');p.add_argument('--stop-when-idle',action='store_true');p.add_argument('--interval',type=int,default=5);p.add_argument('--skip-action',action='append',default=[])
    args=p.parse_args();run(args.once,args.no_submit,args.interval,args.skip_action,args.stop_when_idle)
