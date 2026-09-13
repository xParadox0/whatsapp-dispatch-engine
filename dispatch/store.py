"""Durable job state for WhatsApp dispatch.

Escalation timers must survive a restart. Keeping them inside a running
workflow execution means a redeploy silently drops in-flight jobs, so state
lives on disk and every write is atomic.
"""
import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

PENDING = 'pending'
OFFERED = 'offered'
ASSIGNED = 'assigned'
CLOSED = 'closed'


@dataclass
class Job:
    id: str
    reference: str
    detail: str
    status: str = PENDING
    assigned_supplier_id: str | None = None
    tried_supplier_ids: list[str] = field(default_factory=list)


@dataclass
class Offer:
    job_id: str
    supplier_id: str
    expires_at: float
    resolved: bool = False


class JobStore:
    """File-backed store. Reloads on construction, so a restart recovers state."""

    def __init__(self, path):
        self.path = Path(path)
        self._jobs: dict[str, Job] = {}
        self._offers: list[Offer] = []
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding='utf-8'))
        self._jobs = {jid: Job(**data) for jid, data in raw.get('jobs', {}).items()}
        self._offers = [Offer(**data) for data in raw.get('offers', [])]

    def _save(self):
        payload = {
            'jobs': {jid: asdict(job) for jid, job in self._jobs.items()},
            'offers': [asdict(offer) for offer in self._offers],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic replace: a crash mid-write leaves the previous good file intact
        # and never leaves a partial file behind.
        handle, tmp_name = tempfile.mkstemp(dir=str(self.path.parent), suffix='.tmp')
        try:
            with os.fdopen(handle, 'w', encoding='utf-8') as stream:
                json.dump(payload, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp_name, self.path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def create_job(self, reference, detail):
        job = Job(id=str(uuid.uuid4()), reference=reference, detail=detail)
        self._jobs[job.id] = job
        self._save()
        return job

    def get_job(self, job_id):
        return self._jobs.get(job_id)

    def record_offer(self, job_id, supplier_id, expires_at):
        job = self._jobs[job_id]
        job.status = OFFERED
        if supplier_id not in job.tried_supplier_ids:
            job.tried_supplier_ids.append(supplier_id)
        offer = Offer(job_id=job_id, supplier_id=supplier_id, expires_at=expires_at)
        self._offers.append(offer)
        self._save()
        return offer

    def offers_due_for_escalation(self, now):
        """Unresolved offers past their deadline, for jobs still unassigned."""
        return [offer for offer in self._offers
                if not offer.resolved
                and offer.expires_at <= now
                and self._jobs[offer.job_id].status == OFFERED]

    def resolve_offer(self, job_id, supplier_id):
        for offer in self._offers:
            if offer.job_id == job_id and offer.supplier_id == supplier_id:
                offer.resolved = True
        self._save()
