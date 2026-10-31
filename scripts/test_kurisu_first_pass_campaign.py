import copy,hashlib,json,os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import kurisu_library as lib
import kurisu_first_pass_campaign as campaign

BASE=(lib.PACK/'prompts/library/a032-framing80-blue-probe-02.txt').read_text()
REF=(lib.PACK/campaign.REF_FILE).read_bytes()
class Client:
    def __init__(self,callback=None):self.generation=self;self.callback=callback;self.created=0
    def generation_options(self):
        assert not lib.STATE.with_suffix('.lock').exists()
        if self.callback:self.callback()
        return NS(models=[NS(id=campaign.MODEL,slug='minimax_h3_zm_nono',video_capabilities=NS(
            supported_modes=['reference'],supports_prompt=True,duration_min=1,duration_max=15,
            resolution_ratios={'768p':['16:9']},reference_limits={'image':1},max_prompt_length=20000))])
    def create_generation_task(self,**kwargs):self.created+=1;raise AssertionError('Preparation must never call generation')

class FirstPassCampaignTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.pack=self.root/'pack'
        (self.pack/'prompts/library').mkdir(parents=True);(self.pack/'references').mkdir()
        (self.pack/'prompts/library/a032-framing80-blue-probe-02.txt').write_text(BASE)
        (self.pack/campaign.REF_FILE).write_bytes(REF)
        self.patches=[patch.object(lib,'ROOT',self.root),patch.object(lib,'PACK',self.pack),patch.object(lib,'STATE',self.pack/'library.json'),
            patch.object(campaign,'RUN_DIR',self.root/'controller'),patch.object(campaign,'LOG',self.root/'controller/log.jsonl')]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def state(self,submitted=6):
        actions=[]
        # Historical77calls with27repairs, including9other-modelcalls, are never reset.
        for n in range(50):
            ts=[{'task_id':f'legacy-{n}-0','model_id':'other' if n<9 else campaign.MODEL}]
            if n<27:ts.append({'task_id':f'legacy-{n}-1','model_id':campaign.MODEL})
            actions.append({'id':f'legacy{n}','name':'legacy','group':'legacy','status':'rejected','attempts':ts})
        for n,aid in enumerate(campaign.IDS):
            t={'task_id':f'original-{aid}','model_id':campaign.MODEL,'reference_asset_id':campaign.REFERENCE,
                'reference_sha256':campaign.REF_SHA,'chroma_background':'blue','status':'completed','source_file':f'source/{aid}.mp4'}
            actions.append({'id':aid,'name':aid,'group':'研究与玩耍','node_id':'node-'+aid,'direction':'Inspect a tiny gray object and nod.',
                'status':'processing_failed' if n<submitted else 'planned','attempts':[t] if n<submitted else [],'reused':False})
        limits={'total_calls':130,'repair_calls':27,'attempts_per_action':2,'concurrent_tasks':6,'local_processing':2,'other_model_calls':9}
        s={'model_id':campaign.MODEL,'project_id':'project','reference_asset_id':'old-global','reference_sha256':'old-sha','excluded_models':[],
            'actions':actions,'limits':limits,'production_hold':{'reason':'quality'},'local_processing_hold':{'reason':'no matting'},
            'stage':'first_pass_coverage_priority_new_actions','standing_authorization':{'id':'standing','approved':True,'source':'user',
                'user_quote':'Continue all106 and extend recorded budget as needed','scope':['total_calls'],'target_animation_count':106},
            'quota_policy':{'approved_limits':copy.deepcopy(limits),'approved_action_attempt_limits':{}},
            'first_pass_campaign':{'id':campaign.CAMPAIGN,'approved':True,'owner_agent':'/root/production_queue','action_ids':list(campaign.IDS),
                'max_new_paid_calls':55,'calls_at_authorization':77,'calls_ceiling':132,'model_id':campaign.MODEL,'reference_asset_id':campaign.REFERENCE,
                'reference_sha256':campaign.REF_SHA,'first_generation_only':True,'source_recovery_only':True,'semantic_processing_authorized':False},
            'authorized_paid_pilot':{'id':'h3-framing80-blue-firstpass-03','approved':True,'closed':True,'action_ids':list(campaign.IDS[:6]),'first_pass_only':True,'source_recovery_only':True}}
        lib.save(s);return s
    def test_finite_authority_and_existing_attempt_conditions_fail_closed(self):
        s=self.state();before=copy.deepcopy(s);campaign.guard(s)
        for change in [{'approved':False},{'calls_ceiling':133},{'action_ids':list(campaign.IDS)+['a105']},{'semantic_processing_authorized':True}]:
            t=copy.deepcopy(s);t['first_pass_campaign'].update(change)
            with self.assertRaises(PermissionError):campaign.guard(t)
        a=next(a for a in s['actions'] if a['id']=='a037');a['attempts'].append(copy.deepcopy(a['attempts'][0]))
        with self.assertRaises(PermissionError):campaign.guard(s)
        self.assertEqual(lib.load(),before)
    def test_next_wave_only_six_new_actions_no_paid_call_and_restart_idempotence(self):
        before=self.state();client=Client();pilot=campaign.activate_next_wave(client);saved=lib.load()
        self.assertEqual(pilot['action_ids'],[f'a{i:03d}' for i in range(43,49)])
        self.assertEqual(pilot['calls_ceiling'],89);self.assertEqual(lib.calls(saved),83);self.assertEqual(client.created,0)
        self.assertEqual(campaign.activate_next_wave(client),pilot)
        self.assertEqual(lib.load()['first_pass_campaign']['waves'],saved['first_pass_campaign']['waves'])
        self.assertEqual(saved['actions'][:50],before['actions'][:50])
        self.assertEqual(saved['production_hold'],before['production_hold']);self.assertEqual(saved['local_processing_hold'],before['local_processing_hold'])
    def test_action_change_during_preflight_does_not_activate_or_overwrite(self):
        self.state()
        def race():
            s=lib.load();next(a for a in s['actions'] if a['id']=='a043')['direction']='changed by root';lib.save(s)
        with self.assertRaisesRegex(RuntimeError,'changed before'):campaign.activate_next_wave(Client(race))
        s=lib.load();self.assertEqual(s['authorized_paid_pilot']['id'],'h3-framing80-blue-firstpass-03');self.assertEqual(lib.calls(s),83)
        self.assertEqual(next(a for a in s['actions'] if a['id']=='a043')['direction'],'changed by root')
    def test_total_extension_only_to132_preserves_counts_and_repair_model_limits(self):
        self.state(submitted=54);pilot=campaign.activate_next_wave(Client());s=lib.load()
        self.assertEqual(pilot['action_ids'],['a091']);self.assertEqual(lib.calls(s),131)
        self.assertEqual(s['limits']['total_calls'],132);self.assertEqual(s['limits']['repair_calls'],27);self.assertEqual(s['limits']['other_model_calls'],9)
        event=s['quota_adjustments'][-1];self.assertEqual(event['delta']['total_calls'],2);self.assertEqual(event['delta']['repair_calls'],0);self.assertEqual(event['delta']['other_model_calls'],0);self.assertEqual(event['delta']['actions'],{})
    def test_seasonal_prompts_are_read_only_handoff_bound_and_never_duplicated(self):
        self.state();aid='a069';self.assertIsNone(campaign.seasonal_prompt(aid))
        prompt=self.pack/f'prompts/library/{aid}-firstpass-seasonal-v1.txt';prompt.write_text(BASE)
        handoff=self.pack/campaign.SEASONAL_HANDOFF;handoff.parent.mkdir(parents=True)
        handoff.write_text(json.dumps({'actions':[{'action_id':aid,'prompt_file':str(prompt.relative_to(self.pack)),'sha256':campaign.sha(prompt)}]}))
        result=campaign.seasonal_prompt(aid);self.assertEqual(result['sha256'],campaign.sha(prompt));original=prompt.read_bytes()
        prompt.write_text('tampered')
        with self.assertRaises(PermissionError):campaign.seasonal_prompt(aid)
        prompt.write_bytes(original)
        self.assertEqual(campaign.seasonal_prompt(aid)['file'],str(prompt.relative_to(self.pack)))
    def test_known_original_recovery_claims_only_campaign_blue_and_global_two_slots(self):
        s=self.state();a=next(a for a in s['actions'] if a['id']=='a037');a['status']='awaiting_processing';a['attempts'][0]['result_asset_id']='known'
        lib.save(s);job=campaign.claim_source();self.assertEqual(job['action']['id'],'a037');self.assertEqual(lib.calls(lib.load()),83)
        s=lib.load();other=next(a for a in s['actions'] if a['id']=='a038');other['attempts'][0]['processing_claim']={'pid':os.getpid(),'token':'another'};lib.save(s)
        self.assertIsNone(campaign.claim_source());self.assertEqual(lib.calls(lib.load()),83)
    def test_same_positive_blue_recipe_has_no_unrequested_companion_on_other_actions(self):
        a={'id':'a050','name':'cube','direction':'Turn ivory, red, blue, yellow squares. No green faces.'}
        text=campaign.prompt_text(a);self.assertIn('RGB(0,0,255)',text);self.assertNotIn('small companion',text);self.assertNotIn('green',text.lower());self.assertIn('amber',text)
