"""Timeout escalation chain.

A supplier who does not answer must not stall the job. When an offer expires,
the next closest untried supplier is offered the job, and the chain ends
cleanly when the candidate list is exhausted.
"""
import tempfile
import unittest
from pathlib import Path

from dispatch.store import JobStore
from dispatch.engine import DispatchEngine


class EscalationChainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = JobStore(Path(self.tmp.name) / 'jobs.json')
        self.engine = DispatchEngine(self.store)
        self.job = self.store.create_job(reference='CA123456', detail='blowout')
        self.ranked = ['sup-1', 'sup-2', 'sup-3']

    def tearDown(self):
        self.tmp.cleanup()

    def candidates(self, job):
        return self.ranked

    def test_expired_offer_moves_to_the_next_supplier(self):
        self.store.record_offer(self.job.id, 'sup-1', expires_at=100.0)

        escalations = self.engine.escalate_due_offers(now=101.0, candidates_for=self.candidates)

        self.assertEqual(escalations, [(self.job.id, 'sup-2')])

    def test_a_supplier_is_never_offered_the_same_job_twice(self):
        self.store.record_offer(self.job.id, 'sup-1', expires_at=100.0)
        self.engine.escalate_due_offers(now=101.0, candidates_for=self.candidates)
        self.engine.escalate_due_offers(now=500.0, candidates_for=self.candidates)

        tried = self.store.get_job(self.job.id).tried_supplier_ids
        self.assertEqual(tried, ['sup-1', 'sup-2', 'sup-3'])
        self.assertEqual(len(tried), len(set(tried)))

    def test_chain_closes_when_every_supplier_has_been_tried(self):
        self.store.record_offer(self.job.id, 'sup-1', expires_at=100.0)
        self.engine.escalate_due_offers(now=101.0, candidates_for=self.candidates)
        self.engine.escalate_due_offers(now=500.0, candidates_for=self.candidates)

        final = self.engine.escalate_due_offers(now=900.0, candidates_for=self.candidates)

        self.assertEqual(final, [(self.job.id, None)])
        self.assertEqual(self.store.get_job(self.job.id).status, 'closed')

    def test_escalation_survives_a_restart(self):
        self.store.record_offer(self.job.id, 'sup-1', expires_at=100.0)

        reloaded = JobStore(self.store.path)
        escalations = DispatchEngine(reloaded).escalate_due_offers(
            now=101.0, candidates_for=self.candidates)

        self.assertEqual(escalations, [(self.job.id, 'sup-2')])

    def test_accepted_job_is_never_escalated_even_if_the_offer_expired(self):
        self.store.record_offer(self.job.id, 'sup-1', expires_at=100.0)
        self.engine.accept(self.job.id, 'sup-1')

        self.assertEqual(
            self.engine.escalate_due_offers(now=9999.0, candidates_for=self.candidates), [])


if __name__ == '__main__':
    unittest.main()
