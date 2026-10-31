"""Current action specifications do not inherit old-source completion or budgets.

Historical attempts stay billable. A named revision baseline permits a new first
pass plus one shared correction, while the independent sample gate stays closed.
"""
import hashlib,json

def spec_fingerprint(action):
    """Bind the complete named prop specification, independent of file paths."""
    fields={k:action.get(k) for k in ('id','name','direction','props','spec_revision_id')}
    return hashlib.sha256(json.dumps(fields,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def direct_scope_decision(state,action,gate):
    """A later named human replacement has no inherited sample requirement.

    This route is restricted to the explicit twelve-ID second revision; the
    existing programmer sample gate cannot be relabelled to bypass its proofs.
    """
    revision=action.get('spec_revision_id')
    ids=['a032','a035','a036','a037','a038','a043','a044','a047','a049','a050','a055','a057']
    deny={'allowed':False,'reason':'Named twelve-spec direct human gate missing, changed or unreleased'}
    if revision!='steins-props-v3-2026-10-31' or gate.get('spec_revision_id')!=revision:return deny
    if gate.get('enabled') is not True or gate.get('batch_released') is not True:return deny
    if gate.get('action_ids')!=ids or gate.get('sample_action_ids') or gate.get('sample_decisions'):return deny
    proof=gate.get('user_approval',{})
    if not(proof.get('approved') is True and proof.get('source')=='user'
           and proof.get('spec_revision_id')==revision and isinstance(proof.get('user_quote'),str)
           and proof['user_quote'].strip() and not proof.get('revoked_at')):return deny
    byid={a['id']:a for a in state['actions']}
    fingerprints=gate.get('spec_fingerprints',{})
    if set(fingerprints)!=set(ids) or action['id'] not in ids:return deny
    if any(sum(a['id']==aid for a in state['actions'])!=1 for aid in ids):return deny
    if spec_fingerprint(action)!=fingerprints[action['id']]:return deny
    for aid in ids:
        row=byid.get(aid,{})
        if row.get('spec_revision_id')!=revision or fingerprints[aid]!=spec_fingerprint(row):return deny
    return {'allowed':True,'reason':'Explicit human named twelve-spec replacement released without a new human sample hold'}

def current_spec_attempts(action):
    revision=action.get('spec_revision_id')
    return [t for t in action.get('attempts',[]) if not revision or t.get('spec_revision_id')==revision]

def attempt_is_current(action,attempt):
    return not action.get('spec_revision_id') or attempt.get('spec_revision_id')==action['spec_revision_id']

def has_source(action,current=True):
    attempts=current_spec_attempts(action) if current else action.get('attempts',[])
    origins=(action.get('reused') or action.get('reused_origin_history')) if not(current and action.get('spec_revision_id')) else False
    return bool(origins or any(t.get('source_file') for t in attempts))

def spec_iteration_decision(action,usage,operation):
    revision=action.get('spec_revision_id')
    if not revision:return {'allowed':True,'reason':'No revised specification'}
    record=action.get('spec_revision',{})
    baseline=record.get('baseline_corrective_rounds_used');old_count=record.get('baseline_attempt_count')
    if (record.get('id')!=revision or type(baseline)is not int or baseline<0
            or type(old_count)is not int or old_count<0 or record.get('max_corrective_rounds')!=1):
        return {'allowed':False,'reason':'Malformed specification iteration baseline; reconcile without resetting history'}
    from kurisu_supplemental_retries import is_exempt_retry_attempt
    current=current_spec_attempts(action)
    paid=sum(attempt_is_current(action,t) and not is_exempt_retry_attempt(action,i,t) for i,t in enumerate(action.get('attempts',[]),1))
    old=[t for t in action.get('attempts',[]) if t.get('spec_revision_id')!=revision]
    if len(old)!=old_count or usage['corrective_rounds_used']<baseline+paid:
        return {'allowed':False,'reason':'Historical specification usage changed/decreased; reconcile before new work'}
    corrections=max(0,usage['corrective_rounds_used']-baseline-int(paid>0))
    result={'allowed':True,'reason':'New specification first pass plus at most one shared correction',
            'spec_revision_id':revision,'current_spec_paid_attempts':len(current),'current_spec_ordinary_paid_attempts':paid,
            'current_spec_corrective_rounds':corrections,'current_spec_first_pass':paid==0}
    if operation=='local_repair' and not paid:
        return {**result,'allowed':False,'reason':'New specification has no first source; old content cannot be locally reused as a new first pass'}
    if corrections>=1 or (operation=='submit' and paid>=2):
        return {**result,'allowed':False,'reason':'Current specification one shared corrective round consumed'}
    return result

def sample_batch_decision(state,action):
    revision=action.get('spec_revision_id')
    if not revision:return {'allowed':True,'reason':'No specification sample gate'}
    gate=state.get('spec_batch_gates',{}).get(revision,{})
    if gate.get('gate_type')=='direct_human_scope':
        return direct_scope_decision(state,action,gate)
    if not (gate.get('spec_revision_id')==revision and gate.get('enabled') is True
            and set(gate.get('sample_action_ids',[]))=={'a034','a052'}):
        return {'allowed':False,'reason':'Current specification requires its explicit sample batch gate'}
    if action['id'] in gate['sample_action_ids']:
        p=state.get('authorized_paid_pilot',{})
        if p.get('spec_first_pass_only') is True and current_spec_attempts(action):
            return {'allowed':False,'reason':'This finite sample pilot authorizes only the current-spec first pass, no correction'}
        used=sum(len(a.get('attempts',[])) for a in state['actions'])+len(state.get('diagnostic_attempts',[]))
        allowed=bool(type(p.get('calls_ceiling')) is int and used<p['calls_ceiling']
            and p.get('max_new_paid_calls') in (1,2) and p.get('approved') is True and not p.get('closed') and not p.get('halted')
            and p.get('spec_revision_id')==revision and p.get('spec_samples_only') is True
            and action['id'] in p.get('action_ids',[])
            and set(p.get('action_ids',[]))<=set(gate['sample_action_ids']))
        return {'allowed':allowed,'reason':'Samples require an explicitly activated current-spec finite pilot'}
    if gate.get('batch_released') is not True:
        return {'allowed':False,'reason':'Other25spec actions await both current samples and explicit human/assistant approvals'}
    actions={a['id']:a for a in state['actions']}
    for aid in gate['sample_action_ids']:
        sample=actions.get(aid,{});decision=gate.get('sample_decisions',{}).get(aid,{})
        sha=sample.get('sha256')
        current=current_spec_attempts(sample);baseline=sample.get('spec_revision',{}).get('baseline_attempt_count')
        old_count=sum(t.get('spec_revision_id')!=revision for t in sample.get('attempts',[]))
        if not(sample.get('status')=='approved' and sample.get('spec_revision_id')==revision
               and sha and current and type(baseline)is int and old_count==baseline
               and all(t.get('spec_action_name')==sample.get('name') for t in current)):
            return {'allowed':False,'reason':'Old-spec approval cannot satisfy new-spec sample gate'}
        for role in ['user','assistant']:
            proof=decision.get(role,{})
            if not(proof.get('approved') is True and proof.get('source')==role
                    and proof.get('spec_revision_id')==revision and proof.get('sha256')==sha
                    and (proof.get('user_quote') if role=='user' else proof.get('review_file'))):
                return {'allowed':False,'reason':'Both sample decisions must explicitly bind current-spec final SHA'}
    return {'allowed':True,'reason':'Both current-spec samples explicitly approved by human and assistant'}
