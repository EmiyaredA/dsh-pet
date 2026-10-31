"""Two U24 references are identical bytes, immutable ordered inputs, not keyframes."""
import copy,hashlib
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import kurisu_library as lib
import kurisu_queue as queue
from test_kurisu_queue import action,remote,FramesClient
import test_kurisu_queue as fixtures
import test_kurisu_wan_production as wan_fixtures
from test_kurisu_reference_overrides import OverrideClient
import test_kurisu_reference_overrides as reference_fixtures

class DualClient(OverrideClient):
 def __init__(self):super().__init__();self.images['anchor-copy']=self.images['override-image']
 def generation_options(self):
  result=super().generation_options();model=copy.deepcopy(result.models[0]);model.id=queue.DUAL_REFERENCE_MODEL_ID;model.slug=queue.DUAL_REFERENCE_MODEL_SLUG;result.models.append(model);return result

class DualReferenceTests(unittest.TestCase):
 setUp=fixtures.QueueTests.setUp
 tearDown=fixtures.QueueTests.tearDown
 save=fixtures.QueueTests.save
 def dual(self):
  a=reference_fixtures.ReferenceOverrideTests.overridden(self);a.update(next_model_id=queue.DUAL_REFERENCE_MODEL_ID,next_reference_asset_ids=['override-image','anchor-copy'],next_prompt_file='dual-prompt.txt')
  text=lib.prompt_for(a,a['direction'],True).replace('subject_definitions:\n','subject_definitions:\n<Picture 2> is the exact identical composition and empty-handed baseline of <Picture 1>, depicting the same single human.\n',1);(self.pack/'dual-prompt.txt').write_text(text);return a
 def test_ordered_dual_payload_official_bytes_snapshot_and_global_reference_unchanged(self):
  a=self.dual();before=self.save([a]);client=DualClient();self.assertTrue(queue.submit_one(client));s=lib.load();t=s['actions'][0]['attempts'][0];p=client.tasks[0].request_payload
  self.assertEqual(p['reference_asset_ids'],['override-image','anchor-copy']);self.assertNotIn('first_frame_asset_id',p);self.assertNotIn('last_frame_asset_id',p)
  self.assertEqual(client.downloads,['override-image','anchor-copy']);self.assertEqual(t['reference_asset_ids'],p['reference_asset_ids']);self.assertEqual(t['reference_asset_sha256s'],[a['next_reference_sha256']]*2);self.assertEqual(s['reference_asset_id'],before['reference_asset_id']);self.assertEqual(t['strategy'],'u24_dual_identical_reference_v1')
 def test_invalid_or_ambiguous_dual_inputs_never_reserve(self):
  for refs in [None,[],['override-image'],['override-image']*2,['override-image',' x'],['override-image','a','b']]:
   with self.subTest(refs=refs):
    a=self.dual();a['next_reference_asset_ids']=refs;before=self.save([a]);client=DualClient()
    with self.assertRaises(ValueError):queue.submit_one(client)
    self.assertEqual(lib.load(),before);self.assertEqual(client.created,0)
  a=self.dual();a['next_reference_asset_id']='ambiguous-other';before=self.save([a]);client=DualClient()
  with self.assertRaisesRegex(ValueError,'conflict'):queue.submit_one(client)
  self.assertEqual(lib.load(),before);self.assertEqual(client.created,0)
 def test_missing_second_formal_asset_or_wrong_second_bytes_is_zero_create(self):
  for data in [None,b'wrong-second-bytes']:
   a=self.dual();before=self.save([a]);client=DualClient()
   if data is None:client.images.pop('anchor-copy')
   else:client.images['anchor-copy']=data
   with self.assertRaises(ValueError):queue.submit_one(client)
   self.assertEqual(lib.load(),before);self.assertEqual(client.created,0)
 def test_only_supported_u24_and_authored_two_picture_prompt(self):
  for mutation in ['wrong_slug','max_one','no_prompt','no_second_label']:
   a=self.dual();client=DualClient();options=client.generation_options()
   if mutation=='wrong_slug':options.models[-1].slug='another-workflow'
   elif mutation=='max_one':options.models[-1].video_capabilities.reference_limits={'image':1}
   elif mutation=='no_prompt':a.pop('next_prompt_file')
   else:(self.pack/a['next_prompt_file']).write_text(lib.prompt_for(a,a['direction'],True))
   before=self.save([a])
   with patch.object(client,'generation_options',return_value=options),self.assertRaises(ValueError):queue.submit_one(client)
   self.assertEqual(lib.load(),before);self.assertEqual(client.created,0)
 def test_unknown_submission_matches_exact_two_ordered_images_once(self):
  self.save([self.dual()]);client=DualClient();client.raise_after_create=True;queue.submit_one(client);queue.poll_originals(client);self.assertEqual(client.created,1);t=lib.load()['actions'][0]['attempts'][0];self.assertEqual(t['task_id'],'new1');p=client.tasks[0].request_payload
  self.assertTrue(queue.matches_reservation(remote('same',payload=p),t))
  for refs in [['override-image'],['anchor-copy','override-image'],['override-image','unrelated']]:self.assertFalse(queue.matches_reservation(remote('wrong',payload={**p,'reference_asset_ids':refs}),t))
 def test_unknown_different_second_reference_never_adopts_or_recreates(self):
  self.save([self.dual()]);client=DualClient();client.raise_after_create=True;create=client.create_generation_task
  def changed(*args,**kwargs):
   try:return create(*args,**kwargs)
   finally:client.tasks[-1].request_payload['reference_asset_ids']=['override-image','different-second']
  with patch.object(client,'create_generation_task',side_effect=changed):queue.submit_one(client)
  self.assertEqual(lib.load()['actions'][0]['status'],'submission_uncertain');self.assertFalse(queue.submit_one(client));self.assertEqual(client.created,1)
 def test_changed_second_reference_during_preflight_is_not_reserved(self):
  self.save([self.dual()]);client=DualClient();original=client.get_canvas
  def changed(**kwargs):
   s=lib.load();s['actions'][0]['next_reference_asset_ids'][1]='changed-after-preflight';lib.save(s);return original(**kwargs)
  with patch.object(client,'get_canvas',side_effect=changed),self.assertRaisesRegex(RuntimeError,'changed'):queue.submit_one(client)
  self.assertEqual(client.created,0);self.assertFalse(lib.load()['actions'][0]['attempts'])
 def test_worker_cannot_replace_either_reference_or_shared_sha_proof(self):
  self.save([self.dual()]);client=DualClient();queue.submit_one(client);s=lib.load();a=s['actions'][0];a['status']='awaiting_processing';a['attempts'][0]['result_asset_id']='paid-result';lib.save(s);job=queue.claim_local()
  for key,value in [('reference_asset_ids',['override-image','new']),('reference_asset_sha256s',['0'*64]*2)]:
   with self.subTest(key=key),self.assertRaisesRegex(ValueError,'immutable'):queue.commit_processing(job,{'attempt_patch':{key:value}})
 def test_frames_and_wan_do_not_adopt_extra_reference_anchor_fields(self):
  a=fixtures.QueueTests.frames_action(self);a['next_reference_asset_ids']=['bad'];s=self.save([a]);plan=queue.generation_plan(s,a,FramesClient().generation_options().models[-1]);self.assertNotIn('reference_asset_ids',plan['payload'])
  a=wan_fixtures.WanProductionTests.wan_action(self);a['next_reference_asset_ids']=['bad'];s=self.save([a]);plan=queue.generation_plan(s,a,wan_fixtures.WanClient().generation_options().models[-1]);self.assertEqual(plan['payload']['reference_asset_ids'],['ref'])
if __name__=='__main__':unittest.main()
