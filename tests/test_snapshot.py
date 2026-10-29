import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
import snapshot
import server

class SnapshotTests(unittest.TestCase):
    def test_error_keeps_last_success_and_other_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            snapshot.record_result('hca', [{'name':'Central','available':2}], data_dir=folder)
            snapshot.record_result('rom', [], data_dir=folder)
            before=json.loads((Path(folder)/'availability.json').read_text())
            snapshot.record_result('hca', error='Catalogue timed out', data_dir=folder)
            after=json.loads((Path(folder)/'availability.json').read_text())
            self.assertEqual(before['passes']['hca']['checkedAt'],after['passes']['hca']['checkedAt'])
            self.assertEqual(before['passes']['hca']['branches'],after['passes']['hca']['branches'])
            self.assertEqual(before['passes']['rom'],after['passes']['rom'])

    def test_pending_zero_and_stale_are_distinct(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(server,'DATA',Path(folder)):
            self.assertTrue(all(p['freshness']=='pending' for p in server.status()['passes']))
            snapshot.record_result('hca', [], data_dir=folder)
            self.assertEqual(server.status()['passes'][0]['freshness'],'fresh')
            data=json.loads((Path(folder)/'availability.json').read_text())
            data['passes']['hca']['checkedAt']=(datetime.now(timezone.utc)-timedelta(minutes=12)).isoformat()
            (Path(folder)/'availability.json').write_text(json.dumps(data))
            self.assertEqual(server.status()['passes'][0]['freshness'],'stale')

    def test_invalid_scan_does_not_replace_good_data(self):
        with tempfile.TemporaryDirectory() as folder:
            snapshot.record_result('rom', [], data_dir=folder)
            path=Path(folder)/'availability.json'
            before=path.read_bytes()
            with self.assertRaises(ValueError):
                snapshot.record_result('rom',[{'name':'Barton','available':-1}],data_dir=folder)
            self.assertEqual(before,path.read_bytes())

if __name__=='__main__': unittest.main()
