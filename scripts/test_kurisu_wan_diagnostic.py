import copy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import patch

import kurisu_library as lib
import kurisu_queue as queue
import kurisu_wan_diagnostic as wan


class Client:
    def __init__(self):
        self.generation=self;self.visual=self;self.files=self
        self.nodes=[{'id':'approved-action-node','kind':'video','title':'Existing approved action'}]
        self.revision=1;self.puts=0;self.created=0;self.tasks=[];self.raise_after_create=False
        self.assets=[NS(id='safe-image',media_kind='image'),NS(id='driver-video',media_kind='video')]
        self.cap=NS(supported_modes=['reference'],supports_prompt=False,supports_duration=False,
            supports_ratio=False,supports_seed=True,resolutions=['832x464'],reference_limits={'image':1,'video':1},
            reference_video_upload_configured=True,seed_minimum=1,seed_maximum=999999)
        self.downloads=[];self.fail_download=False;self.download_callback=None
    def unlocked(self):
        assert not lib.STATE.with_suffix('.lock').exists(),'SDK or download held the ledger lock'
    def generation_options(self):
        self.unlocked();return NS(models=[NS(id=wan.MODEL_ID,slug=wan.MODEL_SLUG,video_capabilities=self.cap)])
    def list_files(self,**kwargs):self.unlocked();return NS(items=self.assets)
    def get_canvas(self,**kwargs):
        self.unlocked();return NS(revision=self.revision,nodes=copy.deepcopy(self.nodes),edges=[],categories=[])
    def put_canvas(self,project_id,body):
        self.unlocked();assert body['expected_revision']==self.revision
        self.nodes=copy.deepcopy(body['nodes']);self.revision+=1;self.puts+=1
    def list_generation_tasks(self,**kwargs):
        self.unlocked();items=[t for t in self.tasks if not kwargs.get('canvas_node_id') or t.canvas_node_id==kwargs['canvas_node_id']]
        return NS(items=items,total=len(items))
    def create_generation_task(self,project_id,body):
        self.unlocked();assert body['expected_canvas_revision']==self.revision
        assert not {'prompt','duration','ratio'}&body.keys()
        self.created+=1;self.revision+=1
        task=NS(id='diagnostic-paid-'+str(self.created),status='pending',provider_task_id='original-provider',
            result_asset_id=None,error_message=None,can_retry_materialization=False,canvas_node_id=body['canvas_node_id'],
            request_payload=copy.deepcopy(body),created_at=lib.now())
        self.tasks.append(task)
        if self.raise_after_create:raise ConnectionError('response lost after paid creation')
        return task
    def get_generation_task(self,task_id):
        self.unlocked();return next(t for t in self.tasks if t.id==task_id)
    @contextmanager
    def download_file(self,asset_id):
        self.unlocked();self.downloads.append(asset_id)
        def save(path):
            Path(path).write_bytes(b'partial' if self.fail_download else b'original-diagnostic-bytes')
            if self.fail_download:
                self.fail_download=False;raise ConnectionError('download interrupted')
            if self.download_callback:self.download_callback()
        yield NS(save=save)


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.patches=[patch.object(lib,'PACK',self.root),patch.object(lib,'STATE',self.root/'library.json')]
        for p in self.patches:p.start()
        self.state={'actions':[{'id':'a001','name':'approved idle','group':'idle','status':'approved','node_id':'approved-action-node',
            'attempts':[],'file':'approved.webm','sha256':'untouched'}],
            'project_id':'project','model_id':'h3','reference_asset_id':'safe-image','canonical_reference_asset_id':'safe-image',
            'reference_sha256':'safe','excluded_models':[],
            'limits':{'total_calls':130,'repair_calls':26,'other_model_calls':4,'concurrent_tasks':6},
            'stage':'blocked_style_validation','production_hold':{'reason':'source quality'},
            'local_processing_hold':{'reason':'no old processing'}}
        lib.save(self.state);self.client=Client();self.did='wan-motion-pilot-01'
        (self.root/'safe.png').write_bytes(b'canonical-safe-image');(self.root/'driver.mp4').write_bytes(b'full-green-idle-driver')
        self.manifest=self.root/'manifest.json'
        self.manifest.write_text(json.dumps({'project_id':'project','model_id':wan.MODEL_ID,'model_slug':wan.MODEL_SLUG,
            'purpose':'Internal background/style motion transfer diagnostic, no animation slot',
            'ref_image_asset_id':'safe-image','ref_image_local_file':'safe.png','ref_image_sha256':wan.sha(self.root/'safe.png'),
            'driver_asset_id':'driver-video','driver_local_file':'driver.mp4','driver_sha256':wan.sha(self.root/'driver.mp4')}))
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def prepare(self):return wan.prepare(self.client,self.did,self.manifest)
    def authorize(self):
        s=lib.load();s['authorized_paid_pilot']={'id':'bounded-wan-trial','approved':True,'diagnostic_ids':[self.did],
            'model_ids':[wan.MODEL_ID],'calls_ceiling':lib.calls(s)+1};lib.save(s)
    def complete(self):
        self.client.tasks[-1].status='completed';self.client.tasks[-1].result_asset_id='original-result'

    def test_prepare_is_idempotent_independent_node_and_not_a_paid_attempt(self):
        before=copy.deepcopy(self.state['actions']);first=self.prepare();self.prepare()
        self.assertEqual(self.client.puts,1);self.assertEqual(self.client.created,0);self.assertEqual(lib.calls(lib.load()),0)
        self.assertEqual(lib.load()['actions'],before)
        self.assertEqual(self.client.nodes[0],{'id':'approved-action-node','kind':'video','title':'Existing approved action'})
        self.assertNotEqual(first['node_id'],'approved-action-node');self.assertFalse(first['counts_toward_106'])
        self.assertEqual(self.client.nodes[-1]['id'],first['node_id'])

    def test_new_diagnostic_id_and_prepared_submit_cannot_reuse_anatomy_withdrawn_driver(self):
        self.prepare();self.authorize()
        report=self.root/'anatomy.json'
        report.write_text(json.dumps({'action_id':'a001','classification':'unapproved_foreground_appendage',
            'withdraw_recommended':True,'raw_source_sha256':wan.sha(self.root/'driver.mp4')}))
        state=lib.load();state['actions'][0]['withdrawn_approvals']=[{
            'independent_review_file':'anatomy.json','independent_review_sha256':wan.sha(report)}];lib.save(state)
        before=copy.deepcopy(lib.load());puts=self.client.puts
        with self.assertRaisesRegex(ValueError,'anatomy-withdrawn'):
            wan.prepare(self.client,'new-diagnostic-id',self.manifest)
        with self.assertRaisesRegex(ValueError,'anatomy-withdrawn'):
            wan.submit(self.client,self.did)
        self.assertEqual(self.client.created,0);self.assertEqual(self.client.puts,puts)
        self.assertEqual(lib.load(),before);self.assertEqual(lib.calls(lib.load()),0)

    def test_qa_schema_anatomy_hold_blocks_new_diagnostic_before_canvas_or_paid_calls(self):
        report=self.root/'qa-anatomy.json'
        report.write_text(json.dumps({'action_id':'a001','recommendation':'WITHDRAW_DO_NOT_RELEASE',
            'source_sha256':wan.sha(self.root/'driver.mp4'),
            'defects':[{'severity':'hard','type':'unapproved_foreground_appendage'}]}))
        state=lib.load();state['actions'][0]['withdrawn_approvals']=[{
            'independent_review_file':'qa-anatomy.json','independent_review_sha256':wan.sha(report)}];lib.save(state)
        before=copy.deepcopy(lib.load())
        with self.assertRaisesRegex(ValueError,'anatomy-withdrawn'):
            wan.prepare(self.client,'new-qa-diagnostic-id',self.manifest)
        self.assertEqual(self.client.created,0);self.assertEqual(self.client.puts,0)
        self.assertEqual(lib.load(),before);self.assertEqual(lib.calls(lib.load()),0)

    def test_active_safe_derivative_is_valid_even_when_original_canonical_id_differs(self):
        s=lib.load();s['canonical_reference_asset_id']='original-unpadded-image';lib.save(s)
        self.prepare()
        self.assertEqual(lib.load()['prepared_diagnostics'][self.did]['inputs']['ref_image']['asset_id'],'safe-image')

    def test_submit_omits_unsupported_fields_and_diagnostic_does_not_qualify_or_repair(self):
        self.prepare();self.authorize();before=copy.deepcopy(lib.load()['actions'])
        self.assertTrue(wan.submit(self.client,self.did));self.assertFalse(wan.submit(self.client,self.did))
        s=lib.load();t=s['diagnostic_attempts'][0];body=self.client.tasks[0].request_payload
        self.assertFalse({'prompt','ratio','duration'}&body.keys())
        self.assertEqual(body['workflow_parameters'],{'seed':314159});self.assertEqual(body['resolution'],'832x464')
        self.assertEqual(body['reference_asset_ids'],['safe-image']);self.assertEqual(body['video_asset_ids'],['driver-video'])
        self.assertEqual(t['request_sha256'],wan.digest(json.loads((self.root/t['request_file']).read_text())))
        self.assertEqual(s['actions'],before);self.assertEqual(sum(a['status']=='approved' for a in s['actions']),1)
        self.assertEqual(lib.quota_counts(s),{'calls':1,'repairs':0,'other_model_calls':1})
        self.assertEqual(s['production_hold'],self.state['production_hold']);self.assertEqual(self.client.created,1)

    def test_standing_auth_alone_or_wrong_pilot_scope_cannot_submit(self):
        self.prepare()
        lib.record_standing_authorization(self.state,authorization_id='standing',user_quote='Continue to complete',
            user_date='2026-10-31',timezone='Asia/Shanghai',automation_id=106)
        # Preserve the prepared entry when storing authorization.
        s=lib.load();s.update(standing_authorization=self.state['standing_authorization'],quota_policy=self.state['quota_policy']);lib.save(s)
        self.assertFalse(wan.submit(self.client,self.did))
        self.authorize();s=lib.load();s['authorized_paid_pilot']['diagnostic_ids']=['different-id'];lib.save(s)
        self.assertFalse(wan.submit(self.client,self.did));self.assertEqual(self.client.created,0)
        self.assertFalse(lib.load().get('diagnostic_attempts'))

    def test_unknown_submit_reconciles_original_and_never_creates_twice(self):
        self.prepare();self.authorize();self.client.raise_after_create=True
        self.assertTrue(wan.submit(self.client,self.did));self.assertEqual(self.client.created,1)
        self.assertEqual(lib.load()['diagnostic_attempts'][0]['task_id'],'diagnostic-paid-1')
        wan.recover(self.client,self.did,download=False);self.assertFalse(wan.submit(self.client,self.did))
        self.assertEqual(self.client.created,1);self.assertEqual(lib.calls(lib.load()),1)
        self.assertNotIn('submission_blocker',lib.load())

    def test_unresolved_diagnostic_blocks_action_queue_and_cannot_resubmit(self):
        self.prepare();self.authorize();self.client.raise_after_create=True
        with patch.object(self.client,'list_generation_tasks',return_value=NS(items=[],total=0)):
            wan.submit(self.client,self.did)
        s=lib.load();self.assertIsNone(s['diagnostic_attempts'][0]['task_id']);self.assertIn('submission_blocker',s)
        self.assertTrue(queue.unresolved_submission(s));self.assertFalse(wan.submit(self.client,self.did))
        self.assertFalse(queue.submit_one(self.client));self.assertEqual(self.client.created,1)

    def test_source_recovery_reuses_task_asset_and_atomic_download_without_model_calls(self):
        self.prepare();self.authorize();wan.submit(self.client,self.did);self.complete();self.client.fail_download=True
        with self.assertRaises(ConnectionError):wan.recover(self.client,self.did)
        path=self.root/'source/diagnostics'/self.did/'original.mp4';self.assertFalse(path.exists())
        s=lib.load();s['diagnostic_attempts'][0]['next_poll_at']=0;lib.save(s)
        result=wan.recover(self.client,self.did);wan.recover(self.client,self.did)
        self.assertEqual(self.client.downloads,['original-result','original-result'])
        self.assertEqual(result['task_id'],'diagnostic-paid-1');self.assertEqual(result['source_sha256'],wan.sha(path))
        self.assertEqual(result['recovery_status'],'awaiting_independent_source_review')
        self.assertEqual(self.client.created,1);self.assertEqual(lib.quota_counts(lib.load())['repairs'],0)

    def test_preflight_capability_input_and_canvas_failures_never_count_paid(self):
        self.prepare();self.authorize();self.client.cap.supports_prompt=True
        with self.assertRaises(ValueError):wan.submit(self.client,self.did)
        self.assertEqual(lib.calls(lib.load()),0);self.client.cap.supports_prompt=False
        self.client.assets=self.client.assets[:1]
        with self.assertRaises(ValueError):wan.submit(self.client,self.did)
        self.assertEqual(lib.calls(lib.load()),0);self.client.assets.append(NS(id='driver-video',media_kind='video'))
        self.client.nodes=self.client.nodes[:1]
        with self.assertRaises(ValueError):wan.submit(self.client,self.did)
        self.assertEqual(lib.calls(lib.load()),0);self.assertEqual(self.client.created,0)

    def test_changed_local_driver_is_rejected_before_prepare_or_submission(self):
        (self.root/'driver.mp4').write_bytes(b'different-driver')
        with self.assertRaisesRegex(ValueError,'SHA changed'):self.prepare()
        self.assertEqual(self.client.puts,0);self.assertEqual(lib.calls(lib.load()),0)

    def test_changed_prepared_plan_during_preflight_fails_cas_without_reservation(self):
        self.prepare();self.authorize();original=self.client.get_canvas
        def read_and_change(**kwargs):
            s=lib.load();s['prepared_diagnostics'][self.did]['purpose']='changed concurrently';lib.save(s)
            return original(**kwargs)
        with patch.object(self.client,'get_canvas',side_effect=read_and_change):
            with self.assertRaisesRegex(RuntimeError,'changed during preflight'):wan.submit(self.client,self.did)
        self.assertEqual(lib.calls(lib.load()),0);self.assertEqual(self.client.created,0)

    def test_total_and_other_model_limits_include_diagnostic_reservations(self):
        self.prepare();self.authorize();s=lib.load();s['limits']['other_model_calls']=0;lib.save(s)
        self.assertFalse(wan.submit(self.client,self.did));self.assertEqual(lib.calls(lib.load()),0)
        s['limits']['other_model_calls']=4;s['limits']['total_calls']=0;lib.save(s)
        self.assertFalse(wan.submit(self.client,self.did));self.assertEqual(self.client.created,0)
        s['limits']['total_calls']=130;lib.save(s);wan.submit(self.client,self.did)
        self.assertEqual(lib.calls(lib.load()),1)
        self.assertEqual(queue.model_slots(lib.load()),1)

    def test_quota_ensure_counts_diagnostic_without_making_it_a_repair(self):
        self.prepare();self.authorize();wan.submit(self.client,self.did);s=lib.load()
        s['limits']['total_calls']=1;s['limits']['other_model_calls']=1
        lib.record_standing_authorization(s,authorization_id='standing',user_quote='Continue until all complete',
            user_date='2026-10-31',timezone='Asia/Shanghai',automation_id=106)
        event=lib.ensure_quota(s,request_id='next-diagnostic',reason='Next bounded independent diagnostic',
            calls_needed=1,other_model_calls_needed=1)
        self.assertEqual(event['delta']['total_calls'],1);self.assertEqual(event['delta']['other_model_calls'],1)
        self.assertEqual(event['actual_counts'],{'calls':1,'repairs':0,'other_model_calls':1})
        self.assertEqual(event['delta']['repair_calls'],0)

    def test_reconciliation_checks_dedicated_node_seed_and_inputs(self):
        self.prepare();self.authorize();wan.submit(self.client,self.did)
        t=lib.load()['diagnostic_attempts'][0];remote=self.client.tasks[0]
        self.assertTrue(wan.matches(remote,t))
        for key,value in [('canvas_node_id','approved-action-node'),('request_payload',None)]:
            wrong=copy.deepcopy(remote);setattr(wrong,key,value);self.assertFalse(wan.matches(wrong,t))
        for key,value in [('workflow_parameters',{'seed':42}),('video_asset_ids',['different']),('prompt','H3 style prompt')]:
            wrong=copy.deepcopy(remote);wrong.request_payload[key]=value;self.assertFalse(wan.matches(wrong,t))

    def test_stale_download_result_cannot_overwrite_new_reservation(self):
        self.prepare();self.authorize();wan.submit(self.client,self.did);self.complete()
        def replace_token():
            s=lib.load();s['diagnostic_attempts'][0]['reservation_token']='new-owner-token';lib.save(s)
        self.client.download_callback=replace_token;wan.recover(self.client,self.did)
        self.assertNotIn('source_file',lib.load()['diagnostic_attempts'][0])
        self.assertEqual(self.client.created,1)


if __name__=='__main__':unittest.main()
