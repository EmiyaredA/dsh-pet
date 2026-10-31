"""Load deliberate source-visual QA, bound to an immutable downloaded raw hash.

This gate never performs visual approval itself. It only makes the independent
reviewer's source-processing decision available to detached media workers.
Passing this gate is not approval of the resulting transparent video.
"""
from pathlib import Path
import json
import re

ALLOW='allow_mild_color_and_green_key'


def source_review_path(pack,action_id,attempt_index):
    if not re.fullmatch(r'a\d{3}',action_id) or not isinstance(attempt_index,int) or attempt_index<1:
        raise ValueError('Invalid source review identity')
    return Path(pack)/'quality/source-reviews'/f'{action_id}-attempt-{attempt_index}.json'


def load_source_review(pack,action_id,attempt_index,source_sha256):
    if not re.fullmatch(r'[a-f0-9]{64}',source_sha256):
        raise ValueError('Expected the downloaded source SHA256')
    path=source_review_path(pack,action_id,attempt_index)
    pending={'processing_clearance':'pending','action_id':action_id,'attempt_index':attempt_index,'source_sha256':source_sha256,'review_file':str(path),'final_media_approved':False}
    if not path.exists():
        return {**pending,'review_status':'missing','reason':'Independent source visual review has not been recorded'}
    try:
        review=json.loads(path.read_text())
    except (ValueError,OSError) as error:
        return {**pending,'review_status':'invalid','reason':str(error)}
    if (review.get('action_id')!=action_id or review.get('attempt_index')!=attempt_index or review.get('source_sha256')!=source_sha256):
        return {**pending,'review_status':'stale_or_mismatched','reason':'Review identity/hash differs from this downloaded source; inspect the actual bytes before processing'}
    if not (review.get('visual_review_performed') is True and review.get('reviewer') and review.get('reviewed_at')):
        return {**pending,'review_status':'incomplete','reason':'Metrics alone do not authorize source processing'}
    clearance=review.get('processing_clearance')
    if clearance not in {ALLOW,'reject'}:
        return {**pending,'review_status':'pending','reason':'Independent reviewer has not cleared this source'}
    # A mistaken allow label must never bypass an explicitly recorded hard defect.
    hard=[d for d in review.get('defects',[]) if isinstance(d,dict) and d.get('severity')=='hard']
    if hard:
        clearance='reject'
    return {**review,'processing_clearance':clearance,'review_status':'reviewed','review_file':str(path),'final_media_approved':False}
