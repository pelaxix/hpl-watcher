"""Single-flight, on-demand checks with a shared 30-second cache."""
import copy
import threading
import time
from datetime import datetime, timezone

class Availability:
    def __init__(self, definitions, runner=None):
        self.definitions = definitions
        self.runner = runner
        self.lock = threading.Lock()
        self.checking = False
        self.last_finished = None
        self.results = {p['id']: {'checkedAt': None, 'branches': [], 'error': None} for p in definitions}

    def status(self):
        with self.lock:
            now = datetime.now(timezone.utc)
            passes = []
            for definition in self.definitions:
                item = copy.deepcopy(self.results[definition['id']])
                stamp = item['checkedAt']
                age = (now - datetime.fromisoformat(stamp)).total_seconds() if stamp else None
                item['freshness'] = 'pending' if age is None else 'stale' if age > 660 or item['error'] else 'fresh'
                passes.append({**definition, **item})
            return {'generatedAt': now.isoformat(), 'checking': self.checking, 'cacheSeconds': 30,
                    'copyType': 'Rec Pass Express', 'passes': passes}

    def start(self):
        with self.lock:
            cached = self.last_finished is not None and time.monotonic() - self.last_finished < 30
            if not self.checking and not cached:
                self.checking = True
                threading.Thread(target=self._run, daemon=True).start()
        return self.status()

    def _publish(self, pass_id, branches, error):
        with self.lock:
            previous = self.results[pass_id]
            self.results[pass_id] = {**previous, 'error': error} if error else {
                'checkedAt': datetime.now(timezone.utc).isoformat(), 'branches': branches, 'error': None}

    def _run(self):
        try:
            runner = self.runner
            if runner is None:
                from hpl import check_passes
                runner = check_passes
            runner(self.definitions, self._publish)
        except Exception as exc:
            print(f'HPL check could not start: {type(exc).__name__}: {exc}', flush=True)
            for definition in self.definitions:
                self._publish(definition['id'], None, 'HPL check could not start. Verify Playwright and Chromium are installed.')
        finally:
            with self.lock:
                self.checking = False
                self.last_finished = time.monotonic()
