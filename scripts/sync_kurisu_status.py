#!/usr/bin/env python3
"""Synchronize the recorded quality stop to FPL; never create a model task."""
from uuid import uuid4
import hashlib
import json
from kurisu_library import load, save, production_lock, now
from kurisu_quotas import effective_limits, counts
from kurisu_submission_errors import safe_submission_error


def status_operations(state, canvas):
    ids={n.id for n in canvas.nodes}; operations=[]
    for action in state['actions']:
        for old in action.get('withdrawn_approvals',[])+action.get('media_revisions',[]):
            node=old.get('delivery_node_id')
            if node and node in ids and node!=action.get('delivery_node_id'):
                operations.append({'entity':'node','action':'update','id':node,'value':{
                    'approved':False,'title':'已撤回历史版本 · '+action['name']}})
        if action['status'] in {'approved','generating','submission_uncertain'}:continue
        if action.get('node_id') not in ids:continue
        label=('复核暂挂 · ' if action['status']=='quality_recheck_hold' else
               '尚未生成 · ' if not action['attempts'] and not action.get('withdrawn_approvals') else '未通过验收 · ')
        operations.append({'entity':'node','action':'update','id':action['node_id'],'value':{
            'approved':False,'title':label+action['name']}})
    count=sum(a['status']=='approved' for a in state['actions'])
    usage=counts(state);limits=effective_limits(state)
    active=sum(a['status'] in {'generating','submission_uncertain'} for a in state['actions'])
    quota_note=('用户已授权持续制作至106条合格，当前额度可按审计记录分批扩展；历史调用不重置。'
                if state.get('standing_authorization',{}).get('approved') else '调用额度以当前授权为限。')
    preview_note=('桌面默认临时显示已定稿原图的静态透明预览；它不计106条、不代表待机已完成。'
                  if state.get('preview_static_placeholder') else
                  '桌面默认临时借用明确指定的已合格动作本名；不补算缺失待机。'
                  if state.get('preview_idle_override') else '')
    text=(f'部分交付：合格 {count}/106；累计模型调用 {usage["calls"]}/{limits["total_calls"]}；动作返修 {usage["repairs"]}/{limits["repair_calls"]}；原任务生成/对账中 {active} 条。\n'
          +quota_note+'\n'
          '当前生成路线仍在受控验证；质量停线防止重复相同失败配方，失败与诊断素材不计完成。源片人物移动光斑、眼脸形变、额外耳尾、白岛或裁切均拒收。\n'
          '禁止白底阈值挖色、拼补五官和短步态循环。原片与透明成片分别独立验收；技术Alpha通过不等于视觉合格。\n'
          '调度实现最多6路模型、2路本地处理，任务预留/台账提交/画布写入短锁；下载、转码与视觉验收在锁外。断点恢复沿用原任务 ID，不重复调用模型。\n'
          f'完整正式配置未提升；隔离实时桌宠保留{count}条合格动作。{preview_note}保留位置、名称、尺寸和朝向。当前无合格移动素材，自动漫游暂停。\n'
          '提示词使用 h3-prompt-writing 六段结构及唯一正面定稿图；三视图仅存档。电脑版实验记录屏幕朝角色，外侧只见灰色背盖。\n'
          '完整动作、逐次任务/提示词/哈希、拒收证据与缺口见 library.json、ACTIONS.md、GAPS.md、quality/。完整配置未提升。')
    if 'production-brief' in ids:
        operations.append({'entity':'node','action':'update','id':'production-brief','value':{'text':text}})
    return operations


