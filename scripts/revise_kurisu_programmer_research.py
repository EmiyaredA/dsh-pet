#!/usr/bin/env python3
"""Explicit human revision of 27 specs; preserves all paid/source history.

Only metadata and staged106config are changed. The formal pet config and
physical media remain untouched. This command never calls FPL or model APIs.
"""
import copy,hashlib,json
from pathlib import Path
import kurisu_library as lib
from kurisu_iteration_policy import correction_usage
from kurisu_quotas import counts,attempt_limit,extend_quota
SPEC='programmer-research-v2-2026-10-31'
IDS=[f'a{i:03d}' for i in range(30,57)]
SAMPLES=['a034','a052']
USER_MESSAGE_ID='01a1908d-f493-7621-b2ce-105402a4a118'
USER_QUOTE='这 27 条状态重置为 planned 重新排队，不要动 a001–a029 和 a057 之后已通过验收的动作。'
FRAMING='全身固定镜头；括号中的半身/腰部以上指动作集中在上半身，不裁成半身景别。头饰、双手与双脚始终完整入画；不推拉、不跟拍，不离开画面。'
COMMON='Keep the full figure centered at a fixed scale, with headwear and both shoes visible throughout. Perform compact upper-body gestures; only when this named action explicitly calls for sitting, a foot swing or an in-place gait may the legs move. No camera push/pull, tracking, framing change or travel toward or away from the viewer. All props are miniature, below the chin, then completely stowed; finish empty-handed in the reference stance. Any laptop screen and keyboard face HER; the camera sees only the plain matte gray exterior back lid and hinge. Any visible UI uses abstract marks/icons, no readable text or emitted light.'
# The two None entries preserve the original laboratory action directions.
ROWS=[
('翻文档查资料','Turn a few pages of a tiny neutral-gray technical booklet, pause to compare two abstract diagrams and trace one line with a fingertip, then close and stow it.',['tiny gray technical booklet with abstract diagrams']),
('伏案敲代码','Open a small gray laptop on a waist-high folding support, screen and keyboard facing her and back lid facing the viewer. Type two short focused bursts, pause to inspect her unseen screen, then close and stow the laptop and support.',['gray laptop computer','waist-high folding support']),
('检查试管（沿用原实验室镜头）',None,['original miniature test tube laboratory cameo']),
('盯编译进度','Watch a small charcoal status card held at waist height as a row of static amber blocks fills once. Lean her head slightly with patient concentration, give a tiny relieved nod and stow the card.',['charcoal compilation card with abstract amber progress blocks']),
('报错拍键盘（半身）','Set a tiny gray keyboard on a waist-high folding support. Notice one small static dark-red error square, frown briefly, give the keyboard one restrained palm tap using only her upper body, then exhale, compose herself and stow keyboard and support. Feet stay planted and the complete head and shoes stay in view.',['small gray keyboard','waist-high folding support','static dark-red error square']),
('查看显微镜（沿用原实验室镜头）',None,['original miniature microscope laboratory cameo']),
('拿网兜追 bug','Hold a tiny gray mesh net and guide it through one short arc at waist height to catch a small amber mechanical bug toy moving only a few centimeters near her hands. Smile and stow toy and net without stepping away.',['miniature gray mesh net','small amber mechanical bug toy']),
('对橡皮鸭讲代码','Hold a small yellow rubber duck below her chin, make two precise explanatory finger gestures toward it with a thoughtful expression, nod once as if understanding a solution, then stow it.',['miniature yellow rubber duck']),
('翻 git log 找元凶','Scroll a tiny charcoal history card bearing stacked abstract amber lines, inspect one dark-red dot, point to it with a knowing expression and stow the card.',['charcoal history card with abstract lines and a dark-red dot']),
('提交后松口气','Tap a miniature gray keyboard once on a waist-high folding support, pause, relax her shoulders and give a small closed-mouth sigh of relief, then stow keyboard and support.',['small gray keyboard','waist-high folding support']),
('合并冲突抱头','Inspect two small gray cards with crossing amber/red abstract strokes, place them low on a tiny waist support, briefly hold the sides of her head with an exasperated look, then calm down and stow all props.',['two gray abstract conflict cards','waist-high support']),
('白板画架构图','Hold a tiny ivory diagram board below the chin and use a short dark marker to connect three charcoal boxes with two lines. Nod at the completed abstract architecture diagram, then stow board and marker.',['small ivory diagram board','short dark marker']),
('左右核对 diff','Hold two small charcoal comparison cards at waist level, shift her gaze left then right between abstract amber/red line patterns, point once at a changed mark and stow both cards.',['two charcoal diff cards with abstract amber/red lines']),
('往屏幕边贴便签','Set a tiny gray laptop below her chin with the screen facing her and plain back lid toward the viewer. Attach one pale-pink note to the edge of the lid, check it from her side, remove the note and stow the computer, note and support.',['gray laptop computer','pale-pink blank note','waist-high support']),
('拆键盘换键帽（半身）','Place a tiny gray keyboard on a waist-high folding support, gently lift one amber keycap with a small gray puller, press the replacement into place, test it once and stow the keyboard, puller and support. All manipulation stays at waist height.',['small gray keyboard','small gray keycap puller','one amber keycap','waist-high support']),
('戴耳机写码晃脚','Put on small charcoal headphones while sitting briefly on a compact gray stool at a tiny laptop support. Make a short typing gesture with the screen facing her, swing one foot gently without leaving the frame, then stand, remove headphones and stow every prop.',['charcoal headphones','gray laptop computer','compact gray stool','waist-high support']),
('凑近屏幕皱眉调试','Open a miniature gray laptop on a waist-high support, screen facing her. Lean only her head and shoulders slightly toward the unseen screen, frown in concentration, make one short touchpad adjustment, straighten and stow computer and support.',['gray laptop computer','waist-high folding support']),
('插拔网线（腰部以上入画）','At waist height, connect a short muted-red network cable between a tiny gray laptop and a charcoal network box, disconnect it once and look satisfied. Keep both cable ends visible near her hands, then stow all props; head and shoes remain fully framed.',['short muted-red network cable','tiny gray laptop computer','charcoal network box']),
('拍笔记本重启（半身）','Set a miniature gray laptop on a waist-high folding support, screen facing her and plain rear lid toward the viewer. Give the side of the laptop one small restrained palm pat, press one button near the hinge, wait briefly with a hopeful look, then close and stow computer and support.',['gray laptop computer','waist-high folding support']),
('转笔想方案','Rotate a short gray pen once between her fingers at chest height, pause with a thoughtful head tilt, make a small idea nod and stow the pen.',['short gray pen']),
('被催进度看表','React to an imagined prompt with a brief guilty glance toward the viewer, inspect a small plain gray wristwatch, look back with a composed small nod and lower her hands.',['small gray wristwatch with abstract face']),
('摸鱼刷手机被抓','Hold a tiny charcoal phone low at the waist, make two small scrolling gestures, notice the viewer and freeze with a shy embarrassed look, then quickly stow the phone and return to a neutral stance.',['small charcoal phone with abstract amber shapes']),
('CI 绿灯比耶','Hold a small charcoal CI status card at waist height with one static GREEN painted check mark. Notice the successful check, smile and make a compact V sign with the other hand near her chest, then lower the hand and completely stow the card. The green check is flat ink, not light, and stays on the card.',['small charcoal CI status card','static non-emissive GREEN check mark; BLUE background required']),
('CI 红了瘫椅子','Inspect a small charcoal status card with one static dark-red cross, sit briefly on a compact gray chair and slump her shoulders in comic disappointment while both shoes remain visible. Recover, stand, stow card and chair and restore the neutral stance.',['charcoal CI card with static dark-red cross','compact gray chair']),
('上线成功举手','Check a small charcoal release card with one static amber confirmation circle, give one compact celebratory hand lift no higher than the existing ear tips, smile and stow the card before returning both hands to neutral.',['charcoal release card with static amber icon']),
('打卡拎包跑','Tap a small gray attendance card to a tiny charcoal reader at waist height, stow the card and reader, pick up a small brown work bag and turn into a strict SCREEN-LEFT SIDE PROFILE, with nose, chest, hips, knees and shoe toes all pointing left and only the near eye visible. Take three tiny jogging steps LEFT IN PLACE, keeping full headwear and shoes in frame at a fixed center and scale. Rightward display is the runtime mirror of this left-facing gesture, never frontal marching or travel toward/away from the viewer. Stop, turn back to FRONT and stow the bag, restoring the planted neutral stance.',['small gray attendance card','tiny charcoal reader','small brown work bag']),
('瘫着怀疑人生','Sit briefly on a compact gray chair, let her shoulders droop and stare ahead with a tiny deadpan expression. Blink slowly, straighten, stand up, stow the chair and return to the empty-handed neutral stance.',['compact gray chair']),
]

