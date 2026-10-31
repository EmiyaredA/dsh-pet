import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import kurisu_library as lib
import kurisu_queue as queue
from kurisu_iteration_policy import correction_usage,iteration_decision,submission_priority
from kurisu_spec_revisions import has_source,sample_batch_decision,current_spec_attempts
from kurisu_quotas import counts
from revise_kurisu_programmer_research import revise,SPEC,IDS,SAMPLES
from test_kurisu_queue import Client

STAMP='2026-10-31T06:00:00+00:00'
def fixture():
 actions=[{'id':aid,'name':'old-'+aid,'group':'研究与玩耍','direction':'old-dir-'+aid,'node_id':'node-'+aid,'status':'processing_failed','reused':False,'attempts':[{'task_id':'old-'+aid,'source_file':'source/'+aid+'.mp4','status':'completed'}],'batch':3,'queue_order':i} for i,aid in enumerate(IDS)]
 actions.append({'id':'a011','name':'outside','group':'移动','node_id':'outside','status':'awaiting_local_repair','attempts':[{'task_id':'outside'}],'human_source_selection':{'version':2}})
 limits={'total_calls':132,'repair_calls':27,'attempts_per_action':2,'other_model_calls':39,'concurrent_tasks':6,'local_processing':2}
 return {'actions':actions,'limits':limits,'model_id':'default','reference_asset_id':'ref','reference_sha256':'refhash','project_id':'project','excluded_models':[],'stage':'producing','standing_authorization':{'id':'human-standing','approved':True,'source':'user','user_quote':'continue','target_animation_count':106,'scope':['total_calls','repair_calls','named_action_attempts','other_model_calls']},'quota_policy':{'approved_limits':copy.deepcopy(limits),'approved_action_attempt_limits':{}},'iteration_policy':{'id':'one-correction','source':'user','effective_at':'2026-10-31T02:26:09+00:00','max_corrective_rounds_per_action':1,'prioritize_unattempted_actions':True}}
