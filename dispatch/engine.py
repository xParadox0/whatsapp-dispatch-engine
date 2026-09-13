"""Dispatch engine: acceptance locking and timeout escalation.

Two rules drive everything here:

1. The first acceptance wins. Acceptance is an idempotent write, so a late
   acceptance never produces a second dispatch to the same breakdown.
2. Escalation is driven by persisted deadlines, not by an in-memory timer, so a
   restart cannot drop an in-flight job.
"""
from dataclasses import dataclass

from dispatch.store import ASSIGNED, CLOSED, OFFERED


@dataclass
class AcceptanceResult:
    outcome: str                      # 'assigned' | 'already_assigned' | 'unknown_job'
    job_id: str
    supplier_id: str
    assigned_supplier_id: str | None = None

    @property
    def reply(self):
        """The message the supplier should receive back on WhatsApp."""
        if self.outcome == 'assigned':
            return 'Job assigned to you. Please proceed and send an ETA.'
        if self.outcome == 'already_assigned':
            return 'This job is already assigned to another supplier. No action needed.'
        return 'We could not find that job reference.'


class DispatchEngine:
    def __init__(self, store):
        self.store = store

    def accept(self, job_id, supplier_id):
        job = self.store.get_job(job_id)
        if job is None:
            return AcceptanceResult('unknown_job', job_id, supplier_id)

        if job.assigned_supplier_id is not None:
            return AcceptanceResult('already_assigned', job_id, supplier_id,
                                    assigned_supplier_id=job.assigned_supplier_id)

        job.assigned_supplier_id = supplier_id
        job.status = ASSIGNED
        self.store.resolve_offer(job_id, supplier_id)
        self.store._save()
        return AcceptanceResult('assigned', job_id, supplier_id,
                                assigned_supplier_id=supplier_id)

    def escalate_due_offers(self, now, candidates_for):
        """Expire stale offers and hand each job to the next untried supplier.

        `candidates_for(job)` returns an ordered list of supplier ids, closest
        first. Suppliers already tried are skipped.
        """
        escalations = []
        for offer in list(self.store.offers_due_for_escalation(now=now)):
            job = self.store.get_job(offer.job_id)
            self.store.resolve_offer(job.id, offer.supplier_id)

            next_supplier = next(
                (sid for sid in candidates_for(job) if sid not in job.tried_supplier_ids),
                None,
            )
            if next_supplier is None:
                job.status = CLOSED
                self.store._save()
                escalations.append((job.id, None))
                continue

            job.status = OFFERED
            self.store.record_offer(job.id, next_supplier, expires_at=now + 300)
            escalations.append((job.id, next_supplier))
        return escalations
