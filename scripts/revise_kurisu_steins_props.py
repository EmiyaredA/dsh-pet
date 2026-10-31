"""Apply the human's second twelve-action replacement after batch30 drains.

No model or FPL call. Keep all historical media/prompt/call/attempt bytes.
"""
import copy,hashlib,json
import kurisu_library as lib
from kurisu_iteration_policy import correction_usage
from kurisu_quotas import counts,attempt_limit,extend_quota
from kurisu_spec_revisions import spec_fingerprint,sample_batch_decision,has_source
SPEC='steins-props-v3-2026-10-31'
SCOPE='steins-props-v3-12-firstpass-01'
QUOTE='人类确认了第二轮改造：等这批跑完再切；把这12条换成命运石之门道具动画，id不变，旧素材/旧提示词/失败记录/计费全部保留。未验收照常攒进待验收清单，不要为了等验收阻塞生产。'
COMMON='Fixed orthographic full-body composition. Compact props at waist height, fully inside the frame and below her chin; their controls, opening or display face HER, with the camera seeing the matte back or a narrow side. Full headwear and both shoes stay in frame, without camera tracking, push-in, reframing or scale changes. Tiny upper-body gestures; feet stay planted. Take out props during the action and completely stow them before the final original empty-handed neutral stance. Keep the approved maid outfit and compact proportions; no extra animal tail or hair clips. Any computer is a real small computer with its screen facing her, never UI on a rear cover. No emitted light on the character.'
ROWS=[
('a032','从电话微波炉里端出凝胶香蕉','Open the door of a miniature phone-microwave on a low waist-height support, with the opening facing her. Carefully lift out one pale yellow jelly-like banana on a tiny gray dish, examine its wobble once with a surprised curious look, then return it, close the door and stow the microwave, dish and support.',['miniature gray phone-microwave','pale yellow translucent jelly banana','small gray dish','low folding support']),
('a035','盯着发散计看世界线数字','Inspect a miniature charcoal divergence meter held at waist height, its row of amber numeric tubes angled toward HER. Glance between the small digits, hold a thoughtful serious expression, nod once and stow the meter. Digits need not form a particular readable number; their dim amber appearance remains confined inside the tubes.',['miniature charcoal divergence meter','small amber numeric tubes']),
('a036','抱着乌帕玩偶晃','Cradle a tiny round pale pink Upa plush with short stubby limbs below her chin. Sway the plush gently left then right with her forearms, smile bashfully and completely stow it. It is a separate stuffed toy, never a new body part.',['small round pale pink Upa plush toy']),
('a037','按下微波炉按钮发 D-mail','Place a miniature gray phone-microwave at waist height on a small support, controls facing her. Press one physical button, glance toward a tiny connected charcoal phone with its screen facing her, make a quiet satisfied nod, then stow phone, cable, microwave and support. No lightning, portals, beams or changes to the background.',['miniature gray phone-microwave','tiny charcoal phone','short gray connecting cable','low folding support']),
('a038','戴上时间跳跃耳机','Lift a pair of compact charcoal time-leap headphones with muted-red ear pads, place them gently around the existing headband without removing or changing its cat-ear lace ornaments, pause with eyes closed in concentration, open her eyes, remove and stow the headphones. The two hands and headphone band remain separate clear shapes.',['compact charcoal time-leap headphones with muted-red ear pads']),
('a043','别上 LabMem 徽章','Take out one small round silver-gray LabMem badge, inspect its tiny abstract orange emblem, carefully pin it to the existing apron bib with a restrained upper-body gesture, glance down proudly, then unpin and stow it. The complete figure including ear tips and shoes remains visible throughout; no readable lettering is required.',['tiny round silver-gray LabMem badge with abstract orange emblem']),
('a044','擦拭 IBN 5100 老电脑','Set a miniature beige IBN 5100 vintage portable computer on a waist-height support, its keyboard and small dark CRT facing her. The viewer sees only the plain beige rear casing and a narrow side. Wipe its casing twice with a small gray cloth, inspect it fondly, then stow computer, cloth and support.',['miniature beige IBN 5100 vintage portable computer','small gray wiping cloth','low folding support']),
('a047','调整时间机器天线','Set a tiny charcoal time-machine console with a short muted-red antenna at waist level. Adjust the antenna tip through one small arc with careful upper-body hand movements, check the small console facing HER, nod and stow the antenna and console. Upper-body performance only; retain complete fixed full-body framing and all feet, with antenna below her chin and no camera tracking.',['tiny charcoal time-machine console','short muted-red antenna']),
('a049','端详怀表','Take out a tiny closed brass pocket watch with a short chain, open it at waist height with the dial facing HER, inspect it with a thoughtful head tilt, close the cover and stow watch and chain completely.',['tiny brass pocket watch with short chain']),
('a050','盯着手机等 D-mail 回信','Hold a tiny charcoal phone at waist height, screen facing HER. Wait expectantly, glance once away then back, notice a small static amber envelope icon on her screen, relax into a tiny relieved smile and stow the phone. No readable message, external notification bubble or emitted light.',['tiny charcoal phone with non-emissive amber envelope icon']),
('a055','披上白大褂','Take out a short white laboratory coat, slip both arms into the sleeves and settle it over her existing cat-ear maid costume without changing the hair or headwear. Briefly adjust its lapels with a confident serious look, remove it and fold it away, restoring the unchanged maid outfit and baseline stance. The coat stays above the shoe tops; ear tips and feet remain fully in frame and the camera never pushes in or follows.',['short white laboratory coat worn temporarily over existing maid costume']),
('a057','喝 Dr Pepper','Take out one small dark maroon Dr Pepper soda can, bring its opening toward her mouth for one restrained sip, lower it with a satisfied little nod and stow it. Keep the rim below the nose and both eyes visible; the label is a simple maroon-and-ivory design and exact readable lettering is not required.',['small dark maroon Dr Pepper soda can with ivory label'])]
IDS=[r[0] for r in ROWS]
SAMPLES={'a034':'e7a63c9ca2bddb6f6ef39779569a0bc2ffed0894637a34a2693b2ca02a1a99fc','a052':'4a364ce1a3fa107730a85aad0a70050cc330dda8a06b7a165ec2190770acdc77'}
def revise(s,stamp):
    before=counts(s);outside=copy.deepcopy([a for a in s['actions'] if a['id'] not in IDS]);changes=[]
    for aid,name,direction,props in ROWS:
        a=next(a for a in s['actions'] if a['id']==aid)
        if a.get('spec_revision_id')==SPEC:continue
        if a['status'] in {'generating','submission_uncertain','local_processing','awaiting_processing'} or any(t.get('processing_claim') for t in a['attempts']):raise ValueError('Original task not drained: '+aid)
        old=copy.deepcopy({k:v for k,v in a.items() if k not in ['attempts','spec_revision_history']});usage=correction_usage(a);previous=a.get('spec_revision_id');n=len(a['attempts']);old_attempts=copy.deepcopy(a['attempts'])
        a.setdefault('spec_revision_history',[]).append({'at':stamp,'old_spec_revision_id':previous,'new_spec_revision_id':SPEC,'previous_action_metadata':old,'old_attempt_count':n,'old_corrective_usage':usage,'source':'user','user_quote':QUOTE,'reason':'Explicit second named twelve-action Steins prop replacement; batch30 already complete; no old bytes deleted.'})
        a.update(name=name,direction=direction+' '+COMMON,props=props,status='planned',spec_revision_id=SPEC,spec_revision={'id':SPEC,'authorized_at':stamp,'baseline_attempt_count':n,'baseline_corrective_rounds_used':usage['corrective_rounds_used'],'max_corrective_rounds':1,'new_first_pass_required':True,'source':'user','user_quote':QUOTE},prop_type='steins-gate-props',prompt_strategy='steins-props-v3-firstpass-green')
        for key in list(a):
            if key.startswith('next_') or key in ['prompt_file','prompt_sha256','file','sha256','poster','delivery_asset_id','delivery_node_id','delivery_upload_started','human_approval','approval_basis','source_quality']:
                a.pop(key,None)
        for key in ['quality_hold','repair_instruction']:
            if key in a:a.setdefault('superseded_'+key+'s',[]).append({'spec_revision_id':previous,'value':a.pop(key)})
        s['iteration_policy'].setdefault('named_action_exceptions',[]).append({'action_id':aid,'policy_id':s['iteration_policy']['id'],'approved':True,'source':'user','human_named_action':True,'user_quote':QUOTE,'authorized_at':stamp,'authorization_id':SPEC+'-'+aid,'spec_revision_id':SPEC,'max_corrective_rounds':usage['corrective_rounds_used']+2,'baseline_corrective_rounds_used':usage['corrective_rounds_used'],'reason':'Explicit replacement specification firstpass and at most one shared paid/local correction; old usage not reset'})
        while attempt_limit(s,aid)<n+2:
            extend_quota(s,request_id=SPEC+'-'+aid+'-attempt-cap-'+str(attempt_limit(s,aid)+1),reason='Explicit new twelve props spec '+aid+' old attempt history preserved; new firstpass plus one shared correction only',action_ids=[aid])
        assert a['attempts']==old_attempts
        changes.append({'id':aid,'old_name':old['name'],'name':name,'previous_spec':previous,'baseline_attempts':n,'previous_approved':old['status']=='approved'})
    if changes:
        s.setdefault('spec_batch_gates',{})[SPEC]={'gate_type':'direct_human_scope','spec_revision_id':SPEC,'enabled':True,'batch_released':True,'action_ids':IDS,'user_approval':{'approved':True,'source':'user','spec_revision_id':SPEC,'user_quote':QUOTE,'at':stamp},'spec_fingerprints':{a['id']:spec_fingerprint(a) for a in s['actions'] if a['id'] in IDS},'human_review_is_async':True,'sample_action_ids':[],'sample_decisions':{}}
        s.setdefault('spec_revision_operations',[]).append({'id':SPEC,'at':stamp,'action_ids':IDS,'source':'user','user_quote':QUOTE,'changes':changes,'counts_before':before,'counts_after':counts(s),'physical_files_changed':False})
    assert counts(s)==before
    assert outside==[a for a in s['actions'] if a['id'] not in IDS]
    assert all(sample_batch_decision(s,a)['allowed'] for a in s['actions'] if a['id'] in IDS)
    return changes

