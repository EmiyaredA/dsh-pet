import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import kurisu_palette_anchor as anchors
import kurisu_green_worker as worker

class PaletteAnchorTests(unittest.TestCase):
    def write(self,pack,relative,data):
        p=pack/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data));return hashlib.sha256(p.read_bytes()).hexdigest()
    def fixture(self,folder):
        pack=Path(folder);original=pack/anchors.APPROVED_ORIGINAL_FILE;original.parent.mkdir(parents=True);original.write_bytes((Path(__file__).resolve().parents[1]/'pet-packs/kurisu'/anchors.APPROVED_ORIGINAL_FILE).read_bytes())
        asset_file='previews/static-preview/static.webm';asset=pack/asset_file;asset.parent.mkdir(parents=True);asset.write_bytes(b'pinned-static-bytes');sha=hashlib.sha256(asset.read_bytes()).hexdigest()
        technical={'asset_kind':'explicit_static_reference_preview_only','source_file':anchors.APPROVED_ORIGINAL_FILE,'source_reference_sha256':anchors.APPROVED_ORIGINAL_SHA256,'file':asset_file,'sha256':sha,'counts_as_106_animation':False,'deliverable_animation':False,'verification':{'width':640,'height':360,'fps':24,'duration':10,'decoded_frames':240,'all240_rgba_frames_identical':True,'alpha_min':0,'alpha_max':255,'audio_streams':0}}
        review={'asset_kind':'explicit_static_reference_preview_only','processing_clearance':'allow_static_preview_only','preview_allowed':True,'final_media_approved':False,'counts_toward_106':False,'file':asset_file,'media_sha256':sha,'source_file':anchors.APPROVED_ORIGINAL_FILE,'source_sha256':anchors.APPROVED_ORIGINAL_SHA256,'reviewer':'independent','reviewed_at':'2026-10-31','independent_technical_checks':{'frames':240,'unique_decoded_rgba_framemd5_count':1,'all240_decoded_rgba_frames_identical':True,'true_decoded_alpha':True,'alpha_min':0,'alpha_max':255,'all_rgba_exactly_matches_independently_recreated_filter':True}}
        d={'schema_version':1,'anchor_kind':'approved_original_static_palette_reference','purpose':'palette_reference_only','counts_toward_106':False,'final_animation_approved':False,'source_file':anchors.APPROVED_ORIGINAL_FILE,'source_sha256':anchors.APPROVED_ORIGINAL_SHA256,'asset_file':asset_file,'asset_sha256':sha,'reference_frame':0,'technical_report_file':'previews/static-preview/static.report.json','independent_review_file':'quality/final-reviews/static-preview.json'}
        d['technical_report_sha256']=self.write(pack,d['technical_report_file'],technical);d['independent_review_sha256']=self.write(pack,d['independent_review_file'],review)
        entry={'file':'quality/palette-anchors/static.json','sha256':self.write(pack,'quality/palette-anchors/static.json',d)}
        return pack,asset,entry,d,technical,review
    def resign(self,pack,entry,d):entry['sha256']=self.write(pack,entry['file'],d)
    def test_absent_descriptor_keeps_legacy_behavior_without_new_fallback(self):
        path,proof=anchors.select_palette_anchor(Path('/example/pack'))
        self.assertEqual(path,Path('/example/pack/pet/kurisu-animation/待机呼吸.webm'))
        self.assertEqual(proof['kind'],'legacy_canonical_idle')
    def test_valid_pinned_static_chain_selects_original_preview_not_idle(self):
        with tempfile.TemporaryDirectory() as f:
            pack,asset,e,d,_,_=self.fixture(f);path,proof=anchors.select_palette_anchor(pack,e)
            self.assertEqual(path,asset.resolve());self.assertFalse(proof['counts_toward_106']);self.assertFalse(proof['animation_approval']);self.assertTrue(proof['explicit_descriptor'])
    def test_bad_descriptor_hash_fails_closed_even_if_old_idle_exists(self):
        with tempfile.TemporaryDirectory() as f:
            pack,asset,e,d,_,_=self.fixture(f);old=pack/'pet/kurisu-animation/待机呼吸.webm';old.parent.mkdir(parents=True);old.write_bytes(b'old');e['sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'SHA256'):anchors.select_palette_anchor(pack,e)
    def test_wrong_source_identity_or_changed_original_bytes_rejected(self):
        with tempfile.TemporaryDirectory() as f:
            pack,asset,e,d,_,_=self.fixture(f);d['source_file']='references/unapproved.png';self.resign(pack,e,d)
            with self.assertRaisesRegex(ValueError,'approved original'):anchors.select_palette_anchor(pack,e)
            d['source_file']=anchors.APPROVED_ORIGINAL_FILE;self.resign(pack,e,d);(pack/anchors.APPROVED_ORIGINAL_FILE).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'bytes changed'):anchors.select_palette_anchor(pack,e)
    def test_wrong_asset_hash_rejected(self):
        with tempfile.TemporaryDirectory() as f:
            pack,asset,e,d,_,_=self.fixture(f);asset.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'asset SHA256'):anchors.select_palette_anchor(pack,e)
    def test_arbitrary_absolute_parent_and_outside_namespace_paths_rejected(self):
        for field,path in [('entry','/private/tmp/foreign.json'),('entry','quality/palette-anchors/../static.json'),('asset_file','pet/kurisu-animation/待机呼吸.webm'),('independent_review_file','source/static.json')]:
            with self.subTest(field=field,path=path),tempfile.TemporaryDirectory() as f:
                pack,asset,e,d,_,_=self.fixture(f)
                if field=='entry':e['file']=path
                else:d[field]=path;self.resign(pack,e,d)
                with self.assertRaises(ValueError):anchors.select_palette_anchor(pack,e)
    def test_symlink_asset_rejected_even_when_target_hash_matches(self):
        with tempfile.TemporaryDirectory() as f:
            pack,asset,e,d,_,_=self.fixture(f);target=pack/'other.webm';asset.replace(target);asset.symlink_to(target)
            with self.assertRaisesRegex(ValueError,'symlinks'):anchors.select_palette_anchor(pack,e)
    def test_report_hash_or_provenance_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as f:
            pack,asset,e,d,t,r=self.fixture(f);t['source_reference_sha256']='0'*64;d['technical_report_sha256']=self.write(pack,d['technical_report_file'],t);self.resign(pack,e,d)
            with self.assertRaisesRegex(ValueError,'provenance'):anchors.select_palette_anchor(pack,e)
    def test_incomplete_constant_alpha_proof_and_animation_approval_rejected(self):
        for field,value in [('true_decoded_alpha',False),('frames',239),('unique_decoded_rgba_framemd5_count',2),('all_rgba_exactly_matches_independently_recreated_filter',False)]:
            with self.subTest(field=field),tempfile.TemporaryDirectory() as f:
                pack,asset,e,d,t,r=self.fixture(f);r['independent_technical_checks'][field]=value;d['independent_review_sha256']=self.write(pack,d['independent_review_file'],r);self.resign(pack,e,d)
                with self.assertRaisesRegex(ValueError,'proof'):anchors.select_palette_anchor(pack,e)
        with tempfile.TemporaryDirectory() as f:
            pack,asset,e,d,t,r=self.fixture(f);d['counts_toward_106']=True;self.resign(pack,e,d)
            with self.assertRaisesRegex(ValueError,'animation approval'):anchors.select_palette_anchor(pack,e)
    def test_explicit_bad_descriptor_rejected_before_palette_fitting(self):
        with tempfile.TemporaryDirectory() as f,patch.object(worker,'PACK',Path(f)),patch.object(worker,'decode_palette_frames') as decode,patch.object(worker,'estimate_track') as fit:
            with self.assertRaises(ValueError):worker.green_candidate('source','output','work',palette_anchor_descriptor={})
            decode.assert_not_called();fit.assert_not_called()

if __name__=='__main__':unittest.main()
