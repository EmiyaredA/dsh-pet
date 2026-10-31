"""Pure per-action guard for the human's first-pass / one-correction policy.

Paid regeneration and explicit local repair share a limit. Original-task polling,
download recovery and initial ordinary conversion do not consume this limit.
Historical edit/revision evidence is counted conservatively, never reset by a
new recipe, quota extension, or per-action generation-cap exception.
"""
from __future__ import annotations
from datetime import datetime
import json
from kurisu_spec_revisions import spec_iteration_decision,sample_batch_decision,current_spec_attempts

LOCAL_HISTORY_KEYS=('local_edit','previous_local_edits',
                    'matte_edits','edge_revision','media_revisions','local_revisions',
                    'local_revision_history')


def correction_usage(action):
    attempts=action.get('attempts',[])
    if not isinstance(attempts,list):raise ValueError('Attempt history must be a list')
    origins=action.get('reused_origin_history',[])
    origin_count=len(origins) if isinstance(origins,list) else int(bool(origins))
    if action.get('reused') and not origin_count:origin_count=1
    paid_count=len(attempts)+origin_count
    events=set();requests=0
    for owner in [action,*attempts]:
        requested=owner.get('local_reprocess_requests',[])
        requests+=len(requested) if isinstance(requested,list) else int(bool(requested))
        for key in LOCAL_HISTORY_KEYS:
            value=owner.get(key)
            if not value:continue
            items=value if isinstance(value,list) else [value]
            for item in items:
                # Identical mirrored revision objects are one historical event.
                events.add(json.dumps(item,sort_keys=True,default=str))
    from kurisu_supplemental_retries import is_exempt_retry_attempt
    supplemental=sum(is_exempt_retry_attempt(action,i,t) for i,t in enumerate(attempts,1))
    paid=max(0,paid_count-1-supplemental)
    return {'paid_attempts_including_reused_origins':paid_count,
            'supplemental_paid_retries_exempt_from_normal_corrections':supplemental,
            'paid_corrective_rounds':paid,'historical_local_requests':requests,
            'historical_local_events':requests+len(events),
            'corrective_rounds_used':paid+requests+len(events),'first_pass':paid_count==0}


def _exception_limit(policy,action):
    """Only a later, explicitly named human instruction can lift this guard.

    This does not lift the independently enforced monetary/model quotas.
    A generic standing quota authorization or an old attempt cap is insufficient.
    """
    maximum=None
    entries=policy.get('named_action_exceptions',[])
    if not isinstance(entries,list):return None
    for entry in entries:
        if not isinstance(entry,dict):continue
        if not (entry.get('action_id')==action['id'] and entry.get('policy_id')==policy.get('id')
                and entry.get('approved') is True and entry.get('source')=='user'
                and entry.get('human_named_action') is True
                and isinstance(entry.get('user_quote'),str) and entry['user_quote'].strip()
                and not entry.get('revoked_at')):continue
        cap=entry.get('max_corrective_rounds')
        if type(cap) is not int or cap<1:continue
        try:
            effective=datetime.fromisoformat(policy['effective_at'].replace('Z','+00:00'))
            authorized=datetime.fromisoformat(entry['authorized_at'].replace('Z','+00:00'))
            if effective.tzinfo is None or authorized.tzinfo is None or authorized<effective:continue
        except (KeyError,AttributeError,TypeError,ValueError):continue
        maximum=max(cap,maximum or 0)
    return maximum


def iteration_decision(state,action,operation='submit'):
    if operation not in {'submit','local_repair','recover_original','initial_processing'}:
        raise ValueError('Unsupported iteration-policy operation')
    usage=correction_usage(action)
    result={**usage,'operation':operation,'allowed':True,'reason':'Legacy policy unchanged'}
    if action.get('human_action_hold',{}).get('active') is True and operation!='recover_original':
        reason=('Human selected existing exact-SHA media; no automatic generation or repair'
                if action['human_action_hold'].get('mode')=='immutable_selected_media'
                else 'Human deferred this action/version; await a later named instruction')
        return {**result,'allowed':False,'reason':reason}
    if operation in {'recover_original','initial_processing'}:
        if operation=='initial_processing' and action.get('spec_revision_id') and not current_spec_attempts(action):
            return {**result,'allowed':False,'reason':'Initial processing requires a source from the current specification, not old content'}
        return {**result,'reason':'Same-task recovery / initial conversion is not a corrective round'}
    from kurisu_five_attempt_policy import five_attempt_decision
    campaign=five_attempt_decision(state,action,operation)
    if campaign is not None:return {**result,**campaign}
    from kurisu_supplemental_retries import supplemental_retry_decision
    supplemental=supplemental_retry_decision(state,action,operation)
    if supplemental is not None:return {**result,**supplemental}
    if action.get('spec_revision_id'):
        revision=spec_iteration_decision(action,usage,operation)
        result.update(revision)
        if not revision['allowed']:return result
        if operation=='submit':
            batch=sample_batch_decision(state,action)
            if not batch['allowed']:return {**result,**batch}
    if 'iteration_policy' not in state:
        return {**result,'allowed':False,'reason':'Revised specification requires its named iteration policy'} if action.get('spec_revision_id') else result
    policy=state['iteration_policy']
    if not (isinstance(policy,dict) and isinstance(policy.get('id'),str) and policy['id']
            and isinstance(policy.get('source'),str) and policy['source'].strip()
            and type(policy.get('max_corrective_rounds_per_action')) is int
            and policy['max_corrective_rounds_per_action']==1):
        return {**result,'allowed':False,'reason':'Malformed one-correction human policy; fail closed'}
    extra=_exception_limit(policy,action)
    limit=extra or 1
    result.update(policy_id=policy['id'],corrective_round_limit=limit,
                  human_named_action_exception=extra is not None)
    if policy.get('stopped_action')==action['id'] and extra is None:
        return {**result,'allowed':False,'reason':'Human explicitly stopped this action; a new named-action instruction is required'}
    if operation=='submit' and usage['first_pass'] and not usage['historical_local_events']:
        return {**result,'reason':'Unattempted action first pass does not consume correction allowance'}
    if usage['corrective_rounds_used']>=limit:
        return {**result,'allowed':False,'reason':'Shared one-correction allowance consumed by paid/local history; continue other actions'}
    return {**result,'reason':'One shared corrective round remains'}


def submission_allowed(state,action):
    return iteration_decision(state,action,'submit')['allowed']


def require_local_repair(state,action):
    decision=iteration_decision(state,action,'local_repair')
    if not decision['allowed']:raise PermissionError(decision['reason'])
    return decision


def submission_priority(state,action):
    policy=state.get('iteration_policy')
    if not isinstance(policy,dict) or not policy.get('prioritize_unattempted_actions'):return 0
    return 0 if (not current_spec_attempts(action) if action.get('spec_revision_id') else correction_usage(action)['first_pass']) else 1
