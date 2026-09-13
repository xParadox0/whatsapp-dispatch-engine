"""First acceptance wins.

The failure this prevents: supplier A accepts three seconds after the job was
escalated to supplier B, and B accepts too. Two suppliers get dispatched to one
breakdown, and the operator ends up arguing about who gets paid.

Acceptance must be an idempotent write. The first accepted status locks the job.
"""
import tempfile
import unittest
from pathlib import Path

from dispatch.store import JobStore
from dispatch.engine import DispatchEngine


class FirstAcceptanceWinsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = JobStore(Path(self.tmp.name) / 'jobs.json')
        self.engine = DispatchEngine(self.store)
        self.job = self.store.create_job(reference='CA123456', detail='blowout')
        self.store.record_offer(self.job.id, 'sup-1', expires_at=1000.0)
        self.store.record_offer(self.job.id, 'sup-2', expires_at=2000.0)

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_acceptance_is_accepted(self):
        result = self.engine.accept(self.job.id, supplier_id='sup-2')

        self.assertEqual(result.outcome, 'assigned')
        self.assertEqual(self.store.get_job(self.job.id).assigned_supplier_id, 'sup-2')

    def test_second_supplier_gets_already_assigned_not_a_double_dispatch(self):
        self.engine.accept(self.job.id, supplier_id='sup-2')

        late = self.engine.accept(self.job.id, supplier_id='sup-1')

        self.assertEqual(late.outcome, 'already_assigned')
        self.assertEqual(late.assigned_supplier_id, 'sup-2')
        self.assertEqual(self.store.get_job(self.job.id).assigned_supplier_id, 'sup-2')

    def test_repeating_the_same_acceptance_is_idempotent(self):
        first = self.engine.accept(self.job.id, supplier_id='sup-2')
        repeat = self.engine.accept(self.job.id, supplier_id='sup-2')

        self.assertEqual(first.outcome, 'assigned')
        self.assertEqual(repeat.outcome, 'already_assigned')
        self.assertEqual(self.store.get_job(self.job.id).assigned_supplier_id, 'sup-2')

    def test_lock_survives_a_restart(self):
        self.engine.accept(self.job.id, supplier_id='sup-2')

        reloaded = JobStore(self.store.path)
        late = DispatchEngine(reloaded).accept(self.job.id, supplier_id='sup-1')

        self.assertEqual(late.outcome, 'already_assigned')

    def test_assigned_job_is_no_longer_escalated(self):
        self.engine.accept(self.job.id, supplier_id='sup-2')

        self.assertEqual(self.store.offers_due_for_escalation(now=9999.0), [])


if __name__ == '__main__':
    unittest.main()