def revise(state,stamp):
    before=counts(state);actions={a['id']:a for a in state['actions']};policy=state['iteration_policy'];changes=[]
    for aid,(name,direction,props) in zip(IDS,ROWS):
        a=actions[aid]
        if a.get('spec_revision_id')==SPEC:continue
        if a['status'] in {'generating','submission_uncertain','local_processing'}:raise ValueError('Existing action is active; reconcile before specification revision: '+aid)
        old=copy.deepcopy({k:v for k,v in a.items() if k not in ['attempts','spec_revision_history']});usage=correction_usage(a);previous=a.get('spec_revision_id','original-research-v1');count=len(a['attempts'])
        for t in a['attempts']:
            t.setdefault('spec_revision_id',previous);t.setdefault('spec_action_name',a['name']);t.setdefault('superseded_by_spec_revision',SPEC)
        a.setdefault('spec_revision_history',[]).append({'at':stamp,'old_spec_revision_id':previous,'new_spec_revision_id':SPEC,'previous_action_metadata':old,'old_attempt_count':count,'old_corrective_usage':usage,'user_message_id':USER_MESSAGE_ID,'reason':'User explicitly replaced all27 research/play specifications with programmer preferences; old media/history remain distinct.'})
        a.update(name=name,direction=(direction+' '+COMMON) if direction else old['direction'],props=props,framing_note=FRAMING,status='planned',spec_revision_id=SPEC,spec_revision={'id':SPEC,'authorized_at':stamp,'user_message_id':USER_MESSAGE_ID,'baseline_attempt_count':count,'baseline_corrective_rounds_used':usage['corrective_rounds_used'],'max_corrective_rounds':1,'new_first_pass_required':True},prompt_strategy='programmer-spec-pending-two-samples')
        for key in list(a):
            if key.startswith('next_') or key in ['prompt_file','prompt_sha256','file','sha256','poster','delivery_asset_id','delivery_node_id','delivery_upload_started','human_approval','approval_basis','source_quality']:
                a.pop(key,None)
        if 'quality_hold' in a:a.setdefault('superseded_quality_holds',[]).append({'spec_revision_id':previous,**a.pop('quality_hold')})
        if 'repair_instruction' in a:a.setdefault('superseded_repair_instructions',[]).append(a.pop('repair_instruction'))
        a['prop_type']='laptop-computer' if any('laptop' in p for p in props) else 'programmer-props' if direction else 'laboratory-cameo'
        policy.setdefault('named_action_exceptions',[]).append({'action_id':aid,'policy_id':policy['id'],'approved':True,'source':'user','human_named_action':True,'user_quote':USER_QUOTE,'authorized_at':stamp,'authorization_id':SPEC+'-'+aid,'spec_revision_id':SPEC,'max_corrective_rounds':usage['corrective_rounds_used']+2,'reason':'New human-named specification firstpass + one shared paid/local correction; old usage not reset','baseline_corrective_rounds_used':usage['corrective_rounds_used']})
        target=count+2
        while attempt_limit(state,aid)<target:
            extend_quota(state,request_id=SPEC+'-'+aid+'-attempt-cap-'+str(attempt_limit(state,aid)+1),reason='Explicit new27spec revision '+aid+' allows oldlen+2 totalpaidattemptcapacity; spec gate separatelylimitsnewfirstpass+onecorrection',action_ids=[aid])
        changes.append({'action_id':aid,'old_name':old['name'],'new_name':name,'old_direction':old['direction'],'new_direction':a['direction'],'props':props,'baseline_attempts':count,'baseline_usage':usage,'paid_attempt_cap_after':attempt_limit(state,aid),'current_spec_calls':0,'laboratory_cameo':direction is None})
    if changes:
        state.setdefault('spec_batch_gates',{})[SPEC]={'spec_revision_id':SPEC,'enabled':True,'sample_action_ids':SAMPLES,'batch_released':False,'sample_decisions':{},'require_current_spec_sha_bound_user_and_assistant':True,'created_at':stamp,'user_message_id':USER_MESSAGE_ID,'reason':'Onlya034/a052samplesfirst; other25cannotqueueuntilbothareexplicitlyacceptedbyhumanandassistant'}
        state.setdefault('spec_revision_operations',[]).append({'id':SPEC,'at':stamp,'user_message_id':USER_MESSAGE_ID,'action_ids':IDS,'samples':SAMPLES,'changes':changes,'counts_before':before,'counts_after':counts(state),'physical_files_changed':False})
    assert counts(state)==before
    return changes

