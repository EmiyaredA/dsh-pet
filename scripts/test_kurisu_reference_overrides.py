from contextlib import contextmanager
import copy
import hashlib
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import kurisu_library as lib
import kurisu_queue as queue
from test_kurisu_queue import Client,FramesClient,action,remote
import test_kurisu_queue as fixtures
import test_kurisu_wan_production as wan_fixtures


class OverrideClient(Client):
    def __init__(self):
        super().__init__();self.files=self;self.images={'override-image':b'exact-transparent-safe-image'};self.downloads=[]
    def list_files(self,**kwargs):
        self.unlocked();return NS(items=[NS(id=aid,media_kind='image') for aid in self.images])
    @contextmanager
    def download_file(self,asset_id):
        self.unlocked();self.downloads.append(asset_id)
        yield NS(iter_bytes=lambda:iter([self.images[asset_id][:8],self.images[asset_id][8:]]))


class ReferenceOverrideTests(unittest.TestCase):
    setUp=fixtures.QueueTests.setUp
    tearDown=fixtures.QueueTests.tearDown
    save=fixtures.QueueTests.save
    def overridden(self):
        a=action(1);image=self.pack/'references/transparent.png';image.parent.mkdir(parents=True,exist_ok=True)
        image.write_bytes(b'exact-transparent-safe-image')
        a.update(next_reference_asset_id='override-image',next_reference_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                 next_reference_file='references/transparent.png')
        return a

    def test_override_and_explicit_historical_prompt_are_snapshotted_without_global_mutation(self):
        a=self.overridden();a['next_prompt_file']='prompts/historical.txt';prompt=self.pack/a['next_prompt_file'];prompt.parent.mkdir(exist_ok=True)
        text=lib.prompt_for(a,'Keep this exact historical gesture.',True);prompt.write_text(text)
        s=self.save([a,action(2)]);global_before=(s['reference_asset_id'],s['reference_sha256']);other_before=copy.deepcopy(s['actions'][1]);client=OverrideClient()
        queue.submit_one(client,skip_actions={'a002'})
        saved=lib.load();t=saved['actions'][0]['attempts'][0]
        self.assertEqual((saved['reference_asset_id'],saved['reference_sha256']),global_before)
        self.assertEqual(saved['actions'][1],other_before)
        self.assertEqual(client.tasks[0].request_payload['reference_asset_ids'],['override-image'])
        self.assertEqual(client.tasks[0].request_payload['prompt'],text)
        self.assertEqual(t['reference_asset_id'],'override-image');self.assertEqual(t['reference_sha256'],a['next_reference_sha256'])
        self.assertTrue(t['reference_override']);self.assertEqual(t['reference_file'],a['next_reference_file'])
        self.assertEqual(t['prompt_source_sha256'],hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual((self.pack/t['prompt_file']).read_text(),text)
        prompt.write_text('later edits must not alter immutable history')
        self.assertEqual((self.pack/t['prompt_file']).read_text(),text)
        self.assertEqual(client.downloads,['override-image'])

    def test_missing_formal_asset_or_official_bytes_mismatch_does_not_reserve(self):
        for images,expected in [({},'formal image asset'),({'override-image':b'wrong-remote-bytes'},'Official image bytes')]:
            with self.subTest(images=images):
                a=self.overridden();before=self.save([a]);client=OverrideClient();client.images=images
                with self.assertRaisesRegex(ValueError,expected):queue.submit_one(client)
                self.assertEqual(lib.load(),before);self.assertEqual(client.created,0)

    def test_incomplete_or_changed_local_reference_fails_before_reservation(self):
        for mutation in [dict(next_reference_asset_id=None),dict(next_reference_sha256=None),dict(next_reference_file=None),
                         dict(next_reference_sha256='incorrect'),dict(next_reference_file='../outside.png')]:
            with self.subTest(mutation=mutation):
                a=self.overridden();a.update(mutation);before=self.save([a]);client=OverrideClient()
                with self.assertRaises(ValueError):queue.submit_one(client)
                self.assertEqual(lib.load(),before);self.assertEqual(client.created,0)
        a=self.overridden();before=self.save([a]);(self.pack/a['next_reference_file']).write_bytes(b'changed-local-image');client=OverrideClient()
        with self.assertRaisesRegex(ValueError,'bytes changed'):queue.submit_one(client)
        self.assertEqual(lib.load(),before);self.assertEqual(client.created,0)

    def test_explicit_reference_prompt_requires_h3_six_sections(self):
        a=action(1);a['next_prompt_file']='bad-prompt.txt';(self.pack/'bad-prompt.txt').write_text('Only a summary, not six sections.')
        before=self.save([a]);client=Client()
        with self.assertRaisesRegex(ValueError,'six H3'):queue.submit_one(client)
        self.assertEqual(lib.load(),before);self.assertEqual(client.created,0)

    def test_unknown_submit_reconciles_the_actual_override_once(self):
        self.save([self.overridden()]);client=OverrideClient();client.raise_after_create=True
        queue.submit_one(client);queue.poll_originals(client)
        self.assertEqual(client.created,1);self.assertEqual(lib.load()['actions'][0]['attempts'][0]['task_id'],'new1')
        t=lib.load()['actions'][0]['attempts'][0];payload=copy.deepcopy(client.tasks[0].request_payload)
        self.assertTrue(queue.matches_reservation(remote('same',payload=payload),t))
        self.assertFalse(queue.matches_reservation(remote('wrong-image',payload={**payload,'reference_asset_ids':['ref']}),t))

    def test_unknown_response_with_different_image_never_false_matches_or_recreates(self):
        self.save([self.overridden()]);client=OverrideClient();client.raise_after_create=True;original=client.create_generation_task
        def wrong_remote(*args,**kwargs):
            try:return original(*args,**kwargs)
            finally:client.tasks[-1].request_payload['reference_asset_ids']=['different-image']
        with patch.object(client,'create_generation_task',side_effect=wrong_remote):queue.submit_one(client)
        s=lib.load();self.assertIsNone(s['actions'][0]['attempts'][0].get('task_id'))
        self.assertEqual(s['actions'][0]['status'],'submission_uncertain');self.assertIn('submission_blocker',s)
        self.assertFalse(queue.submit_one(client));self.assertEqual(client.created,1)

    def test_frames_and_wan_ignore_reference_override_and_keep_their_existing_inputs(self):
        frames=fixtures.QueueTests.frames_action(self);frames.update(next_reference_asset_id='do-not-use',next_reference_sha256='invalid',next_reference_file='missing.png')
        state=self.save([frames]);model=FramesClient().generation_options().models[-1]
        plan=queue.generation_plan(state,frames,model)
        self.assertEqual(plan['payload']['first_frame_asset_id'],'formal-first-asset')
        self.assertNotIn('reference_asset_ids',plan['payload'])
        wan=wan_fixtures.WanProductionTests.wan_action(self);wan.update(next_reference_asset_id='do-not-use',next_reference_sha256='invalid',next_reference_file='missing.png')
        state=self.save([wan]);model=wan_fixtures.WanClient().generation_options().models[-1]
        plan=queue.generation_plan(state,wan,model)
        self.assertEqual(plan['payload']['reference_asset_ids'],['ref'])
        self.assertEqual(plan['metadata']['reference_sha256'],'refhash')

    def test_worker_cannot_replace_the_reference_file_or_its_identity(self):
        self.save([self.overridden()]);client=OverrideClient();queue.submit_one(client)
        s=lib.load();s['actions'][0]['status']='awaiting_processing';s['actions'][0]['attempts'][0]['result_asset_id']='existing-result';lib.save(s)
        job=queue.claim_local()
        for key,value in [('reference_file','other.png'),('reference_asset_id','other'),('reference_sha256','wrong')]:
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'immutable'):
                queue.commit_processing(job,{'attempt_patch':{key:value}})


if __name__=='__main__':unittest.main()
