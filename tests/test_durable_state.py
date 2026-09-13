"""Durable job state.

The failure this prevents: if an escalation timer lives only inside a running
workflow execution, restarting or redeploying that workflow silently drops
every in-flight job. A breakdown then sits unassigned with nobody paged.

These tests pin the behaviour that state survives a process restart.
"""
import tempfile
import unittest
from pathlib import Path

from dispatch.store import JobStore


class DurableJobStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'jobs.json'

    def tearDown(self):
        self.tmp.cleanup()

    def test_job_survives_a_full_restart(self):
        store = JobStore(self.path)
        job = store.create_job(reference='CA123456', detail='front left tyre blowout')

        # Simulate a crash or redeploy: nothing of the old process remains.
        del store
        recovered = JobStore(self.path)

        self.assertEqual(recovered.get_job(job.id).reference, 'CA123456')
        self.assertEqual(recovered.get_job(job.id).status, 'pending')

    def test_pending_escalations_are_recoverable_after_restart(self):
        store = JobStore(self.path)
        job = store.create_job(reference='CA123456', detail='blowout')
        store.record_offer(job.id, supplier_id='sup-1', expires_at=1000.0)

        recovered = JobStore(self.path)
        due = recovered.offers_due_for_escalation(now=1001.0)

        self.assertEqual([(o.job_id, o.supplier_id) for o in due], [(job.id, 'sup-1')])

    def test_offer_not_yet_expired_is_not_escalated(self):
        store = JobStore(self.path)
        job = store.create_job(reference='CA123456', detail='blowout')
        store.record_offer(job.id, supplier_id='sup-1', expires_at=1000.0)

        self.assertEqual(JobStore(self.path).offers_due_for_escalation(now=999.0), [])

    def test_writes_are_atomic_so_a_crash_cannot_corrupt_state(self):
        store = JobStore(self.path)
        store.create_job(reference='CA123456', detail='blowout')

        # No partial temp files may be left behind next to the state file.
        leftovers = [p.name for p in self.path.parent.iterdir() if p.name != self.path.name]
        self.assertEqual(leftovers, [])


if __name__ == '__main__':
    unittest.main()
