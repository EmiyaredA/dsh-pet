"""Read-only revocation gate for motion inputs; remote history stays immutable."""
import hashlib
import json
import re
from pathlib import Path

# Background-only rejection is deliberately absent: a separately reviewed
# motion-only input may have a bad screen. Anatomy cannot be transferred safely.
ANATOMY_DEFECTS = {'unapproved_foreground_appendage', 'unapproved_anatomy', 'extra_limb', 'animal_tail'}


def anatomy_withdrawal(report):
    """Normalize only the two existing, explicit anatomy-withdrawal schemas."""
    if (report.get('classification') in ANATOMY_DEFECTS
            and report.get('withdraw_recommended') is True):
        return True
    defects = report.get('defects')
    return bool(report.get('recommendation') == 'WITHDRAW_DO_NOT_RELEASE'
        and isinstance(defects, list)
        and any(isinstance(d, dict) and d.get('severity') == 'hard'
                and d.get('type') in ANATOMY_DEFECTS for d in defects))


def assert_motion_source_reusable(state, pack, source_sha256, asset_id=None):
    """Reject source bytes with a current, explicit anatomy-withdrawal report.

    The hash identifies bytes across renamed local files or formal asset copies.
    Never mutate old allow reports, completed tasks or paid-call counts.
    """
    pack = Path(pack).resolve()
    # Follow only recorded motion-driver lineage, never visual resemblance.
    # A completed diagnostic remains completed, but is not a fresh safe driver.
    lineage_hashes = {source_sha256}
    lineage_assets = {asset_id} if asset_id else set()
    records = list(state.get('diagnostic_attempts', []))
    records += [t for a in state.get('actions', []) for t in a.get('attempts', [])]
    changed = True
    while changed:
        changed = False
        for record in records:
            if not (record.get('source_sha256') in lineage_hashes
                    or (record.get('result_asset_id') and record['result_asset_id'] in lineage_assets)):
                continue
            driver = record.get('inputs', {}).get('driver', {})
            parent_hash = record.get('driver_sha256') or driver.get('sha256')
            parent_asset = record.get('driver_asset_id') or driver.get('asset_id')
            if parent_hash and parent_hash not in lineage_hashes:
                lineage_hashes.add(parent_hash);changed=True
            if parent_asset and parent_asset not in lineage_assets:
                lineage_assets.add(parent_asset);changed=True
    reports = {}
    for action in state.get('actions', []):
        hold = action.get('quality_hold') or {}
        if hold.get('report_file') and hold.get('report_sha256'):
            reports[hold['report_file']] = (hold['report_sha256'], action['id'])
        for old in action.get('withdrawn_approvals', []):
            if old.get('independent_review_file') and old.get('independent_review_sha256'):
                reports[old['independent_review_file']] = (old['independent_review_sha256'], action['id'])
    for filename, (expected_sha, expected_action_id) in reports.items():
        path = (pack / filename).resolve()
        if not path.is_relative_to(pack):
            raise ValueError('Motion-source revocation evidence escaped the pet pack')
        try:
            data = path.read_bytes()
            if expected_sha and hashlib.sha256(data).hexdigest() != expected_sha:
                raise ValueError('Motion-source revocation evidence SHA changed')
            report = json.loads(data)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError('Motion-source revocation evidence is unavailable or malformed') from exc
        if not isinstance(report, dict):
            raise ValueError('Motion-source revocation evidence must be a record')
        if not anatomy_withdrawal(report):
            continue
        if report.get('action_id') != expected_action_id:
            raise ValueError('Motion-source anatomy report action identity needs reconciliation')
        source_values = [report[k] for k in ('raw_source_sha256', 'source_sha256', 'driver_sha256') if report.get(k) is not None]
        if not source_values or not all(isinstance(value,str) and re.fullmatch(r'[0-9a-f]{64}',value) for value in source_values):
            raise ValueError('Motion-source anatomy report lacks a bound original source SHA')
        hashes = set(source_values)
        assets = {report.get(k) for k in ('raw_asset_id', 'source_asset_id', 'driver_asset_id', 'result_asset_id')}
        if lineage_hashes & hashes or lineage_assets & assets:
            raise ValueError('Motion source is anatomy-withdrawn; a historical motion allow cannot override '+filename)
