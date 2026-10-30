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
        self.discovery_error = None
        self.completed = set()
        self.excluded = set()
        self.total = len(definitions)
        self.results = {p['id']: {'checkedAt': None, 'branches': [], 'error': None} for p in definitions}

    def status(self):
        with self.lock:
            now = datetime.now(timezone.utc)
            passes = []
            for definition in self.definitions:
                if definition['id'] in self.excluded:
                    continue
                item = copy.deepcopy(self.results[definition['id']])
                stamp = item['checkedAt']
                age = (now - datetime.fromisoformat(stamp)).total_seconds() if stamp else None
                item['freshness'] = 'pending' if age is None else 'stale' if age > 660 or item['error'] else 'fresh'
                passes.append({**definition, **item})
            return {'generatedAt': now.isoformat(), 'checking': self.checking, 'cacheSeconds': 30,
                    'copyType': 'Rec Pass Express', 'passes': passes, 'completed': len(self.completed),
                    'total': self.total, 'discoveryError': self.discovery_error}

    def start(self):
        with self.lock:
            cached = self.last_finished is not None and time.monotonic() - self.last_finished < 30
            if not self.checking and not cached:
                self.checking = True
                self.completed = set()
                self.discovery_error = None
                threading.Thread(target=self._run, daemon=True).start()
        return self.status()

    def _register(self, definitions):
        with self.lock:
            self.definitions = definitions
            self.total = len(definitions)
            self.excluded = set()
            self.results = {p['id']: self.results.get(p['id'], {'checkedAt': None, 'branches': [], 'error': None}) for p in definitions}

    def _publish(self, pass_id, branches, error, eligible=True):
        with self.lock:
            self.completed.add(pass_id)
            if not eligible:
                self.excluded.add(pass_id)
            previous = self.results[pass_id]
            self.results[pass_id] = {**previous, 'error': error} if error else {
                'checkedAt': datetime.now(timezone.utc).isoformat(), 'branches': branches, 'error': None}

    def _run(self):
        try:
            runner = self.runner
            if runner is None:
                from hpl import check_passes
                check_passes(self.definitions, self._publish, self._register)
            else:
                runner(self.definitions, self._publish)
        except Exception as exc:
            print(f'HPL check could not start: {type(exc).__name__}: {exc}', flush=True)
            with self.lock:
                self.discovery_error = 'Could not complete catalogue discovery or start HPL checks. Try again.'
            for definition in self.definitions:
                self._publish(definition['id'], None, 'Could not complete the HPL check. Try again or use the catalogue.')
        finally:
            with self.lock:
                self.checking = False
                self.last_finished = time.monotonic()
