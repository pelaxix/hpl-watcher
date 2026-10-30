import threading
import unittest
from datetime import datetime, timezone, timedelta
from availability import Availability

PASSES=[{'id':'hca'}, {'id':'rom'}]
class AvailabilityTests(unittest.TestCase):
    def test_single_flight_cache_and_results(self):
        entered=threading.Event(); release=threading.Event(); done=threading.Event(); calls=[]
        def runner(definitions,publish):
            calls.append(1);entered.set();release.wait(2)
            publish('hca',[{'name':'Barton','available':2}],None)
            publish('rom',[],None);done.set()
        checker=Availability(PASSES,runner)
        self.assertTrue(checker.start()['checking']);self.assertTrue(entered.wait(1))
        for _ in range(5):self.assertTrue(checker.start()['checking'])
        self.assertEqual(len(calls),1)
        release.set();self.assertTrue(done.wait(1))
        # Wait for the worker finally block by acquiring the same state until finished.
        for _ in range(1000):
            if not checker.status()['checking']:break
            threading.Event().wait(.001)
        result=checker.start()
        self.assertFalse(result['checking']);self.assertEqual(len(calls),1)
        self.assertEqual(result['passes'][0]['branches'][0]['available'],2)
        self.assertEqual(result['passes'][1]['freshness'],'fresh')

    def test_failed_check_retains_previous_timestamp_and_excludes_freshness(self):
        checker=Availability(PASSES)
        checker._publish('hca',[{'name':'Barton','available':1}],None)
        before=checker.status()['passes'][0]
        checker._publish('hca',None,'Failed')
        after=checker.status()['passes'][0]
        self.assertEqual(before['checkedAt'],after['checkedAt'])
        self.assertEqual(before['branches'],after['branches'])
        self.assertEqual(after['freshness'],'stale')

    def test_pending_and_old_results(self):
        checker=Availability(PASSES)
        self.assertEqual(checker.status()['passes'][0]['freshness'],'pending')
        checker.results['hca']['checkedAt']=(datetime.now(timezone.utc)-timedelta(minutes=12)).isoformat()
        self.assertEqual(checker.status()['passes'][0]['freshness'],'stale')

    def test_runner_start_failure_marks_both_passes(self):
        def runner(definitions,publish):raise RuntimeError('Browser missing')
        checker=Availability(PASSES,runner);checker._run()
        self.assertFalse(checker.status()['checking'])
        self.assertTrue(all(p['error'] for p in checker.status()['passes']))

if __name__=='__main__':unittest.main()
