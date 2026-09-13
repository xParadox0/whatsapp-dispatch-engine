# WhatsApp Dispatch Engine

[![tests](https://github.com/xParadox0/whatsapp-dispatch-engine/actions/workflows/tests.yml/badge.svg)](https://github.com/xParadox0/whatsapp-dispatch-engine/actions/workflows/tests.yml)

A small, dependency-free reference implementation of the parts of a WhatsApp
dispatch bot that break in production rather than in testing.

Built as a portfolio piece for roadside assistance, field service, and clinic
booking automation, where a job is offered to one provider, escalated on
timeout, and must never be dispatched twice.

## See it run without installing anything

**Option 1: read the CI log.** Every push runs the full suite and the demo on
GitHub's servers. The output below is produced there, not on my machine.
[Latest run](https://github.com/xParadox0/whatsapp-dispatch-engine/actions/workflows/tests.yml)

**Option 2: run it in the browser.** Open the repository in GitHub Codespaces
(Code, then Codespaces, then Create codespace) and run:

```bash
python3 examples/demo_dispatch.py
```

**Option 3: run it locally.** No dependencies to install.

```bash
git clone https://github.com/xParadox0/whatsapp-dispatch-engine
cd whatsapp-dispatch-engine
python3 -m unittest discover -s tests -q   # 23 tests
python3 examples/demo_dispatch.py          # full flow, no credentials needed
```

Python 3.11+, standard library only. No Meta account, no database, no network.

## The four failures this addresses

Most WhatsApp automations demo cleanly and then fail once real traffic arrives.
These are the failures, and the test that pins each one.

### 1. Escalation timers that do not survive a restart

If a "wait 5 minutes, then escalate" step lives inside a running workflow
execution, a restart or redeploy silently drops every in-flight job. A
breakdown then sits unassigned with nobody paged.

Job state and offer deadlines are persisted, and every write is atomic, so a
crash mid-write leaves the previous good state intact.

```
tests/test_durable_state.py::test_job_survives_a_full_restart
tests/test_durable_state.py::test_pending_escalations_are_recoverable_after_restart
tests/test_durable_state.py::test_writes_are_atomic_so_a_crash_cannot_corrupt_state
```

### 2. Double dispatch when two providers accept

Supplier A accepts three seconds after the job was escalated to supplier B, and
B accepts too. Two vehicles get sent to one breakdown, and the operator ends up
arguing about who gets paid.

Acceptance is an idempotent write. The first accepted status locks the job, and
later acceptances receive an automatic "already assigned" reply.

```
tests/test_acceptance_locking.py::test_second_supplier_gets_already_assigned_not_a_double_dispatch
tests/test_acceptance_locking.py::test_repeating_the_same_acceptance_is_idempotent
tests/test_acceptance_locking.py::test_lock_survives_a_restart
```

### 3. The WhatsApp 24-hour window

Outside the 24-hour customer service window, only pre-approved template
messages may be sent. Free-form text is refused. This passes in testing,
because the tester has just messaged in, and then fails on real reminders.

Each conversation carries its own window. The client and every supplier are
independent sessions. Templates are validated before sending, so a missing
variable is caught locally instead of by Meta.

```
tests/test_session_window.py::test_free_form_blocked_once_the_window_closes
tests/test_session_window.py::test_each_conversation_has_its_own_window
tests/test_session_window.py::test_template_with_missing_variable_is_rejected_before_sending
```

### 4. Escalation chains that loop or stall

A provider who does not answer must not stall the job, and must never be
offered the same job twice.

```
tests/test_escalation.py::test_a_supplier_is_never_offered_the_same_job_twice
tests/test_escalation.py::test_chain_closes_when_every_supplier_has_been_tried
tests/test_escalation.py::test_accepted_job_is_never_escalated_even_if_the_offer_expired
```

## Demo output

Real output from `python3 examples/demo_dispatch.py`, trimmed for length:

```
2. Closest supplier is offered the job
   ranked: sup-1=8.2km, sup-2=14.7km, sup-3=31.5km
   free-form REJECTED: free-form text to +27820001001 is outside the 24-hour
   window; use an approved template
   template "job_dispatch" sent to Highway Tyres

3. No answer in 5 minutes, escalate
   Highway Tyres timed out
   escalated to N1 Truck Assist (14.7km)

4. Restart the process mid-job
   state reloaded from disk: status=offered tried=['sup-1', 'sup-2']
   pending escalations still tracked: 1

5. Two suppliers accept within seconds of each other
   sup-2 accepts -> assigned
   sup-1 accepts 3s later -> already_assigned
   assigned supplier remains: sup-2

Result
   job CA123456: status=assigned assigned=sup-2
   suppliers contacted: ['sup-1', 'sup-2']
   double dispatch: none
```

## Layout

```
dispatch/store.py      durable job state, atomic writes, offer deadlines
dispatch/engine.py     acceptance locking, timeout escalation chain
dispatch/whatsapp.py   24-hour window and template rules, simulated gateway
tests/                 23 tests, written before the implementation
examples/              runnable end-to-end demo
```

## This runs against the real WhatsApp Cloud API

The engine below is transport-independent and tested on its own. The same logic
also runs in production on self-hosted n8n, wired to the Meta WhatsApp Cloud API.

Recorded output from that deployment is in [`evidence/`](evidence/), including the
exported 9-node workflow and two Meta delivery status callbacks.

Those callbacks are the point. The Graph API returns `HTTP 200` with a `wamid` as
soon as it queues a message, which is not the same as delivery. Failures arrive
later through a status webhook. Both recorded callbacks are failures that a
naive integration would have counted as successes:

```text
131047  the 24-hour window was closed, so free-form text was refused
130497  the account is country-restricted pending business verification
```

Error 131047 confirms the window logic reached the right answer independently.
The dispatch step had already classified that message as `template` before Meta
returned the same verdict.

## Scope

This is a reference implementation of dispatch logic, not a deployable product.

It does not include a live Meta Cloud API client, real supplier data, distance
calculation against a mapping provider, or authentication. The gateway is
simulated on purpose, so the state machine can be read and run without
credentials.

In a production build the same logic sits behind the real Cloud API, with
supplier ranking driven by a mapping API and a shortlist pre-filtered by
straight-line radius to keep call volume down.

## Licence

MIT
