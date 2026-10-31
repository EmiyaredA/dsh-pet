#!/usr/bin/env python3
"""Finite first-pass-only production, detached from chat lifetime.

Only root-authorized a037..a091, at most55 creates /132 total. Recovery uses
original IDs and blue source-only workers. No repair, keying or approval.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,os,re,time
from pathlib import Path
from uuid import uuid4
from future_props_lab.desktop import desktop_client
import kurisu_library as lib
import kurisu_queue as queue
from kurisu_quotas import ensure_quota
from kurisu_submission_errors import safe_submission_error

CAMPAIGN='human-breadth-first-remaining-2026-10-31'
IDS=tuple(f'a{i:03d}' for i in range(37,92))
MODEL='e4940af9-574e-4696-ae71-7527cfb0e30d'
REFERENCE='19637694-92f8-4109-b08a-20a52d6850b6'
REF_SHA='5bd754ab2df7c59fff6ebde7158781b3be8ce6670b1c48f16957dc6e05dc71c1'
REF_FILE='references/kurisu-front-80-transparent.png'
RUN_DIR=lib.ROOT/'temp/kurisu/first-pass-campaign-2026-10-31'
LOG=RUN_DIR/'controller.log'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def guard(state):
    c=state.get('first_pass_campaign',{})
    if not (c.get('id')==CAMPAIGN and c.get('approved') is True and c.get('owner_agent')=='/root/production_queue'
            and tuple(c.get('action_ids',[]))==IDS and c.get('max_new_paid_calls')==55
            and c.get('calls_at_authorization')==77 and c.get('calls_ceiling')==132
            and c.get('model_id')==MODEL and c.get('reference_asset_id')==REFERENCE and c.get('reference_sha256')==REF_SHA
            and c.get('first_generation_only') is True and c.get('source_recovery_only') is True
            and c.get('semantic_processing_authorized') is False):
        raise PermissionError('Finite first-pass campaign authorization is missing, changed or revoked')
    actions={a['id']:a for a in state['actions']}
    for aid in IDS:
        a=actions[aid]
        if len(a['attempts'])>1 or a.get('reused_origin_history') or a.get('reused'):
            raise PermissionError('Campaign cannot adopt an existing or corrective action: '+aid)
        for t in a['attempts']:
            if (t.get('model_id')!=MODEL or t.get('reference_asset_id')!=REFERENCE
                    or t.get('reference_sha256')!=REF_SHA or t.get('chroma_background')!='blue'):
                raise PermissionError('Existing campaign task conditions changed: '+aid)
    if lib.calls(state)>132:raise PermissionError('Campaign overall132 ceiling exceeded')
    return c

def remaining(state):
    guard(state)
    return [a for aid in IDS for a in state['actions'] if a['id']==aid and not a['attempts'] and a['status']=='planned']

def prompt_text(action):
    # Same approved six-section human/fabric80%/blue recipe. Only the named
    # action/miniature prop text varies. No new reference/model/matte route.
    base=(lib.PACK/'prompts/library/a032-framing80-blue-probe-02.txt').read_text()
    prefix=base.split('00:00.000 to 00:02.000: hold the empty-handed reference front stance.')[0]
    title=action['name']
    direction=action['direction'].strip()
    direction=direction.replace('red-and-blue beads','dark-red-and-amber beads').replace('red, blue, yellow','red, amber, yellow')
    direction=direction.replace('No green beads or light effects.','The beads stay dark-red and amber under neutral light.')
    direction=direction.replace('No green faces.','All cube faces use the listed warm and neutral colors.')
    direction=direction.replace('No green lettuce.','The filling stays red and beige.')
    direction=direction.replace('No green strawberry leaves.','The berry has a plain red top.')
    direction=direction.replace('No green leaves or floating petals.','All petals stay attached to the twig.')
    direction=direction.replace('Do not draw green wrapping leaves.','The dumpling is already unwrapped.')
    direction=direction.replace('No green leaves and no leaf may leave the frame.','The small leaf pile remains inside the frame.')
    direction=direction.replace('No snowfall, green decorations or separate landscape.','Keep the small tray isolated on the digital matte.')
    direction=direction.replace('No green tree or flashing lights.','The miniature tree stays ivory with steady red ornaments.')
    direction=direction.replace('with no green garnish','with plain beige garnish')
    direction=re.sub(r'\bwhite\b','ivory',direction,flags=re.I)
    direction=re.sub(r'\bblue\b','amber',direction,flags=re.I)
    if action['id']=='a053':
        prefix=prefix.replace('Her rear silhouette consists solely of long hair and skirt.',
            'Her rear silhouette consists solely of long hair and skirt.\n<Subject 2> is one tiny calm gray kitten, separate from the human girl, sitting beside her feet.')
        prefix=prefix.replace('examining a test tube','gently interacting with <Subject 2>')
        prefix=prefix.replace('<Picture 1> ([Shot 1] composition):', '<Subject 2> ([Shot 1]): fully_preserved - one small gray kitten stays separate from her human body.\n<Picture 1> ([Shot 1] composition):')
        prefix=prefix.replace('Only the named human gesture and miniature prop move.','Only the named human gesture and tiny separate companion move.')
        direction=direction.replace('cat','kitten')
    else:
        # A descriptive existing direction, not a new semantic action invention.
        prefix=prefix.replace('examining a test tube','performing her named miniature action')
    return (prefix+'00:00.000 to 00:02.000: hold the empty-handed reference front stance. '
        '00:02.000 to 00:07.000: '+direction+' '+
        ('00:07.000 to 00:09.000: lower her hands and let the separate kitten completely leave the image. ' if action['id']=='a053' else '00:07.000 to 00:09.000: lower hands and stow each named prop smoothly. ')+
        '00:09.000 to 00:10.000: hold the same empty-handed reference front stance.\n\n'
        'overall_soundscape:\nSilence.\n\nnon_diegetic_music:\nN/A.\n')

def emit(event,**values):
    RUN_DIR.mkdir(parents=True,exist_ok=True)
    item={'at':lib.now(),'event':event,**values}
    with LOG.open('a') as f:f.write(json.dumps(item,ensure_ascii=False)+'\n')
    print(json.dumps(item,ensure_ascii=False),flush=True)


SEASONAL_HANDOFF='quality/collaboration/seasonal-prompts/handoff.json'

def seasonal_prompt(aid):
    if not 'a069'<=aid<='a089':return None
    path=lib.PACK/SEASONAL_HANDOFF
    if not path.is_file():return None
    data=json.loads(path.read_text())
    entries=next((data[k] for k in ['actions','entries','prompts','items'] if k in data),[])
    if isinstance(entries,dict):entries=[{'action_id':k,**v} for k,v in entries.items() if isinstance(v,dict)]
    item=next((v for v in entries if v.get('action_id',v.get('id',v.get('stable_id')))==aid),None)
    if not item:return None
    filename=item.get('prompt_file',item.get('file'))
    expected='prompts/library/'+aid+'-firstpass-seasonal-v1.txt'
    digest=item.get('sha256',item.get('prompt_sha256',item.get('prompt_file_sha256')))
    if filename!=expected or not isinstance(digest,str) or not re.fullmatch(r'[0-9a-f]{64}',digest):
        raise PermissionError('Seasonal handoff does not bind the assigned immutable prompt '+aid)
    target=lib.PACK/filename
    if not target.is_file():return None
    if sha(target)!=digest:raise PermissionError('Seasonal handoff SHA mismatch '+aid)
    return {'file':filename,'sha256':digest,'handoff_file':SEASONAL_HANDOFF,'handoff_sha256':sha(path)}

def fields_for(aid,wave):
    return {'next_generation_mode':'reference','next_model_id':MODEL,'next_reference_asset_id':REFERENCE,
        'next_reference_sha256':REF_SHA,'next_reference_file':REF_FILE,
        'next_prompt_file':f'prompts/library/{aid}-framing80-blue-firstpass-{wave:02d}.txt',
        'next_chroma_background':'blue'}

def activate_next_wave(client):
    s=lib.load();c=guard(s);old=s.get('authorized_paid_pilot',{})
    if old.get('approved') and not old.get('closed'):
        if not (old.get('first_pass_only') and old.get('source_recovery_only') and set(old.get('action_ids',[]))<=set(IDS)):
            raise PermissionError('Another active scope owns paid submission')
        if any(not next(a for a in s['actions'] if a['id']==aid)['attempts'] for aid in old['action_ids']):return old
        with lib.production_lock():
            fresh=lib.load();live=fresh.get('authorized_paid_pilot',{})
            if live.get('id')!=old['id']:raise RuntimeError('Pilot changed during close CAS')
            live.update(closed=True,closed_at=lib.now(),close_reason='all_first_attempts_submitted');lib.save(fresh)
        s=lib.load();c=guard(s);old=s['authorized_paid_pilot']
    todo=[a for a in remaining(s) if not 'a069'<=a['id']<='a089' or seasonal_prompt(a['id']) is not None][:6]
    if not todo:return None
    known=[int(x['id'].rsplit('-',1)[-1]) for x in c.get('waves',[]) if re.fullmatch(r'h3-framing80-blue-firstpass-\d+',x.get('id',''))]
    wave=max([3,*known])+1
    identity=f'h3-framing80-blue-firstpass-{wave:02d}'
    folder=lib.ROOT/'temp/kurisu'/identity;folder.mkdir(parents=True,exist_ok=True)
    model=next((m for m in client.generation.generation_options().models if m.id==MODEL),None)
    if model is None:raise PermissionError('Primary H3 model is unavailable')
    plans=[]
    for a in todo:
        fields=fields_for(a['id'],wave);season=seasonal_prompt(a['id'])
        if season:
            fields['next_prompt_file']=season['file'];path=lib.PACK/season['file'];text=path.read_text()
        else:
            path=lib.PACK/fields['next_prompt_file'];text=prompt_text(a)
            if path.exists():
                if path.read_text()!=text:raise RuntimeError('Immutable prompt conflict: '+str(path))
            else:
                with path.open('x') as f:f.write(text)
        plan=queue.generation_plan(s,{**copy.deepcopy(a),**fields},model)
        plans.append({'action_id':a['id'],'name':a['name'],'node_id':a['node_id'],
            'expected_action_fingerprint':fingerprint(a),'expected_attempt_count':0,
            'proposed_action_fields':fields,'prompt_sha256':sha(path),'generation_metadata':plan['metadata'],
            'request_without_canvas':plan['payload'],'seasonal_handoff':season})
    ceiling=lib.calls(s)+len(todo)
    if ceiling>132:raise PermissionError('Finite campaign cannot extend beyond132 overall calls')
    manifest={'id':identity,'campaign_id':CAMPAIGN,'created_at':lib.now(),'action_ids':[a['id'] for a in todo],
        'calls_before':lib.calls(s),'calls_ceiling':ceiling,'max_new_paid_calls':len(todo),'first_generation_only':True,
        'reference_asset_id':REFERENCE,'reference_sha256':REF_SHA,'chroma_background':'blue','source_recovery_only':True,
        'semantic_processing_authorized':False,'actions':plans,'scope_authority':'library.first_pass_campaign finite55',
        'skill':'h3-prompt-writing/references/ref-en.txt six English sections','no_old_repair_or_approval':True}
    manifest_path=folder/'manifest.json';serialized=json.dumps(manifest,ensure_ascii=False,indent=2)+'\n'
    if manifest_path.exists():
        previous=json.loads(manifest_path.read_text())
        if previous['action_ids']!=manifest['action_ids'] or previous['actions']!=manifest['actions']:
            raise RuntimeError('Existing wave manifest is different; reconcile rather than overwrite')
        manifest=previous
    else:
        with manifest_path.open('x') as f:f.write(serialized)
    with lib.production_lock():
        fresh=lib.load();guard(fresh);prior=fresh.get('authorized_paid_pilot',{})
        if prior.get('id')!=old.get('id') or prior.get('approved') and not prior.get('closed'):
            raise RuntimeError('Pilot changed before activation CAS')
        for p in plans:
            a=next(a for a in fresh['actions'] if a['id']==p['action_id'])
            if a['attempts'] or a['status']!='planned' or fingerprint(a)!=p['expected_action_fingerprint']:
                raise RuntimeError('Action changed before first-pass activation CAS')
            if p.get('seasonal_handoff') and seasonal_prompt(p['action_id'])!=p['seasonal_handoff']:
                raise RuntimeError('Seasonal handoff changed before activation')
            if sha(lib.PACK/p['proposed_action_fields']['next_prompt_file'])!=p['prompt_sha256']:
                raise RuntimeError('Prompt changed before activation')
        if ceiling>lib.effective_limits(fresh)['total_calls']:
            ensure_quota(fresh,request_id=identity+'-finite-total-room',
                reason='Explicit finite first-pass campaign needs remaining original actions; totalonly up to132, no repair/model extensions',
                calls_needed=len(todo))
        if lib.effective_limits(fresh)['total_calls']>132:raise PermissionError('Unexpected total extension beyond campaign ceiling')
        fresh.setdefault('paid_pilot_history',[]).append(copy.deepcopy(prior))
        pilot={'id':identity,'approved':True,'closed':False,'approved_at':lib.now(),
            'authorization_basis':CAMPAIGN,'action_ids':manifest['action_ids'],'model_ids':[MODEL],
            'calls_ceiling':ceiling,'max_new_paid_calls':len(todo),'max_per_action_this_scope':1,
            'first_pass_only':True,'source_recovery_only':True,'semantic_processing_authorized':False}
        for p in plans:next(a for a in fresh['actions'] if a['id']==p['action_id']).update(p['proposed_action_fields'])
        fresh['authorized_paid_pilot']=pilot
        fresh['stage']='first_pass_coverage_priority_new_actions'
        fresh['first_pass_campaign'].setdefault('waves',[]).append({'id':identity,'manifest':str(manifest_path.relative_to(lib.ROOT)),
            'manifest_sha256':sha(manifest_path),'action_ids':manifest['action_ids'],'activated_at':lib.now()})
        lib.save(fresh)
    emit('wave_activated',wave=identity,ids=manifest['action_ids'],ceiling=ceiling)
    return pilot

def claim_source():
    with lib.production_lock():
        s=lib.load();guard(s);queue.reclaim_dead_claims(s)
        busy=sum(bool(a['attempts'] and a['attempts'][-1].get('processing_claim')) for a in s['actions'])
        if busy>=2:return None
        for aid in IDS:
            a=next(a for a in s['actions'] if a['id']==aid)
            if len(a['attempts'])!=1 or a['status']!='awaiting_processing':continue
            t=a['attempts'][0]
            if not t.get('task_id') or not t.get('result_asset_id') or t.get('local_retry_after',0)>time.time():continue
            if t.get('chroma_background')!='blue':raise PermissionError('Nonblue source cannot enter this recovery scope')
            token=str(uuid4());t['processing_claim']={'token':token,'pid':os.getpid(),'started_at':lib.now(),'mode':'finite_campaign_blue_source_only'}
            a['status']='local_processing';lib.save(s);job=queue.snapshot(a);job['claim_token']=token;return job
    return None

def progress(s):
    actions=[a for a in s['actions'] if a['id'] in IDS]
    return {'calls':lib.calls(s),'campaign_submitted':sum(bool(a['attempts']) for a in actions),
        'campaign_sources':sum(bool(a['attempts'] and a['attempts'][0].get('source_file')) for a in actions),
        'campaign_inflight':sum(a['status'] in {'generating','submission_uncertain'} for a in actions),
        'campaign_source_failures':sum(a['status']=='processing_failed' for a in actions),
        'qualified_actions':sum(a['status']=='approved' for a in s['actions'])}

def run():
    RUN_DIR.mkdir(parents=True,exist_ok=True)
    with lib.production_lock():
        s=lib.load();guard(s);prior=s['first_pass_campaign'].get('controller',{})
        if prior.get('status')=='running' and type(prior.get('pid')) is int and prior['pid']>0 and prior['pid']!=os.getpid() and queue.alive(prior['pid']):
            raise PermissionError('Existing finite campaign controller owns this scope')
        s['first_pass_campaign']['controller']={'pid':os.getpid(),'status':'running','started_at':lib.now(),
            'script':'scripts/kurisu_first_pass_campaign.py','log':str(LOG.relative_to(lib.ROOT)),
            'max_model_concurrency':6,'max_local_processing':1,'source_only':True,'new_repair_allowed':False}
        lib.save(s)
    (RUN_DIR/'controller.pid').write_text(str(os.getpid())+'\n')
    runner=queue.QueueRunner(desktop_client);reason='interrupted';previous=None;failures=0
    emit('controller_started',pid=os.getpid(),scope=list(IDS),calls=lib.calls(lib.load()))
    try:
        while True:
            s=lib.load();c=guard(s)
            if c.get('stop_requested') or c.get('controller',{}).get('stop_requested'):reason='explicit_stop';break
            try:
                runner.reap()
                with desktop_client() as client:
                    queue.poll_originals(client,skip_actions={a['id'] for a in s['actions'] if a['id'] not in IDS})
                    s=lib.load()
                    if not queue.unresolved_submission(s) and not c.get('pause_new_submissions'):
                        for _ in range(6):
                            try:pilot=activate_next_wave(client)
                            except Exception as exc:
                                emit('submission_preflight_wait',error=safe_submission_error(exc));break
                            if pilot is None:break
                            s=lib.load();scope=set(pilot['action_ids'])
                            if lib.calls(s)>=132:break
                            before={a['id']:len(a['attempts']) for a in s['actions'] if a['id'] in scope}
                            if not queue.submit_one(client,skip_actions={a['id'] for a in s['actions'] if a['id'] not in scope}):break
                            fresh=lib.load();added=[a for a in fresh['actions'] if a['id'] in scope and len(a['attempts'])>before[a['id']]]
                            if len(added)!=1:raise RuntimeError('Unexpected paid reservation delta')
                            a=added[0];t=a['attempts'][0]
                            emit('first_task_submitted',action_id=a['id'],task_id=t.get('task_id'),calls=lib.calls(fresh),
                                wave=pilot['id'],prompt_sha256=t.get('prompt_sha256'),chroma=t.get('chroma_background'))
                            if not t.get('task_id') or t.get('submission_error') or fresh.get('submission_blocker'):
                                emit('submission_reconcile_only',action_id=a['id'],task_id=t.get('task_id'));break
                    elif queue.unresolved_submission(s):emit('submission_reconcile_only',blocker=s.get('submission_blocker'))
                # Refill model slots first; one raw decoder leaves another slot for nativeQA.
                while len(runner.futures)<1:
                    job=claim_source()
                    if not job:break
                    runner.futures[job['claim_token']]=(job,runner.executor.submit(runner.process,job))
                s=lib.load();p=progress(s)
                with lib.production_lock():
                    fresh=lib.load();control=fresh.get('first_pass_campaign',{}).get('controller',{})
                    if control.get('pid')==os.getpid():control.update(last_check_at=lib.now(),progress=p);lib.save(fresh)
                if p!=previous:emit('progress',**p);previous=p
                all_terminal=all(a['attempts'] and (a['attempts'][0].get('source_file') or a['status']=='generation_failed') for a in s['actions'] if a['id'] in IDS)
                if p['campaign_submitted']==55 and all_terminal and not runner.futures:
                    reason='finite_first_pass_source_coverage_complete_not106_approval';break
                failures=0
            except Exception as exc:
                failures+=1
                emit('recoverable_cycle_error',error=safe_submission_error(exc),attempt=failures,
                    new_calls_not_retried_blindly=True)
                if isinstance(exc,PermissionError) and 'unavailable' not in str(exc):
                    reason='authorization_or_scope_blocked';break
            time.sleep(min(60,20 if not failures else 5*2**min(failures-1,4)))
    finally:
        runner.close()
        for _ in range(20):
            try:
                with lib.production_lock():
                    s=lib.load();control=s.get('first_pass_campaign',{}).get('controller',{})
                    if control.get('pid')==os.getpid():control.update(status='stopped',finished_at=lib.now(),stop_reason=reason,progress=progress(s));lib.save(s)
                break
            except RuntimeError:time.sleep(.2)
        emit('controller_stopped',reason=reason,**progress(lib.load()))

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');args=p.parse_args()
    if args.run:run()
    else:
        s=lib.load();guard(s);print(json.dumps({'mode':'dry_run','campaign':CAMPAIGN,'ids':IDS,'remaining':len(remaining(s)),
            'progress':progress(s),'no_model_calls':True},ensure_ascii=False))
if __name__=='__main__':main()
