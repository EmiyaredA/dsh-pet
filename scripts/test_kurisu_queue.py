import copy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import time
import unittest
from unittest.mock import patch
import kurisu_library as lib
import kurisu_queue as queue


def action(i,status='planned',attempt=None,batch=1):
    return {'id':f'a{i:03d}','name':f'action{i}','group':'日常小动作','status':status,'reused':False,'node_id':f'node{i}',
        'direction':'Nod softly and relax.','batch':batch,'queue_order':i,'attempts':[attempt] if attempt else []}


def remote(tid,status='pending',node=None,payload=None):
    return NS(id=tid,status=status,canvas_node_id=node,provider_task_id='provider-'+tid,
        result_asset_id='asset-'+tid if status=='completed' else None,error_message=None,can_retry_materialization=False,
        request_payload=payload or {},created_at=lib.now())


class Client:
    def __init__(self):self.tasks=[];self.created=0;self.events=[];self.revision=1;self.generation=self;self.visual=self;self.raise_after_create=False
    def unlocked(self):assert not lib.STATE.with_suffix('.lock').exists(),'Network or local processing under ledger lock'
    def generation_options(self):
        self.unlocked();cap=NS(supported_modes=['reference'],supports_prompt=True,reference_limits={'image':9},duration_min=1,duration_max=15,resolution_ratios={'768p':['16:9']})
        return NS(models=[NS(id='default',slug='minimax_h3_zm_nono',video_capabilities=cap)])
    def list_generation_tasks(self,**kwargs):
        self.unlocked();items=[t for t in self.tasks if not kwargs.get('canvas_node_id') or t.canvas_node_id==kwargs['canvas_node_id']];return NS(items=items,total=len(items))
    def get_generation_task(self,task_id):self.unlocked();return next(t for t in self.tasks if t.id==task_id)
    def retry_materialization(self,task_id):
        self.unlocked();t=self.get_generation_task(task_id);t.status='pending';return t
    def get_canvas(self,**kwargs):
        self.unlocked();return NS(revision=self.revision,nodes=[{'id':a['node_id'],'kind':'video','asset_id':None} for a in lib.load()['actions']])
    def create_generation_task(self,project_id,body):
        self.unlocked();assert body['expected_canvas_revision']==self.revision
        self.created+=1;self.revision+=1;self.events.append('submit');t=remote('new'+str(self.created),node=body['canvas_node_id'],payload=body);self.tasks.append(t)
        if self.raise_after_create:raise ConnectionError('interrupted response')
        return t