def status_fingerprint(state):
    """Only fields that determine the visible status intent, not unrelated edits."""
    projection={'project_id':state['project_id'],'usage':counts(state),'limits':effective_limits(state),
        'standing_authorized':bool(state.get('standing_authorization',{}).get('approved')),
        'preview_static_declared':bool(state.get('preview_static_placeholder')),
        'preview_idle_override_declared':bool(state.get('preview_idle_override')),
        'actions':[{'id':a['id'],'name':a['name'],'status':a['status'],'node_id':a.get('node_id'),
            'delivery_node_id':a.get('delivery_node_id'),'has_attempts':bool(a['attempts']),
            'historical_delivery_nodes':[old.get('delivery_node_id') for old in a.get('withdrawn_approvals',[])+a.get('media_revisions',[])]}
            for a in state['actions']]}
    return hashlib.sha256(json.dumps(projection,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def _record_event(state,event):
    event.setdefault('at',now())
    state.setdefault('canvas_status_sync_history',[]).append(event)
    state['canvas_status_sync']=event


def _verify_operations(canvas,operations,applied_revision):
    if canvas.revision<applied_revision:return False
    by_id={n.id:n for n in canvas.nodes}
    return all(op['id'] in by_id and all(getattr(by_id[op['id']],key,None)==value
        for key,value in op['value'].items()) for op in operations)


def sync_status(client,max_stale_retries=1):
    """Snapshot -> unlocked remote CAS/verify -> short fresh-ledger commit.

    A relevant concurrent edit invalidates the old snapshot even after a remote
    apply succeeded. Record it as stale without advancing the local synced
    revision. At most one fresh retry is allowed; no model methods are called.
    """
    if type(max_stale_retries) is not int or max_stale_retries not in (0,1):
        raise ValueError('Status sync permits zero or one fresh stale-snapshot retry')
    sync_id=str(uuid4())
    for attempt in range(max_stale_retries+1):
        with production_lock():
            state=load();fingerprint=status_fingerprint(state);pid=state['project_id']
        phase='get';canvas=None;applied_revision=None;verified=None
        try:
            canvas=client.visual.get_canvas(project_id=pid)
            operations=status_operations(state,canvas)
            phase='apply'
            if operations:
                result=client.visual.apply_canvas_operations(project_id=pid,body={
                    'expected_revision':canvas.revision,'request_id':str(uuid4()),'operations':operations})
                applied_revision=result.revision
            else:
                applied_revision=canvas.revision
            phase='verify'
            verified=client.visual.get_canvas(project_id=pid)
        except Exception as exc:
            with production_lock():
                fresh=load();current=status_fingerprint(fresh);event={'sync_id':sync_id,'attempt':attempt+1,'status':phase+'_failed',
                    'snapshot_fingerprint':fingerprint,'current_fingerprint':current,'snapshot_stale':current!=fingerprint,
                    'applied_revision':applied_revision,'needs_retry':True,'error':safe_submission_error(exc)}
                _record_event(fresh,event);save(fresh)
            raise
        verification_passed=_verify_operations(verified,operations,applied_revision)
        with production_lock():
            fresh=load();current=status_fingerprint(fresh)
            stale=current!=fingerprint
            event={'sync_id':sync_id,'attempt':attempt+1,'status':'stale' if stale else ('synced' if verification_passed else 'verify_failed'),
                'snapshot_fingerprint':fingerprint,'current_fingerprint':current,
                'snapshot_stale':stale,
                'expected_revision':canvas.revision,'applied_revision':applied_revision,
                'verified_revision':verified.revision,'remote_values_verified':verification_passed,
                'operation_count':len(operations),'needs_retry':stale or not verification_passed}
            if event['status']=='synced':
                # Another successful status sync may have committed a newer
                # proof while our readback was in flight; never regress it.
                fresh['canvas_status_revision']=max(fresh.get('canvas_status_revision',0),applied_revision)
                event['committed_revision']=fresh['canvas_status_revision']
            _record_event(fresh,event);save(fresh)
        if stale:
            if attempt<max_stale_retries:continue
            return event
        if not verification_passed:raise RuntimeError('Canvas status readback did not verify the applied values; local revision unchanged')
        return event


if __name__=='__main__':
    from future_props_lab.desktop import desktop_client
    with desktop_client() as client:
        result=sync_status(client)
    print(json.dumps(result,ensure_ascii=False))
    if result['needs_retry']:raise SystemExit(1)
