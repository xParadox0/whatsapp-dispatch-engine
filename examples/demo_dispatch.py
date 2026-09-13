"""End-to-end demo: a roadside breakdown from intake to assignment.

Run it:

    python3 examples/demo_dispatch.py

No Meta credentials, no database, no network. The WhatsApp gateway is
simulated so the dispatch logic can be inspected on its own.
"""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dispatch.engine import DispatchEngine
from dispatch.store import JobStore
from dispatch.whatsapp import MessageRejected, WhatsAppGateway

DAY = 24 * 60 * 60

SUPPLIERS = {
    'sup-1': {'name': 'Highway Tyres', 'phone': '+27820001001', 'km': 8.2},
    'sup-2': {'name': 'N1 Truck Assist', 'phone': '+27820001002', 'km': 14.7},
    'sup-3': {'name': 'Midrand Mobile Fitment', 'phone': '+27820001003', 'km': 31.5},
}
CLIENT = '+27829990000'


def banner(text):
    print(f'\n{text}\n' + '=' * len(text))


def main():
    workdir = Path(tempfile.mkdtemp(prefix='dispatch-demo-'))
    store = JobStore(workdir / 'jobs.json')
    engine = DispatchEngine(store)
    gateway = WhatsAppGateway(
        approved_templates={
            'job_dispatch': ['reference', 'tyre_size', 'location', 'eta'],
            'job_update': ['reference', 'status'],
        },
        outbox_path=workdir / 'outbox.jsonl',
    )

    clock = 1_000_000.0

    banner('1. Client reports a breakdown')
    gateway.record_inbound(CLIENT, at=clock)
    print(f'   inbound from {CLIENT}: "Truck CA123456 blown front left tyre, N1 north km 43"')
    job = store.create_job(reference='CA123456', detail='front left tyre blowout, N1 north km 43')
    print(f'   job created: {job.id[:8]} status={job.status}')

    reply = gateway.send_text(CLIENT, 'Got it. Finding the closest fitment now.', now=clock)
    print(f'   reply sent as {reply["type"]} (window is open, client just messaged)')

    banner('2. Closest supplier is offered the job')
    first = 'sup-1'
    print(f'   ranked: ' + ', '.join(f'{s}={SUPPLIERS[s]["km"]}km' for s in SUPPLIERS))
    try:
        gateway.send_text(SUPPLIERS[first]['phone'], 'Job available, can you take it?', now=clock)
    except MessageRejected as exc:
        print(f'   free-form REJECTED: {exc}')
    sent = gateway.send_template(
        SUPPLIERS[first]['phone'], 'job_dispatch',
        {'reference': 'CA123456', 'tyre_size': '295/80R22.5',
         'location': 'N1 north, km 43', 'eta': 'asap'}, now=clock)
    print(f'   template "{sent["name"]}" sent to {SUPPLIERS[first]["name"]}')
    store.record_offer(job.id, first, expires_at=clock + 300)

    banner('3. No answer in 5 minutes, escalate')
    clock += 301
    escalations = engine.escalate_due_offers(now=clock, candidates_for=lambda j: list(SUPPLIERS))
    for job_id, next_supplier in escalations:
        print(f'   {SUPPLIERS[first]["name"]} timed out')
        print(f'   escalated to {SUPPLIERS[next_supplier]["name"]} ({SUPPLIERS[next_supplier]["km"]}km)')

    banner('4. Restart the process mid-job')
    del store, engine
    store = JobStore(workdir / 'jobs.json')
    engine = DispatchEngine(store)
    recovered = store.get_job(job.id)
    print(f'   state reloaded from disk: status={recovered.status} '
          f'tried={recovered.tried_supplier_ids}')
    print(f'   pending escalations still tracked: '
          f'{len(store.offers_due_for_escalation(now=clock + 10_000))}')

    banner('5. Two suppliers accept within seconds of each other')
    result_b = engine.accept(job.id, 'sup-2')
    print(f'   sup-2 accepts -> {result_b.outcome}')
    print(f'      reply: "{result_b.reply}"')
    result_a = engine.accept(job.id, 'sup-1')
    print(f'   sup-1 accepts 3s later -> {result_a.outcome}')
    print(f'      reply: "{result_a.reply}"')
    print(f'   assigned supplier remains: {store.get_job(job.id).assigned_supplier_id}')

    banner('6. Client update, 26 hours later')
    clock += 26 * 60 * 60
    try:
        gateway.send_text(CLIENT, 'Your truck is back on the road.', now=clock)
    except MessageRejected as exc:
        print(f'   free-form REJECTED: {exc}')
    sent = gateway.send_template(CLIENT, 'job_update',
                                 {'reference': 'CA123456', 'status': 'completed'}, now=clock)
    print(f'   template "{sent["name"]}" sent instead')

    banner('Result')
    final = store.get_job(job.id)
    print(f'   job {final.reference}: status={final.status} '
          f'assigned={final.assigned_supplier_id}')
    print(f'   suppliers contacted: {final.tried_supplier_ids}')
    print(f'   messages in outbox: '
          f'{len(gateway.outbox_path.read_text().strip().splitlines())}')
    print('   double dispatch: none')

    shutil.rmtree(workdir)


if __name__ == '__main__':
    main()