def pilot(s):s['authorized_paid_pilot']={'approved':True,'closed':False,'spec_revision_id':SPEC,'spec_samples_only':True,'action_ids':SAMPLES,'calls_ceiling':100,'max_new_paid_calls':2}
def aget(s,aid='a034'):return next(a for a in s['actions'] if a['id']==aid)
def new_attempt(a):a['attempts'].append({'task_id':'current-'+str(len(a['attempts'])),'spec_revision_id':SPEC,'spec_action_name':a['name'],'status':'completed','source_file':'new/current.mp4'})
class SpecTests(unittest.TestCase):
 def setUp(self):self.s=fixture();self.before=copy.deepcopy(self.s);revise(self.s,STAMP)
 def test_revision_preserves_real_counts_history_outside_and_old_content_identity(self):
  self.assertEqual(counts(self.s),counts(self.before));self.assertEqual(aget(self.s,'a011'),aget(self.before,'a011'))
  for aid in IDS:
   a=aget(self.s,aid);old=aget(self.before,aid);self.assertEqual(a['status'],'planned');self.assertEqual(a['attempts'][0]['task_id'],old['attempts'][0]['task_id']);self.assertEqual(a['attempts'][0]['spec_action_name'],old['name']);self.assertNotEqual(a['attempts'][0]['spec_revision_id'],SPEC);self.assertFalse(has_source(a));self.assertTrue(has_source(a,False));self.assertEqual(a['spec_revision_history'][0]['previous_action_metadata']['direction'],old['direction'])
  self.assertEqual(aget(self.s,'a032')['direction'],aget(self.before,'a032')['direction']);self.assertEqual(aget(self.s,'a035')['direction'],aget(self.before,'a035')['direction'])
 def test_exactly27_names_brackets_caps_and_named_authorizations(self):
  self.assertEqual(aget(self.s)['name'],'报错拍键盘（半身）');self.assertEqual(aget(self.s,'a047')['name'],'插拔网线（腰部以上入画）');self.assertEqual(len(self.s['iteration_policy']['named_action_exceptions']),27)
  for aid in IDS:self.assertGreaterEqual(self.s['action_attempt_limits'][aid],len(aget(self.before,aid)['attempts'])+2)
  before=copy.deepcopy(self.s);self.assertEqual(revise(self.s,STAMP),[]);self.assertEqual(self.s,before)
 def test_global_clear_hold_still_blocks25_and_unactivated_samples(self):
  for aid in IDS:self.assertFalse(iteration_decision(self.s,aget(self.s,aid))['allowed'])
  pilot(self.s)
  for aid in IDS:self.assertEqual(iteration_decision(self.s,aget(self.s,aid))['allowed'],aid in SAMPLES)
  self.s['authorized_paid_pilot']['spec_revision_id']='old';self.assertFalse(iteration_decision(self.s,aget(self.s))['allowed'])
 def test_finite_sample_firstpass_permission_cannot_be_reused_for_paid_correction(self):
  pilot(self.s);self.s['authorized_paid_pilot']['spec_first_pass_only']=True;a=aget(self.s);self.assertTrue(iteration_decision(self.s,a)['allowed']);new_attempt(a);self.assertFalse(iteration_decision(self.s,a)['allowed'])
 def test_new_first_plus_only_one_shared_paid_or_local_correction(self):
  pilot(self.s);a=aget(self.s);self.assertTrue(iteration_decision(self.s,a)['allowed']);self.assertFalse(iteration_decision(self.s,a,'local_repair')['allowed']);new_attempt(a);self.assertTrue(iteration_decision(self.s,a,'local_repair')['allowed']);self.assertTrue(iteration_decision(self.s,a)['allowed']);a['attempts'][-1]['local_reprocess_requests']=[{'reason':'one new-spec localrepair'}];self.assertFalse(iteration_decision(self.s,a)['allowed']);self.assertFalse(iteration_decision(self.s,a,'local_repair')['allowed'])
  a['attempts'][-1].pop('local_reprocess_requests');new_attempt(a);self.assertFalse(iteration_decision(self.s,a)['allowed'])
 def test_prior_repair_usage_is_not_reset_but_named_new_spec_gets_two_slots(self):
  s=fixture();a=aget(s);a['attempts'].append({'task_id':'old-repair'});a['attempts'][0]['local_edit']={'type':'old-repair'};old_usage=correction_usage(a);old_counts=counts(s);revise(s,STAMP);pilot(s);self.assertEqual(correction_usage(a),old_usage);self.assertEqual(counts(s),old_counts);self.assertTrue(iteration_decision(s,a)['allowed']);new_attempt(a);self.assertTrue(iteration_decision(s,a)['allowed']);new_attempt(a);self.assertFalse(iteration_decision(s,a)['allowed'])
 def test_history_deletion_is_fail_closed_and_old_source_not_processing_ready(self):
  pilot(self.s);a=aget(self.s);self.assertFalse(iteration_decision(self.s,a,'initial_processing')['allowed']);self.assertTrue(iteration_decision(self.s,a,'recover_original')['allowed']);a['status']='awaiting_processing';a['attempts'][0]['result_asset_id']='old-result';self.assertFalse(queue.local_ready(a));a['attempts'].clear();self.assertFalse(iteration_decision(self.s,a)['allowed'])
 def test_both_current_sample_user_assistant_sha_approvals_needed(self):
  gate=self.s['spec_batch_gates'][SPEC];gate['batch_released']=True
  for aid in SAMPLES:
   a=aget(self.s,aid);a.update(status='approved',sha256='a'*64)
   gate['sample_decisions'][aid]={role:{'approved':True,'source':role,'spec_revision_id':SPEC,'sha256':'a'*64,'user_quote':'accept','review_file':'quality/current.json'} for role in ['user','assistant']}
  self.assertFalse(sample_batch_decision(self.s,aget(self.s,'a030'))['allowed'])
  for aid in SAMPLES:new_attempt(aget(self.s,aid))
  self.assertTrue(sample_batch_decision(self.s,aget(self.s,'a030'))['allowed']);gate['sample_decisions']['a052']['user']['sha256']='b'*64;self.assertFalse(sample_batch_decision(self.s,aget(self.s,'a030'))['allowed'])
 def test_priority_new_spec_and_coverage_keep_historical_vs_current(self):
  self.assertEqual(submission_priority(self.s,aget(self.s)),0)
  with tempfile.TemporaryDirectory() as tmp,patch.object(lib,'STATE',Path(tmp)/'state.json'):
   lib.save(self.s);saved=lib.load();self.assertEqual(saved['production_coverage']['source_action_count'],27);self.assertEqual(saved['production_coverage']['current_spec_source_action_count'],0);new_attempt(aget(self.s));lib.save(self.s);self.assertEqual(lib.load()['production_coverage']['current_spec_source_action_count'],1)
 def test_queue_freezes_spec_id_name_and_never_sends_new_vendor_fields(self):
  pilot(self.s);a=aget(self.s)
  with tempfile.TemporaryDirectory() as tmp,patch.object(lib,'PACK',Path(tmp)),patch.object(lib,'STATE',Path(tmp)/'library.json'):
   lib.save(self.s);c=Client();queue.submit_one(c,skip_actions={x['id'] for x in self.s['actions'] if x['id']!='a034'});t=aget(lib.load())['attempts'][-1];self.assertEqual(t['spec_revision_id'],SPEC);self.assertEqual(t['spec_action_name'],a['name']);self.assertNotIn('spec_revision_id',c.tasks[0].request_payload);self.assertIn('spec_revision_id',queue.PROTECTED);self.assertIn('spec_action_name',queue.PROTECTED)

 def test_unknown_new_spec_submission_recovers_same_task_and_old_attempt_remains(self):
  pilot(self.s);old=copy.deepcopy(aget(self.s)['attempts'][0])
  with tempfile.TemporaryDirectory() as tmp,patch.object(lib,'PACK',Path(tmp)),patch.object(lib,'STATE',Path(tmp)/'library.json'):
   lib.save(self.s);c=Client();c.raise_after_create=True;skip={x['id'] for x in self.s['actions'] if x['id']!='a034'};queue.submit_one(c,skip_actions=skip);queue.poll_originals(c,skip_actions=skip);queue.poll_originals(c,skip_actions=skip);a=aget(lib.load());self.assertEqual(c.created,1);self.assertEqual(a['attempts'][0],old);self.assertEqual(len(a['attempts']),2);self.assertEqual(a['attempts'][-1]['task_id'],'new1');self.assertEqual(a['attempts'][-1]['spec_revision_id'],SPEC);self.assertFalse(queue.submit_one(c,skip_actions=skip))
 def test_worker_cannot_change_current_spec_identity(self):
  pilot(self.s)
  with tempfile.TemporaryDirectory() as tmp,patch.object(lib,'PACK',Path(tmp)),patch.object(lib,'STATE',Path(tmp)/'library.json'):
   lib.save(self.s);c=Client();skip={x['id'] for x in self.s['actions'] if x['id']!='a034'};queue.submit_one(c,skip_actions=skip);s=lib.load();a=aget(s);a['status']='awaiting_processing';a['attempts'][-1]['result_asset_id']='current-source';lib.save(s);job=queue.claim_local(skip_actions=skip)
   for key,value in [('spec_revision_id','old'),('spec_action_name','old-name')]:
    with self.subTest(key=key),self.assertRaisesRegex(ValueError,'immutable'):queue.commit_processing(job,{'attempt_patch':{key:value}})

if __name__=='__main__':unittest.main()
