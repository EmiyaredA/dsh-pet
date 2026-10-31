"""Bounded palette-anchor selection, never animation approval or media mutation.

New processing may explicitly pin an approved-original static descriptor. Legacy
absence keeps the previous idle-file behavior solely for compatibility.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re

APPROVED_ORIGINAL_FILE='references/kurisu-front.png'
APPROVED_ORIGINAL_SHA256='78e84345c8c876360c628310498484c3146e4da5ceae314b3b87e9de8f4c4725'
DESCRIPTOR_NAMESPACE='quality/palette-anchors'
STATIC_NAMESPACE='previews/static-preview'
REVIEW_NAMESPACE='quality/final-reviews'


def _sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value):
    if not isinstance(value,str) or not re.fullmatch(r'[0-9a-f]{64}',value):
        raise ValueError('Palette anchor requires an exact lowercase SHA256')
    return value


def _path(pack,relative,namespace,suffix):
    if not isinstance(relative,str) or not relative or relative!=relative.strip() or '\\' in relative:
        raise ValueError('Invalid palette anchor relative path')
    rel=Path(relative)
    if rel.is_absolute() or any(p in {'.','..'} for p in rel.parts):
        raise ValueError('Palette anchor path must remain inside its fixed namespace')
    prefix=Path(namespace).parts
    if rel.parts[:len(prefix)]!=prefix or len(rel.parts)!=len(prefix)+1 or not relative.endswith(suffix):
        raise ValueError('Palette anchor path is outside its fixed namespace')
    base=Path(pack).resolve();candidate=base
    for part in rel.parts:
        candidate=candidate/part
        if candidate.is_symlink():raise ValueError('Palette anchor symlinks are not allowed')
    try:resolved=candidate.resolve(strict=True)
    except FileNotFoundError as exc:raise ValueError('Declared palette anchor path is missing') from exc
    if not resolved.is_relative_to(base) or not resolved.is_file():
        raise ValueError('Declared palette anchor is not a regular pack file')
    return resolved


def _bound_json(pack,relative,expected,namespace):
    path=_path(pack,relative,namespace,'.json')
    if _sha(path)!=_digest(expected):raise ValueError('Palette anchor JSON SHA256 mismatch')
    try:data=json.loads(path.read_text())
    except (ValueError,UnicodeError) as exc:raise ValueError('Invalid palette anchor JSON') from exc
    if not isinstance(data,dict):raise ValueError('Palette anchor JSON must be an object')
    return path,data


def select_palette_anchor(pack,entry=None):
    """Return (path, provenance); explicit bad descriptors NEVER fall back."""
    pack=Path(pack)
    if entry is None:
        return pack/'pet/kurisu-animation/待机呼吸.webm',{'kind':'legacy_canonical_idle','explicit_descriptor':False}
    if not isinstance(entry,dict) or set(entry)!={'file','sha256'}:
        raise ValueError('Explicit palette anchor must pin descriptor file and SHA256')
    descriptor_path,d=_bound_json(pack,entry['file'],entry['sha256'],DESCRIPTOR_NAMESPACE)
    if type(d.get('schema_version')) is not int or d['schema_version']!=1 or d.get('anchor_kind')!='approved_original_static_palette_reference' or d.get('purpose')!='palette_reference_only':
        raise ValueError('Unsupported palette anchor descriptor kind/purpose')
    if d.get('counts_toward_106') is not False or d.get('final_animation_approved') is not False:
        raise ValueError('A static palette reference must never claim animation approval')
    if type(d.get('reference_frame')) is not int or d['reference_frame']!=0:
        raise ValueError('Static palette reference uses frame0 only')
    if d.get('source_file')!=APPROVED_ORIGINAL_FILE or d.get('source_sha256')!=APPROVED_ORIGINAL_SHA256:
        raise ValueError('Palette anchor is not bound to the approved original source')
    original=_path(pack,APPROVED_ORIGINAL_FILE,'references','.png')
    if _sha(original)!=APPROVED_ORIGINAL_SHA256:raise ValueError('Approved original palette source bytes changed')
    asset=_path(pack,d.get('asset_file'),STATIC_NAMESPACE,'.webm');asset_sha=_digest(d.get('asset_sha256'))
    if _sha(asset)!=asset_sha:raise ValueError('Static palette anchor asset SHA256 mismatch')
    _,technical=_bound_json(pack,d.get('technical_report_file'),d.get('technical_report_sha256'),STATIC_NAMESPACE)
    _,review=_bound_json(pack,d.get('independent_review_file'),d.get('independent_review_sha256'),REVIEW_NAMESPACE)
    if (technical.get('asset_kind')!='explicit_static_reference_preview_only' or technical.get('source_file')!=APPROVED_ORIGINAL_FILE
        or technical.get('source_reference_sha256')!=APPROVED_ORIGINAL_SHA256 or technical.get('file')!=d['asset_file']
        or technical.get('sha256')!=asset_sha or technical.get('counts_as_106_animation') is not False or technical.get('deliverable_animation') is not False):
        raise ValueError('Static palette technical report provenance/role mismatch')
    v=technical.get('verification') or {}
    expected={'width':640,'height':360,'fps':24,'duration':10,'decoded_frames':240,'all240_rgba_frames_identical':True,'alpha_min':0,'alpha_max':255,'audio_streams':0}
    if any(type(v.get(k)) is not type(value) or v.get(k)!=value for k,value in expected.items()):raise ValueError('Static palette anchor technical proof is incomplete or incompatible')
    if (review.get('asset_kind')!='explicit_static_reference_preview_only' or review.get('processing_clearance')!='allow_static_preview_only'
        or review.get('preview_allowed') is not True or review.get('final_media_approved') is not False
        or review.get('counts_toward_106') is not False or review.get('file')!=d['asset_file']
        or review.get('media_sha256')!=asset_sha or review.get('source_file')!=APPROVED_ORIGINAL_FILE
        or review.get('source_sha256')!=APPROVED_ORIGINAL_SHA256 or not review.get('reviewer') or not review.get('reviewed_at')):
        raise ValueError('Static palette anchor independent preview proof mismatch')
    r=review.get('independent_technical_checks') or {}
    proof={'frames':240,'unique_decoded_rgba_framemd5_count':1,'all240_decoded_rgba_frames_identical':True,
        'true_decoded_alpha':True,'alpha_min':0,'alpha_max':255,'all_rgba_exactly_matches_independently_recreated_filter':True}
    if any(type(r.get(k)) is not type(value) or r.get(k)!=value for k,value in proof.items()):raise ValueError('Static palette independent constant-frame/Alpha proof is incomplete')
    return asset,{'kind':'approved_original_static_palette_reference','purpose':'palette_reference_only','explicit_descriptor':True,
        'descriptor_file':entry['file'],'descriptor_sha256':entry['sha256'],'source_file':APPROVED_ORIGINAL_FILE,
        'source_sha256':APPROVED_ORIGINAL_SHA256,'asset_file':d['asset_file'],'asset_sha256':asset_sha,
        'technical_report_file':d['technical_report_file'],'technical_report_sha256':d['technical_report_sha256'],
        'independent_review_file':d['independent_review_file'],'independent_review_sha256':d['independent_review_sha256'],
        'reference_frame':0,'counts_toward_106':False,'animation_approval':False}