def main():
    out=lib.ROOT/'temp/kurisu'/SCOPE;out.mkdir(parents=True,exist_ok=True)
    prior=json.loads((lib.PACK/'quality/batches/programmer-research-v2-batch30-firstpass-01.json').read_text());assert prior['status']=='completed' and prior['in_progress']==prior['awaiting_review']==prior['not_submitted']==0
    with lib.production_lock():
        s=lib.load();before=counts(s);assert s['authorized_paid_pilot'].get('closed') is True
        assert not any(a['status'] in {'generating','submission_uncertain','local_processing','awaiting_processing'} or any(t.get('processing_claim') for t in a['attempts']) for a in s['actions'])
        for aid,digest in SAMPLES.items():
            a=next(a for a in s['actions'] if a['id']==aid);assert a['status']=='approved' and a['sha256']==digest and hashlib.sha256((lib.PACK/a['file']).read_bytes()).hexdigest()==digest
        stamp=lib.now();changes=revise(s,stamp);lib.save(s)
    groups={};directions={}
    for a in s['actions']:groups.setdefault(a['group'],[]).append(a['name']);directions.setdefault(a['group'],[]).append(a['direction'])
    for filename,value in [('action-groups.json',groups),('action-directions.json',directions)]:
        (lib.PACK/filename).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    fullpath=lib.PACK/'kurisu-config.full.json';full=json.loads(fullpath.read_text())
    for category in full['animations']['categories']:
        if category['id'] in groups:category['actions']=groups[category['id']]
    fullpath.write_text(json.dumps(full,ensure_ascii=False,indent=2)+'\n')
    audit={'at':stamp,'spec_revision_id':SPEC,'scope_id':SCOPE,'changes':changes,'counts_before':before,'counts_after':counts(lib.load()),'history_preserved':True,'physical_files_changed':False,'other_actions_unchanged':True,'accepted_samples_unchanged':True,'current_approved':sum(a['status']=='approved' for a in s['actions'])}
    (out/'spec-revision-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');print(json.dumps(audit,ensure_ascii=False))
if __name__=='__main__':main()
