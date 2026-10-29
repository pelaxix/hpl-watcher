"""Call from the existing scheduled watcher; never read or overwrite its alert baseline."""
import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def record_result(pass_id, branches=None, error=None, data_dir=None):
    """branches: [{name: str, available: int}]. Call only after a complete successful scan.

    With error=..., preserves the last successful results and their timestamp.
    Call sequentially from the existing single watcher job.
    """
    if pass_id not in ('hca', 'rom'):
        raise ValueError('pass_id must be hca or rom')
    if error is None:
        if not isinstance(branches, list):
            raise ValueError('A successful scan must supply a list, including [] for no availability')
        seen = set()
        for branch in branches:
            if not isinstance(branch.get('name'), str) or not branch['name'].strip():
                raise ValueError('Each branch requires a name')
            count = branch.get('available')
            if type(count) is not int or count < 0:
                raise ValueError('available must be a nonnegative integer')
            if branch['name'].strip().casefold() in seen:
                raise ValueError('Duplicate branch name')
            seen.add(branch['name'].strip().casefold())
    directory = Path(data_dir or os.environ.get('HPL_DATA_DIR', str(Path(__file__).resolve().parent / 'data')))
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / 'availability.json'
    saved = json.loads(destination.read_text(encoding='utf-8')) if destination.exists() else {'passes': {}}
    previous = saved.setdefault('passes', {}).get(pass_id, {})
    if error is not None:
        saved['passes'][pass_id] = {**previous, 'error': str(error)}
    else:
        saved['passes'][pass_id] = {'checkedAt': datetime.now(timezone.utc).isoformat(),
                                    'branches': sorted(branches, key=lambda b: b['name']), 'error': None}
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory, delete=False) as handle:
            temp_name = handle.name
            json.dump(saved, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, destination)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pass_id', choices=['hca', 'rom'])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--branches-json', help='JSON array of branch name/available objects; [] means none available')
    group.add_argument('--error', help='Record a failed check without changing last successful results')
    args = parser.parse_args()
    record_result(args.pass_id, json.loads(args.branches_json) if args.branches_json is not None else None, args.error)
