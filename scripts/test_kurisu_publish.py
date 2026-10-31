"""Publishing must leave model scheduling unlocked during file transfers."""
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import kurisu_library as lib
import publish_kurisu_library as pub


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.pack=self.root/'pack';self.pack.mkdir()
        self.state=self.root/'state.json';self.lock=self.state.with_suffix('.lock')
        self.patches=[patch.object(lib,'STATE',self.state),patch.object(pub,'PACK',self.pack)]
        for p in self.patches:p.start();self.addCleanup(p.stop)
        (self.pack/'clip.webm').write_bytes(b'approved')
        self.action={'id':'a026','name':'clip','status':'approved','attempts':[{}],'file':'clip.webm',
            'sha256':hashlib.sha256(b'approved').hexdigest(),'node_id':'source','category_id':'daily'}
        lib.save({'project_id':'project','actions':[self.action]})
        self.uploads=0;self.assets=[];self.nodes=[NS(id='source',asset_id=None,approved=False,title='source')];self.revision=1
        self.during_upload=None;self.raise_after_upload=False;self.insert_initializes_unreviewed=False
        owner=self
        class Files:
            def list_files(self,**kw):
                owner.assertFalse(owner.lock.exists());return NS(items=owner.assets)
            def upload_file(self,body,files):
                owner.assertFalse(owner.lock.exists());owner.uploads+=1
                owner.assertEqual(files['upload'][1].read(),b'approved')
                asset=NS(id='asset',display_name=body['display_name']);owner.assets.append(asset)
                if owner.during_upload:owner.during_upload()
                if owner.raise_after_upload:raise OSError('response lost')
                return asset
        class Visual:
            def get_canvas(self,**kw):return NS(revision=owner.revision,nodes=owner.nodes)
            def apply_canvas_operations(self,**kw):
                owner.assertTrue(owner.lock.exists())
                body=kw['body'];owner.assertEqual(body['expected_revision'],owner.revision)
                for op in body['operations']:
                    if op['action']=='insert':
                        value=dict(op['value'])
                        if owner.insert_initializes_unreviewed:value['approved']=False
                        owner.nodes.append(NS(**value))
                    else:
                        node=next(n for n in owner.nodes if n.id==op['id'])
                        for k,v in op['value'].items():setattr(node,k,v)
                owner.revision+=1;return NS(revision=owner.revision)
        self.client=NS(files=Files(),visual=Visual())

    def test_upload_is_unlocked_but_canvas_and_metadata_are_serialized(self):
        pub.publish(self.client);pub.publish(self.client)
        self.assertEqual(self.uploads,1)
        a=lib.load()['actions'][0];self.assertEqual(a['delivery_asset_id'],'asset')
        self.assertTrue(any(n.id==a['delivery_node_id'] for n in self.nodes))

    def test_withdraw_during_upload_never_publishes_stale_approved_media(self):
        def withdraw():
            with lib.production_lock():
                s=lib.load();s['actions'][0]['status']='quality_withdrawn';lib.save(s)
        self.during_upload=withdraw;pub.publish(self.client)
        self.assertEqual(len(self.nodes),1)
        self.assertNotIn('delivery_asset_id',lib.load()['actions'][0])

    def test_unknown_upload_recovers_existing_asset_without_duplicate_transfer(self):
        self.raise_after_upload=True
        with self.assertRaises(OSError):pub.publish(self.client)
        self.raise_after_upload=False;pub.publish(self.client)
        self.assertEqual(self.uploads,1)
        self.assertEqual(lib.load()['actions'][0]['delivery_asset_id'],'asset')

    def test_unresolved_generation_reservation_defers_canvas_only(self):
        s=lib.load();s['actions'].append({'id':'a030','status':'generating','attempts':[{}]});lib.save(s)
        pub.publish(self.client)
        self.assertEqual(self.uploads,1);self.assertEqual(len(self.nodes),1)
        with lib.production_lock():
            s=lib.load();s['actions'][1]['attempts'][0]['task_id']='accepted';lib.save(s)
        pub.publish(self.client)
        self.assertEqual(self.uploads,1);self.assertEqual(len(self.nodes),2)

    def test_restored_same_delivery_becomes_approved_without_approving_repaired_source(self):
        s=lib.load();a=s['actions'][0]
        a.update(delivery_asset_id='asset',delivery_node_id='current-delivery',
                 media_revisions=[{'delivery_node_id':'old-delivery'}],
                 withdrawn_approvals=[{'delivery_node_id':'current-delivery'},
                                      {'delivery_node_id':'older-withdrawn'}],
                 human_approval={'source':'user','sha256':a['sha256']})
        lib.save(s)
        self.nodes.extend([NS(id='current-delivery',asset_id='asset',approved=False,title='已撤回'),
                           NS(id='old-delivery',asset_id='old',approved=True,title='old'),
                           NS(id='older-withdrawn',asset_id='older',approved=True,title='older')])
        self.nodes[0].approved=True
        pub.publish(self.client);pub.publish(self.client)
        current=next(n for n in self.nodes if n.id=='current-delivery')
        self.assertTrue(current.approved);self.assertEqual(current.asset_id,'asset')
        self.assertEqual(current.title,'透明交付 · clip')
        self.assertFalse(self.nodes[0].approved)
        self.assertFalse(next(n for n in self.nodes if n.id=='old-delivery').approved)
        self.assertFalse(next(n for n in self.nodes if n.id=='older-withdrawn').approved)
        self.assertEqual(self.uploads,0)

    def test_nonapproved_action_existing_delivery_is_never_restored(self):
        s=lib.load();s['actions'][0].update(status='quality_withdrawn',
            delivery_asset_id='asset',delivery_node_id='withdrawn')
        lib.save(s);self.nodes.append(NS(id='withdrawn',asset_id='asset',approved=False,title='已撤回'))
        pub.publish(self.client)
        self.assertFalse(self.nodes[-1].approved);self.assertEqual(self.uploads,0)

    def test_new_node_insert_review_default_is_explicitly_approved_and_verified(self):
        self.insert_initializes_unreviewed=True
        pub.publish(self.client)
        a=lib.load()['actions'][0]
        node=next(n for n in self.nodes if n.id==a['delivery_node_id'])
        self.assertTrue(node.approved);self.assertEqual(node.asset_id,'asset')
        self.assertEqual(self.uploads,1)


if __name__=='__main__':unittest.main()