def write_gaps(state):
    coverage=state['production_coverage'];approved=[a for a in state['actions'] if a['status']=='approved'];u=counts(state)
    lines=['# 当前缺口（含明确的新规格）','',f"当前通过{len(approved)}/106；缺口{106-len(approved)}。当前规格原片覆盖{coverage.get('current_spec_source_action_count',coverage['source_action_count'])}/106；历史原片覆盖{coverage['source_action_count']}/106。",'','27条旧研究素材仍完整保留；它们不满足新程序员规格，扣除的是当前规格覆盖，不是删除历史。',f"累计{u['calls']}模型调用、{u['repairs']}历史返修、{u['other_model_calls']}其它模型；历史用量未重置。",'', '新27项仅先看a034/a052样片；双方明确批准当前规格/同SHA后才可制作其它25项。正式pet配置未提升。','', '| ID | 分类 | 当前动作 | 状态 | 说明 |','|---|---|---|---|---|']
    for a in state['actions']:
        if a['status']=='approved':continue
        reason=('新规格待首轮；先a034/a052双样片；旧规格源仅历史可见' if a.get('spec_revision_id')==SPEC else (a.get('quality_hold',{}).get('reason') or (a['attempts'][-1].get('processing_error') if a['attempts'] else '') or '待按原规格继续'))
        lines.append(f"|{a['id']}|{a['group']}|{a['name']}|{a['status']}|{str(reason).replace('|','/').replace(chr(10),' ')[:400]}|")
    (lib.PACK/'GAPS.md').write_text('\n'.join(lines)+'\n')