class FramesClient(Client):
    def __init__(self):
        super().__init__();self.files=self;self.frame_images=['formal-first-asset','formal-last-asset']
    def list_files(self,**kwargs):
        self.unlocked();return NS(items=[NS(id=aid,media_kind='image') for aid in self.frame_images])
    def generation_options(self):
        options=super().generation_options()
        cap=copy.deepcopy(options.models[0].video_capabilities);cap.supported_modes=['frames'];cap.reference_limits={}
        options.models.append(NS(id=queue.FRAMES_MODEL_ID,slug=queue.FRAMES_MODEL_SLUG,video_capabilities=cap))
        return options


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.pack=Path(self.temp.name);self.patches=[patch.object(lib,'PACK',self.pack),patch.object(lib,'STATE',self.pack/'library.json')]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def save(self,actions,**extra):
        s={'limits':{'total_calls':130,'repair_calls':26,'concurrent_tasks':6,'local_processing':2,'other_model_calls':4},'actions':actions,
            'model_id':'default','project_id':'project','reference_asset_id':'ref','reference_sha256':'refhash','excluded_models':[],'stage':'producing',**extra};lib.save(s);return s
    @contextmanager
    def factory(self):yield self.client
    def frames_action(self):
        a=action(1);a.update(next_generation_mode='frames',next_model_id=queue.FRAMES_MODEL_ID,
            next_first_frame_asset_id='formal-first-asset',next_last_frame_asset_id='formal-last-asset',
            next_first_frame_sha256='same-safe-pixels',next_last_frame_sha256='same-safe-pixels',
            next_prompt_file='prompts/authored-fl2va.txt')
        path=self.pack/a['next_prompt_file'];path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot 1) aligns with the 10.00-second mark of the target video.\n\n'
            'integrated_multimodal_description: [Shot 1] Static shot, green backdrop, nod gently and return to the same standing pose.\n\n'
            'overall_soundscape: Silent.\n\nnon_diegetic_music: None.\n')
        return a
    def test_frames_uses_authored_prompt_and_only_distinct_first_last_payload(self):
        a=self.frames_action();self.save([a]);self.client=FramesClient()
        authored=(self.pack/a['next_prompt_file']).read_text()
        self.assertTrue(queue.submit_one(self.client));payload=self.client.tasks[0].request_payload
        self.assertEqual(payload['mode'],'frames');self.assertEqual(payload['model_id'],queue.FRAMES_MODEL_ID)
        self.assertEqual(payload['first_frame_asset_id'],'formal-first-asset')
        self.assertEqual(payload['last_frame_asset_id'],'formal-last-asset')
        self.assertNotIn('reference_asset_ids',payload)
        self.assertEqual(payload['prompt'],authored)
        self.assertEqual((payload['duration'],payload['ratio'],payload['resolution']),(10,'16:9','768p'))
        t=lib.load()['actions'][0]['attempts'][0]
        self.assertEqual(t['generation_mode'],'frames')
        self.assertEqual(t['first_frame_asset_id'],payload['first_frame_asset_id'])
        self.assertEqual(t['last_frame_asset_id'],payload['last_frame_asset_id'])
        self.assertEqual(t['first_frame_sha256'],t['last_frame_sha256'])
        self.assertNotIn('reference_asset_id',t)
        self.assertEqual(t['prompt_sha256'],hashlib.sha256(authored.encode()).hexdigest())
        self.assertEqual((self.pack/t['prompt_file']).read_text(),authored)
        (self.pack/a['next_prompt_file']).write_text('later edit must not alter the historical attempt')
        self.assertEqual((self.pack/t['prompt_file']).read_text(),authored)
    def test_default_reference_request_and_prompt_remain_unchanged(self):
        a=action(1);self.save([a]);self.client=Client();queue.submit_one(self.client)
        payload=self.client.tasks[0].request_payload
        self.assertEqual(payload['mode'],'reference');self.assertEqual(payload['reference_asset_ids'],['ref'])
        self.assertNotIn('first_frame_asset_id',payload);self.assertNotIn('last_frame_asset_id',payload)
        self.assertEqual(payload['prompt'],lib.prompt_for(a,a['direction'],True))
        self.assertEqual(lib.load()['actions'][0]['attempts'][0]['generation_mode'],'reference')
    def test_frames_missing_assets_same_asset_or_missing_prompt_never_reserves(self):
        for mutation in [dict(next_first_frame_asset_id=None),dict(next_last_frame_asset_id=None),
                         dict(next_last_frame_asset_id='formal-first-asset'),dict(next_prompt_file=None),
                         dict(next_prompt_file='../escape.txt'),dict(next_prompt_file='missing.txt'),
                         dict(next_generation_mode='text')]:
            with self.subTest(mutation=mutation):
                a=self.frames_action();a.update(mutation);before=self.save([a]);self.client=FramesClient()
                with self.assertRaises((ValueError,FileNotFoundError)):queue.submit_one(self.client)
                self.assertEqual(lib.load(),before);self.assertEqual(self.client.created,0)
                self.assertEqual(lib.calls(lib.load()),0)
    def test_frames_unsupported_capability_or_model_never_reserves(self):
        a=self.frames_action();before=self.save([a]);self.client=Client()
        with self.assertRaisesRegex(ValueError,'unavailable'):queue.submit_one(self.client)
        self.assertEqual(lib.load(),before);self.assertEqual(self.client.created,0)
        self.client=FramesClient();options=self.client.generation_options();options.models[-1].video_capabilities.supported_modes=['reference']
        with patch.object(self.client,'generation_options',return_value=options),self.assertRaisesRegex(ValueError,'frames workflow'):
            queue.submit_one(self.client)
        self.assertEqual(lib.load(),before);self.assertEqual(self.client.created,0)
        a['next_model_id']='default';before=self.save([a]);options.models[0].video_capabilities.supported_modes=['reference','frames']
        with patch.object(self.client,'generation_options',return_value=options),self.assertRaisesRegex(ValueError,'not been approved'):
            queue.submit_one(self.client)
        self.assertEqual(lib.load(),before);self.assertEqual(self.client.created,0)
    def test_frames_unregistered_assets_fail_preflight_without_a_paid_attempt(self):
        a=self.frames_action();before=self.save([a]);self.client=FramesClient();self.client.frame_images=['formal-first-asset']
        with self.assertRaisesRegex(ValueError,'formal image assets'):queue.submit_one(self.client)
        self.assertEqual(lib.load(),before);self.assertEqual(self.client.created,0)
    def test_frames_wrong_h3_prompt_format_and_canvas_read_failure_are_preflight(self):
        a=self.frames_action();before=self.save([a]);self.client=FramesClient()
        (self.pack/a['next_prompt_file']).write_text('subject_definitions: a reference-mode prompt is not FL2VA')
        with self.assertRaisesRegex(ValueError,'base-en'):queue.submit_one(self.client)
        self.assertEqual(lib.load(),before);self.assertEqual(self.client.created,0)
        a=self.frames_action();before=self.save([a])
        with patch.object(self.client,'get_canvas',side_effect=ConnectionError('read-only preflight interrupted')):
            with self.assertRaises(ConnectionError):queue.submit_one(self.client)
        self.assertEqual(lib.load(),before);self.assertEqual(self.client.created,0)
        self.assertFalse((self.pack/'prompts/library/a001-attempt-1.txt').exists())
    def test_frames_inputs_changed_during_preflight_do_not_reserve(self):
        a=self.frames_action();self.save([a]);self.client=FramesClient()
        def read_canvas(**kwargs):
            s=lib.load();s['actions'][0]['next_last_frame_asset_id']='another-asset';lib.save(s)
            return NS(revision=1,nodes=[{'id':'node1','kind':'video','asset_id':None}])
        with patch.object(self.client,'get_canvas',side_effect=read_canvas),self.assertRaisesRegex(RuntimeError,'changed during preflight'):
            queue.submit_one(self.client)
        self.assertEqual(lib.calls(lib.load()),0);self.assertEqual(self.client.created,0)
    def test_frames_unknown_submission_reconciles_original_without_second_call(self):
        self.save([self.frames_action()]);self.client=FramesClient();self.client.raise_after_create=True
        self.assertTrue(queue.submit_one(self.client))
        self.assertEqual(self.client.created,1);self.assertEqual(lib.calls(lib.load()),1)
        self.assertEqual(lib.load()['actions'][0]['attempts'][0]['task_id'],'new1')
        queue.poll_originals(self.client)
        self.assertFalse(queue.submit_one(self.client));self.assertEqual(self.client.created,1)
    def test_frames_reconciliation_requires_exact_mode_and_first_last_order(self):
        self.save([self.frames_action()]);self.client=FramesClient();queue.submit_one(self.client)
        t=lib.load()['actions'][0]['attempts'][0];payload=copy.deepcopy(self.client.tasks[0].request_payload)
        self.assertTrue(queue.matches_reservation(remote('correct',payload=payload),t))
        for mutation in [dict(mode='reference'),dict(first_frame_asset_id='wrong'),dict(last_frame_asset_id='wrong'),
                         dict(first_frame_asset_id=payload['last_frame_asset_id'],last_frame_asset_id=payload['first_frame_asset_id']),
                         dict(reference_asset_ids=['unapproved-reference'])]:
            with self.subTest(mutation=mutation):
                self.assertFalse(queue.matches_reservation(remote('wrong',payload={**payload,**mutation}),t))
        missing=remote('missing');missing.request_payload=None
        self.assertFalse(queue.matches_reservation(missing,t))
    def test_media_worker_cannot_rewrite_frames_conditions(self):
        a=self.frames_action();self.save([a]);self.client=FramesClient();queue.submit_one(self.client)
        s=lib.load();s['actions'][0]['status']='awaiting_processing';s['actions'][0]['attempts'][0]['result_asset_id']='paid-result';lib.save(s)
        job=queue.claim_local()
        with self.assertRaisesRegex(ValueError,'immutable'):
            queue.commit_processing(job,{'attempt_patch':{'first_frame_asset_id':'wrong'}})
        self.assertEqual(lib.load()['actions'][0]['attempts'][0]['first_frame_asset_id'],'formal-first-asset')
    def test_exact_six_active_cap_counts_local_reservations_and_external_tasks(self):
        self.client=Client();self.save([action(i) for i in range(1,10)])
        for _ in range(10):queue.submit_one(self.client)
        self.assertEqual(self.client.created,6);self.assertEqual(lib.calls(lib.load()),6)
        self.assertFalse(queue.submit_one(self.client));self.assertEqual(queue.model_slots(lib.load(),self.client.tasks),6)
    def test_completed_slot_refills_before_local_processing_and_processing_is_unlocked(self):
        t={'task_id':'old','status':'processing'};a=action(1,'generating',t);self.save([a,action(2)]);self.client=Client();self.client.tasks=[remote('old','completed','node1')]
        def processor(client,a,t,index,token):
            client.unlocked();client.events.append('process');return {'attempt_patch':{'source_file':'raw.mp4'},'action_status':'awaiting_source_review','hard_defect':False}
        runner=queue.QueueRunner(self.factory,processor)
        try:runner.cycle(self.client);runner.close()
        finally:runner.executor.shutdown(wait=True)
        self.assertEqual(self.client.events[:2],['submit','process']);self.assertEqual(lib.load()['actions'][0]['status'],'awaiting_source_review')
    def test_two_local_claims_shared_across_runners(self):
        self.save([action(i,'awaiting_processing',{'task_id':str(i),'result_asset_id':'asset','status':'completed'}) for i in range(1,5)])
        self.assertIsNotNone(queue.claim_local());self.assertIsNotNone(queue.claim_local());self.assertIsNone(queue.claim_local())
    def test_restart_reclaims_dead_owner_but_never_restarts_model(self):
        a=action(1,'local_processing',{'task_id':'paid','result_asset_id':'asset','status':'completed','processing_claim':{'token':'old','pid':99999999,'started_at':'old'}});self.save([a]);self.client=Client()
        with patch.object(queue,'alive',return_value=False):job=queue.claim_local()
        self.assertIsNotNone(job);self.assertNotEqual(job['claim_token'],'old');self.assertEqual(lib.calls(lib.load()),1);self.assertEqual(self.client.created,0)
    def test_live_claim_is_not_reclaimed_by_elapsed_time(self):
        a=action(1,'local_processing',{'task_id':'paid','result_asset_id':'asset','processing_claim':{'token':'old','pid':123,'started_at':'2000-01-01'}});self.save([a])
        with patch.object(queue,'alive',return_value=True):self.assertIsNone(queue.claim_local())
    def test_stale_attempt_or_claim_never_overwrites_newer_ledger(self):
        self.save([action(1,'awaiting_processing',{'task_id':'paid','result_asset_id':'asset','status':'completed'})]);job=queue.claim_local()
        s=lib.load();s['actions'][0]['attempts'].append({'task_id':'newer'});s['actions'][0]['status']='generating';s['unrelated']='keep';lib.save(s)
        self.assertFalse(queue.commit_processing(job,{'attempt_patch':{'candidate_file':'old.webm'},'action_status':'awaiting_review'}))
        self.assertEqual(lib.load()['actions'][0]['attempts'][-1],{'task_id':'newer'});self.assertEqual(lib.load()['unrelated'],'keep')
    def test_fresh_commit_preserves_unrelated_root_writes(self):
        self.save([action(1,'awaiting_processing',{'task_id':'paid','result_asset_id':'asset','status':'completed'})]);job=queue.claim_local();s=lib.load();s['unrelated']='root';lib.save(s)
        self.assertTrue(queue.commit_processing(job,{'attempt_patch':{'contact':'contact.png'},'action_status':'awaiting_source_review'}));self.assertEqual(lib.load()['unrelated'],'root')
    def test_unknown_submission_reconciles_existing_task_without_second_create(self):
        self.save([action(1)]);self.client=Client();self.client.raise_after_create=True
        self.assertTrue(queue.submit_one(self.client));self.assertEqual(self.client.created,1)
        self.assertEqual(lib.load()['actions'][0]['attempts'][0]['task_id'],'new1')
        queue.poll_originals(self.client);self.assertEqual(self.client.created,1);self.assertEqual(lib.calls(lib.load()),1)
    def test_unknown_submission_with_no_remote_match_blocks_new_paid_calls(self):
        a=action(1,'generating',{'status':'submission_started','previous_task_ids':[],'started_at':lib.now(),'normalized_prompt_sha256':'hash','model_id':'default'});self.save([a,action(2)]);self.client=Client()
        queue.poll_originals(self.client);self.assertIn('submission_blocker',lib.load());self.assertFalse(queue.submit_one(self.client));self.assertEqual(self.client.created,0)
    def test_hold_allows_poll_and_local_recovery_but_no_paid_submission(self):
        self.save([action(1,'generating',{'task_id':'paid','status':'processing'}),action(2)],production_hold={'reason':'quality'});self.client=Client();self.client.tasks=[remote('paid','completed','node1')]
        queue.poll_originals(self.client);self.assertEqual(lib.load()['actions'][0]['status'],'awaiting_processing');self.assertFalse(queue.submit_one(self.client));self.assertEqual(self.client.created,0)
    def test_bounded_explicit_pilot_is_only_hold_exception(self):
        s=self.save([action(1),action(2)],production_hold={'reason':'quality'},authorized_paid_pilot={'approved':True,'action_ids':['a002'],'calls_ceiling':1});self.client=Client()
        self.assertTrue(queue.submit_one(self.client));self.assertEqual(lib.load()['actions'][1]['attempts'][0]['task_id'],'new1');self.assertFalse(queue.submit_one(self.client))
    def test_two_distinct_hard_defects_in_batch_hold_new_calls_and_never_retry(self):
        self.save([action(i,'awaiting_processing',{'task_id':str(i),'result_asset_id':'asset','status':'completed','release_epoch':'trial'}) for i in [1,2]]+[action(3)])
        for _ in range(2):
            job=queue.claim_local();queue.commit_processing(job,{'attempt_patch':{'source_quality':{'processing_clearance':'reject'}},'action_status':'processing_failed','hard_defect':True,'defect_kind':'foreground_lighting'})
        self.assertIn('production_hold',lib.load());self.assertEqual(lib.calls(lib.load()),2);self.client=Client();self.assertFalse(queue.submit_one(self.client))
    def test_different_defect_families_do_not_trigger_repeated_lighting_stop(self):
        self.save([action(i,'awaiting_processing',{'task_id':str(i),'result_asset_id':'asset','release_epoch':'trial'}) for i in [1,2]])
        for kind in ['background','foreground_lighting']:
            job=queue.claim_local();queue.commit_processing(job,{'attempt_patch':{},'action_status':'processing_failed','hard_defect':True,'defect_kind':kind})
        self.assertNotIn('production_hold',lib.load())
    def test_prop_and_anatomy_failures_reject_without_being_lighting_stop(self):
        self.save([action(i,'awaiting_processing',{'task_id':str(i),'result_asset_id':'asset','release_epoch':'trial'}) for i in [1,2]])
        for kind in ['prop_occlusion','anatomy']:
            job=queue.claim_local();queue.commit_processing(job,{'attempt_patch':{},'action_status':'processing_failed','hard_defect':True,'defect_kind':kind})
        self.assertNotIn('production_hold',lib.load())
        self.assertTrue(all(a['status']=='processing_failed' for a in lib.load()['actions']))

    def test_pending_source_review_only_rechecks_changed_report(self):
        self.save([action(1,'awaiting_source_review',{'task_id':'paid','result_asset_id':'asset','status':'completed'})]);a=lib.load()['actions'][0];self.assertFalse(queue.local_ready(a))
        p=self.pack/'quality/source-reviews/a001-attempt-1.json';p.parent.mkdir(parents=True);p.write_text('{}');self.assertTrue(queue.local_ready(a));stat=p.stat();a['attempts'][0]['source_review_fingerprint']=f'{stat.st_mtime_ns}:{stat.st_size}';self.assertFalse(queue.local_ready(a));p.write_text('{"changed":true}');self.assertTrue(queue.local_ready(a))
    def test_global_and_repair_caps_count_reserved_attempts(self):
        a=action(1);s=self.save([a]);s['limits']['total_calls']=0;lib.save(s);self.client=Client();self.assertFalse(queue.submit_one(self.client))
        s['limits']['total_calls']=130;s['limits']['repair_calls']=0;a['attempts']=[{'task_id':'prior'}];lib.save(s);self.assertFalse(queue.submit_one(self.client))
    def test_interrupted_local_download_retries_original_asset_without_model_call(self):
        self.save([action(1,'awaiting_processing',{'task_id':'original','result_asset_id':'same-asset','status':'completed'})]);self.client=Client();seen=[]
        def processor(client,a,t,index,token):
            seen.append((t['task_id'],t['result_asset_id']))
            if len(seen)==1:raise ConnectionError('interrupted download')
            return {'attempt_patch':{'source_file':'same.mp4'},'action_status':'awaiting_source_review','hard_defect':False}
        runner=queue.QueueRunner(self.factory,processor)
        runner.cycle(self.client,submit=False);runner.close()
        s=lib.load();self.assertEqual(s['actions'][0]['status'],'awaiting_processing');s['actions'][0]['attempts'][0]['local_retry_after']=0;lib.save(s)
        runner=queue.QueueRunner(self.factory,processor);runner.cycle(self.client,submit=False);runner.close()
        self.assertEqual(seen,[('original','same-asset')]*2);self.assertEqual(self.client.created,0);self.assertEqual(lib.calls(lib.load()),1)
    def test_http_transient_statuses_and_transport_timeouts_backoff_but_cv_errors_do_not(self):
        for status in [408,429,500,503]:
            e=Exception();e.response=NS(status_code=status);self.assertTrue(queue.transient_local(e))
        for name in ['WriteTimeout','ConnectTimeout','PoolTimeout','ReadError','WriteError']:
            self.assertTrue(queue.transient_local(type(name,(Exception,),{})()))
        self.assertFalse(queue.transient_local(ValueError('invalid palette bounds')))
    def test_new_pipeline_cannot_approve_audio_background_or_alpha_failures(self):
        good={'width':640,'height':360,'fps':24,'frames':240,'audio_streams':0,'all_frames_have_alpha':True,'background_clear':True}
        for patch_value in [{'audio_streams':1},{'all_frames_have_alpha':False},{'background_clear':False}]:
            t={'task_id':'original','candidate_file':'candidate.webm','processing_claim_history':[{}],
               'source_background':{'passed':True},'source_sha256':'source','source_quality':{'processing_clearance':'allow_mild_color_and_green_key','source_sha256':'source'},'report':{'verification':{**good,**patch_value}}}
            a=action(1,'awaiting_review',t);s=self.save([a])
            with self.assertRaises(AssertionError):lib.review(s,a['id'],'pass','invalid result')
            self.assertNotEqual(lib.load()['actions'][0]['status'],'approved')
    def test_source_clearance_for_another_hash_cannot_approve_candidate(self):
        t={'task_id':'original','candidate_file':'candidate.webm','processing_claim_history':[{}],
            'source_background':{'passed':True},'source_sha256':'current','source_quality':{'processing_clearance':'allow_mild_color_and_green_key','source_sha256':'old'}}
        a=action(1,'awaiting_review',t);s=self.save([a])
        with self.assertRaisesRegex(AssertionError,'hash'):lib.review(s,a['id'],'pass','stale clearance')

    def test_explicit_new_recipe_reprocess_archives_candidate_and_preserves_call_count(self):
        raw=self.pack/'raw.mp4';raw.write_bytes(b'original-source');digest=hashlib.sha256(raw.read_bytes()).hexdigest()
        t={'task_id':'paid','result_asset_id':'asset','source_file':'raw.mp4','source_sha256':digest,
           'candidate_file':'old.webm','candidate_sha256':'oldhash','report':{'old':True},'worker_version':'v1'}
        self.save([action(1,'awaiting_review',t)])
        with patch.object(queue,'load_source_review',return_value={'processing_clearance':queue.ALLOW,'source_sha256':digest}):
            queue.request_local('a001','New canonical palette recipe','v2')
        s=lib.load();current=s['actions'][0]['attempts'][0]
        self.assertEqual(lib.calls(s),1);self.assertEqual(s['actions'][0]['status'],'awaiting_processing')
        self.assertNotIn('candidate_file',current);self.assertNotIn('report',current);self.assertEqual(current['requested_worker_version'],'v2')
        h=self.pack/current['local_reprocess_requests'][0]['history_file'];self.assertEqual(json.loads(h.read_text())['processing_metadata']['candidate_file'],'old.webm')
    def test_local_reprocess_cannot_override_rejected_source_or_changed_bytes(self):
        raw=self.pack/'raw.mp4';raw.write_bytes(b'changed');t={'task_id':'paid','result_asset_id':'asset','source_file':'raw.mp4','source_sha256':'old'}
        self.save([action(1,'processing_failed',t)])
        with self.assertRaisesRegex(ValueError,'bytes'):queue.request_local('a001','retry','v2')
        t['source_sha256']=hashlib.sha256(raw.read_bytes()).hexdigest();self.save([action(1,'processing_failed',t)])
        with patch.object(queue,'load_source_review',return_value={'processing_clearance':'reject'}):
            with self.assertRaisesRegex(ValueError,'ALLOW'):queue.request_local('a001','override reject','v2')
        self.assertEqual(lib.calls(lib.load()),1)
    def test_old_worker_recipe_cannot_commit_new_candidate(self):
        a=action(1,'awaiting_processing',{'task_id':'paid','result_asset_id':'asset','requested_worker_version':'v2'});self.save([a]);job=queue.claim_local()
        with self.assertRaisesRegex(ValueError,'recipe'):
            queue.commit_processing(job,{'attempt_patch':{'candidate_file':'old.webm','worker_version':'v1'},'action_status':'awaiting_review'})
        self.assertNotIn('candidate_file',lib.load()['actions'][0]['attempts'][0])
    def test_worker_response_identity_mismatch_is_rejected(self):
        self.save([action(1,'awaiting_processing',{'task_id':'paid','result_asset_id':'asset'})]);job=queue.claim_local()
        with self.assertRaisesRegex(ValueError,'identity'):
            queue.commit_processing(job,{'task_id':'other','attempt_patch':{},'action_status':'awaiting_review'})
    def test_transient_model_preflight_does_not_reserve_paid_call_or_block_local_work(self):
        self.save([action(1,'awaiting_processing',{'task_id':'paid','result_asset_id':'asset','status':'completed'}),action(2)]);self.client=Client()
        self.client.list_generation_tasks=lambda **kwargs:(_ for _ in ()).throw(ConnectionError('offline'))
        def processor(*args):return {'attempt_patch':{},'action_status':'awaiting_source_review'}
        r=queue.QueueRunner(self.factory,processor);r.cycle(self.client);r.close()
        s=lib.load();self.assertEqual(lib.calls(s),1);self.assertEqual(s['actions'][0]['status'],'awaiting_source_review');self.assertEqual(s['submission_preflight_failures'],1)

    def test_move_mode_and_old_holds_change_only_after_explicit_final_pass(self):
        folder=self.pack/'pet/kurisu-animation';folder.mkdir(parents=True);(self.pack/'previews/library').mkdir(parents=True)
        t={'task_id':'paid','candidate_file':'candidate.webm'};a=action(1,'awaiting_review',t);a.update(group='移动',motion_mode='continuous-left-profile',quality_hold={'reason':'old'},automatic_playback_hold={'reason':'old'})
        s=self.save([a]);lib.review(s,a['id'],'reject','source rejected')
        self.assertEqual(a['motion_mode'],'continuous-left-profile');self.assertIn('quality_hold',a)
        a['status']='awaiting_review';self.save([a]);prepared={}
        for kind in ['media','report','poster']:
            path=self.pack/('prepared-'+kind);path.write_bytes(b'fixture');prepared[kind]=str(path)
        prepared.update(sha256='newsha',alpha_contact='proof.png')
        lib.review(s,a['id'],'pass','new full front-left-front source passed','front-left-front',prepared)
        self.assertEqual(a['motion_mode'],'front-left-front');self.assertNotIn('quality_hold',a);self.assertNotIn('automatic_playback_hold',a);self.assertEqual(len(a['resolved_quality_holds']),2)
    def test_cli_review_prepares_media_outside_lock_then_commits(self):
        (self.pack/'pet/kurisu-animation').mkdir(parents=True);(self.pack/'previews/library').mkdir(parents=True)
        source=self.pack/'candidate.webm';source.write_bytes(b'candidate');source.with_suffix('.report.json').write_text('{}')
        a=action(1,'awaiting_review',{'task_id':'paid','candidate_file':'candidate.webm'});self.save([a])
        def contact(a,t,path):
            self.assertFalse(lib.STATE.with_suffix('.lock').exists());t['alpha_contact']='proof.png'
        def render(command,**kwargs):
            self.assertFalse(lib.STATE.with_suffix('.lock').exists());Path(command[-1]).write_bytes(b'poster')
        with patch.object(lib,'ROOT',self.pack),patch.object(lib,'write_alpha_contact',side_effect=contact),patch('subprocess.run',side_effect=render):
            queue.review_media('a001','pass','explicit reviewed candidate')
        self.assertEqual(lib.load()['actions'][0]['status'],'approved')
    def test_final_local_hold_stops_claims_and_explicit_recalibration(self):
        self.save([action(1,'awaiting_processing',{'task_id':'paid','result_asset_id':'asset'})],local_processing_hold={'reason':'final'})
        self.assertIsNone(queue.claim_local())
        with self.assertRaisesRegex(RuntimeError,'explicitly held'):queue.request_local('a001','unapproved calibration','v4')
        self.assertEqual(lib.calls(lib.load()),1)

    def test_final_style_stop_and_closed_pilot_never_allow_paid_submission(self):
        a=action(1);s=self.save([a],stage='blocked_style_validation',production_hold={'reason':'final'},authorized_paid_pilot={'approved':True,'action_ids':['a001'],'calls_ceiling':130})
        self.assertFalse(queue.paid_allowed(s,a))
        s['stage']='producing';s['authorized_paid_pilot']['closed']=True;self.assertFalse(queue.paid_allowed(s,a))

    def test_legacy_global_caps_cannot_drift_without_an_audited_extension(self):
        s={'limits':{'total_calls':999,'repair_calls':999},'actions':[{'attempts':[{}]} for _ in range(130)]}
        self.assertFalse(lib.can_submit(s,{'attempts':[]}))
        s['actions']=[{'attempts':[{},{}]} for _ in range(26)]
        self.assertFalse(lib.can_submit(s,{'attempts':[{}]}))

    def test_protected_metadata_rejected_and_does_not_change_paid_identity(self):
        self.save([action(1,'awaiting_processing',{'task_id':'paid','result_asset_id':'asset','status':'completed'})]);job=queue.claim_local()
        with self.assertRaises(ValueError):queue.commit_processing(job,{'attempt_patch':{'task_id':'other'},'action_status':'awaiting_review'})
        self.assertEqual(lib.load()['actions'][0]['attempts'][0]['task_id'],'paid')


if __name__=='__main__':unittest.main()
