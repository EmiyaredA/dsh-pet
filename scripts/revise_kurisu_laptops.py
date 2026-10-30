#!/usr/bin/env python3
"""Apply the user's laptop-computer correction without submitting model tasks."""
import json
from uuid import uuid4
from kurisu_library import PACK,load,save,production_lock,prompt_for,now

DIRECTIONS={
    'a011': 'From seconds 0 to 2 pivot from the neutral FRONT stance into a strict SCREEN-LEFT SIDE PROFILE. The nose, chest, hips, knees and shoe toes point left; only the near eye is visible. Take a miniature CLOSED SILVER-GRAY LAPTOP COMPUTER with a rigid two-piece metal clamshell, visible rear hinge and thin side vents, and hug it securely against the waist below the chin. It is a computer, never a paper notebook, book or folder. Between seconds 2 and 8 take small LEFTWARD IN-PLACE side-profile steps while holding the closed laptop with both hands. Stay centered with full ears and shoes inside the wide padded framing. Do not travel toward the viewer or march frontally. From seconds 8 to 9 stop, turn to FRONT and completely stow the laptop. By seconds 9 to 10 hold the exact original empty-handed front standing stance. The runtime mirrors this left-facing gait to face right and moves the window only horizontally.',
    'a031': 'Bring a tiny neutral-gray LAPTOP COMPUTER into view in front of the waist, with its screen and keyboard facing HER. The viewer sees only the plain matte gray exterior BACK LID and hinge; there is no UI, screen, webcam or keyboard on the back cover. Type focused short bursts with both hands behind the lid, pause to inspect her screen, then close and stow the laptop. Keep the entire device below the chin and the full face and feet visible.',
    'a056': 'Take a miniature CLOSED silver-gray LAPTOP COMPUTER with a rigid two-piece metal clamshell, visible rear hinge, thin side vents and small rubber feet. The closed computer slips only a few centimeters; react with a small surprised expression and catch it with both hands at waist height before it falls. Keep the face and full body clear, put the computer completely away and relax. The outer cover stays plain gray. No paper pages, paper notebook, screen, interface or readable text is visible.',
    'a100': 'Take a miniature CLOSED silver-gray LAPTOP COMPUTER with a rigid two-piece metal clamshell, visible rear hinge and thin side vents, and hug it against the waist below the chin. Look thoughtfully aside and make a few subtle silent muttering mouth movements, then look forward, stow the computer completely and return to the empty-handed closed-mouth neutral smile. The outer cover stays plain gray. Never use a paper notebook or book. No visible screen, interface, webcam, glowing logo or readable text.',
    'a103': 'From seconds 0 to 2 take out a miniature gray LAPTOP COMPUTER and folding gray support. Open it below the chin with the screen and keyboard facing HER; the viewer sees ONLY the plain matte gray EXTERIOR BACK LID and rear hinge. No UI, data, screen, webcam or keyboard exists on the outward-facing cover. Between seconds 2 and 7 look at her unseen screen, make two or three short touchpad gestures behind the lid to organize experiment records, pause and nod in confirmation. Do not continuously type. From seconds 7 to 9 close and stow the computer and support entirely. From seconds 9 to 10 hold the exact original empty-handed front standing pose. Keep the face, both ears and shoes unobstructed. No desk, paper or extra object remains.',
}


if __name__=='__main__':
    from future_props_lab.desktop import desktop_client
    with production_lock():
        s=load();groups=json.loads((PACK/'action-groups.json').read_text())
        directions=json.loads((PACK/'action-directions.json').read_text());ops=[]
        for a in s['actions']:
            if a['id'] not in DIRECTIONS:continue
            assert a['status'] not in {'generating','approved'}
            new=DIRECTIONS[a['id']]
            if a['direction']!=new:
                a.setdefault('requirement_revisions',[]).append({'at':now(),'old_direction':a['direction'],
                    'new_direction':new,'reason':'User clarified laptop computer and physical orientation: camera sees the back lid while she operates it'})
                a['direction']=new
            a['prop_type']='laptop-computer'
            prompt=prompt_for(a,new,prepared_reference=True)
            (PACK/a['prompt_file']).write_text(prompt)
            directions[a['group']][groups[a['group']].index(a['name'])]=new
            ops.append({'entity':'node','action':'update','id':a['node_id'],'value':{
                'approved':False,'title':'电脑版 · '+a['name'],'generation_draft':{
                    'model_id':s['model_id'],'mode':'reference','duration':10,'ratio':'16:9',
                    'resolution':'768p','prompt':prompt,'reference_asset_ids':[s['reference_asset_id']]}}})
        (PACK/'action-directions.json').write_text(json.dumps(directions,ensure_ascii=False,indent=2)+'\n')
        save(s)
        with desktop_client() as c:
            canvas=c.visual.get_canvas(project_id=s['project_id'])
            result=c.visual.apply_canvas_operations(project_id=s['project_id'],body={
                'expected_revision':canvas.revision,'request_id':str(uuid4()),'operations':ops})
            verified=c.visual.get_canvas(project_id=s['project_id'])
            for aid in DIRECTIONS:
                a=next(a for a in s['actions'] if a['id']==aid)
                n=next(n for n in verified.nodes if n.id==a['node_id'])
                assert 'LAPTOP COMPUTER' in n.generation_draft.prompt
        record=json.loads((PACK/'quality/laptop-correction.json').read_text())
        record.update(status='ledger and FPL drafts synchronized; original task snapshots retained',actions=list(DIRECTIONS),
            canvas_revision=result.revision,applied_at=now(),new_model_calls=0)
        (PACK/'quality/laptop-correction.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
        print('Laptop correction applied to '+', '.join(DIRECTIONS)+'; generation calls unchanged')
