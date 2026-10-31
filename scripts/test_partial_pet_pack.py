"""Partial delivery must never silently ship withdrawn or altered media."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pet_pack_manifest import validate_pack


class PartialDeliveryTests(unittest.TestCase):
    def fixture(self,root):
        folder=root/'pet/kurisu-animation';folder.mkdir(parents=True)
        config={'animations':{'idle':['idle'],'turn':[],'drag':[],'clicks':[],
            'moves':{'actions':[]},'categories':[],'events':{}}}
        (root/'pet/kurisu-config.json').write_text(json.dumps(config))
        (folder/'idle.webm').write_bytes(b'accepted-video')
        (folder/'withdrawn.webm').write_bytes(b'bad-old-video')
        library={'actions':[{'id':'a001','name':'idle','status':'approved',
            'sha256':hashlib.sha256(b'accepted-video').hexdigest()},
            {'id':'a003','name':'withdrawn','status':'quality_withdrawn'}]}
        (root/'library.json').write_text(json.dumps(library))
        return config,library

    def test_partial_config_still_rejects_unapproved_or_modified_media(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);config,library=self.fixture(root)
            self.assertEqual(validate_pack(root,config,library,True),{'idle'})
            config['animations']['drag']=['withdrawn']
            with self.assertRaisesRegex(ValueError,'unapproved'):validate_pack(root,config,library,True)
            config['animations']['drag']=[]
            (root/'pet/kurisu-animation/idle.webm').write_bytes(b'modified')
            with self.assertRaisesRegex(ValueError,'Altered'):validate_pack(root,config,library,True)

    def test_partial_zip_excludes_stale_withdrawn_runtime_files_and_declares_gaps(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'pack';root.mkdir();self.fixture(root)
            evidence=root/'quality/source-reviews';evidence.mkdir(parents=True)
            (evidence/'a003-attempt-1.json').write_text('{"final_media_approved":false}')
            target=Path(temp)/'partial.zip'
            subprocess.run([sys.executable,str(Path(__file__).with_name('package_pet_pack.py')),
                '--pack',str(root),'--output',str(target),'--allow-partial'],check=True,capture_output=True)
            with zipfile.ZipFile(target) as archive:
                self.assertIn('pet/kurisu-animation/idle.webm',archive.namelist())
                self.assertNotIn('pet/kurisu-animation/withdrawn.webm',archive.namelist())
                self.assertIn('quality/source-reviews/a003-attempt-1.json',archive.namelist())
                delivery=json.loads(archive.read('DELIVERY.json'))
                self.assertTrue(delivery['partial']);self.assertEqual(delivery['missing_ids'],['a003'])
                self.assertEqual(delivery['missing_actions'][0]['name'],'withdrawn')
                self.assertFalse(delivery['formal_full_config_promoted'])

    def test_unconfigured_approved_media_cannot_be_missing_or_count_a_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);config,library=self.fixture(root)
            library['actions'].append({'id':'a004','name':'extra','status':'approved',
                'sha256':library['actions'][0]['sha256']})
            with self.assertRaisesRegex(ValueError,'Missing approved'):validate_pack(root,config,library,True)
            (root/'pet/kurisu-animation/extra.webm').write_bytes(b'accepted-video')
            with self.assertRaisesRegex(ValueError,'Duplicate'):validate_pack(root,config,library,True)

    def test_preview_only_static_asset_is_never_shipped_or_counted_as_an_animation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'pack';root.mkdir();_,library=self.fixture(root)
            preview=root/'previews/static-preview';preview.mkdir(parents=True)
            (preview/'static.webm').write_bytes(b'explicit-static-preview-only')
            library['preview_static_placeholder']={'approved':True,'file':'previews/static-preview/static.webm',
                'label':'静态定稿占位 · 不计106条动画','sha256':hashlib.sha256(b'explicit-static-preview-only').hexdigest()}
            (root/'library.json').write_text(json.dumps(library))
            target=Path(temp)/'partial.zip'
            subprocess.run([sys.executable,str(Path(__file__).with_name('package_pet_pack.py')),
                '--pack',str(root),'--output',str(target),'--allow-partial'],check=True,capture_output=True)
            with zipfile.ZipFile(target) as archive:
                self.assertNotIn('previews/static-preview/static.webm',archive.namelist())
                delivery=json.loads(archive.read('DELIVERY.json'))
                self.assertEqual(delivery['approved_animation_count'],1)
                self.assertEqual(delivery['configured_animation_count'],1)


if __name__=='__main__':unittest.main()