def main():
    with lib.production_lock():
        state=lib.load();outside_before=copy.deepcopy([a for a in state['actions'] if a['id'] not in IDS]);formal=lib.PACK/'pet/kurisu-config.json';formal_sha=hashlib.sha256(formal.read_bytes()).hexdigest();stamp=lib.now();changes=revise(state,stamp)
        clarifications=[]
        for aid,(_,direction,_) in zip(IDS,ROWS):
            if direction is None:continue
            a=next(a for a in state['actions'] if a['id']==aid);wanted=direction+' '+COMMON
            if a['direction']==wanted:continue
            if any(t.get('spec_revision_id')==SPEC for t in a['attempts']):raise ValueError('Currentspec already submitted; use a new immutable revision instead of editing '+aid)
            change={'at':stamp,'spec_revision_id':SPEC,'old_direction':a['direction'],'new_direction':wanted,'reason':'Rootclarifiesfullbodyfixedcenter;onlynamedseating/footswing/inplacegaitmaymovelegs; a055strictSCREEN-LEFTprofilegait. Nobaselineorhistoryreset.'}
            a.setdefault('spec_clarification_history',[]).append(change);a['direction']=wanted;clarifications.append({'action_id':aid,**change})
        groups=json.loads((lib.PACK/'action-groups.json').read_text());directions=json.loads((lib.PACK/'action-directions.json').read_text());group=next(a for a in state['actions'] if a['id']=='a030')['group'];selected=[a for a in state['actions'] if a['id'] in IDS];groups[group]=[a['name'] for a in selected];directions[group]=[a['direction'] for a in selected]
        # Change only this category's name mapping in the staged full config.
        full=json.loads((lib.PACK/'kurisu-config.full.json').read_text());category=next(c for c in full['animations']['categories'] if c['id']==group);category['actions']=groups[group]
        for file,value in [('action-groups.json',groups),('action-directions.json',directions),('kurisu-config.full.json',full)]:
            target=lib.PACK/file;temp=target.with_suffix('.spec.pending.json');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temp.replace(target)
        lib.save(state);write_gaps(state);assert outside_before==[a for a in state['actions'] if a['id'] not in IDS];assert hashlib.sha256(formal.read_bytes()).hexdigest()==formal_sha
        record={'spec_revision_id':SPEC,'at':stamp,'user_message_id':USER_MESSAGE_ID,'user_quote_excerpt':USER_QUOTE,'action_count':27,'actions':[{'action_id':a['id'],'name':a['name'],'direction':a['direction'],'props':a['props'],'framing_note':a['framing_note'],'baseline':a['spec_revision'],'old_spec_name':a['spec_revision_history'][-1]['previous_action_metadata']['name'],'current_spec_calls':sum(t.get('spec_revision_id')==SPEC for t in a['attempts'])} for a in selected],'root_framing_clarifications':clarifications,'sample_gate':state['spec_batch_gates'][SPEC],'production_coverage':state['production_coverage'],'counts_unchanged':counts(state),'formal_pet_config_sha256_unchanged':formal_sha,'physical_media_unchanged':True,'all_other_actions_preserved':True,'paid_calls_added':0,'global_budget_not_extended':True,'only_per_action_paid_caps_audited':True,'user_request_file':'quality/spec-revisions/'+SPEC+'/user-request.json','user_request_file_sha256':hashlib.sha256((lib.PACK/'quality/spec-revisions'/SPEC/'user-request.json').read_bytes()).hexdigest()}
        folder=lib.PACK/'quality/spec-revisions'/SPEC;folder.mkdir(parents=True,exist_ok=True);(folder/'manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'spec':SPEC,'revised':len(changes),'coverage':state['production_coverage'],'counts':counts(state),'formal_unchanged':True},ensure_ascii=False))
if __name__=='__main__':main()
