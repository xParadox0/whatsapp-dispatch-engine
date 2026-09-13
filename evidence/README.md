# Live integration evidence

The `dispatch/` package in this repository is a self-contained state machine with
its own tests. The files here come from somewhere else: a running WhatsApp Cloud
API integration on self-hosted n8n. They are recorded output, not fixtures
written by hand.

## What is here

```text
dispatch-report.png               the report page, rendered from real messages
workflow-whatsapp-dispatch.json   the 13-node n8n workflow, secrets removed
status-callback-20.json           Meta delivery status, error 131047
status-callback-21.json           Meta delivery status, error 130497
```

## The path that runs green

```text
phone  ->  WhatsApp Cloud API  ->  webhook  ->  n8n  ->  report page
```

A driver sends a plain WhatsApp message describing a breakdown. The workflow
parses it, assigns a reference, ranks suppliers by distance, decides whether the
24-hour session window allows free-form text or requires an approved template,
and appends the result to a durable log. The report page renders that log.

Every row in `dispatch-report.png` came from a message typed on a real phone.
Phone numbers are masked in the page itself, not edited afterwards.

State lives in n8n static data, so the log survives a container restart.

## Why the status callbacks are kept

The Graph API answers `HTTP 200` with a `wamid` as soon as it accepts a message.
That means queued, not delivered. Delivery resolves later, and failures come back
through a status callback to the same webhook. An integration that treats
`HTTP 200` as success will report delivery for messages that never arrive.

Both recorded callbacks are failures that such an integration would have counted
as successes:

```text
131047  the 24-hour window was closed, so free-form text was refused
130497  the account is country-restricted pending business verification
```

Error 131047 is worth reading twice. The workflow had already classified that
message as `template` before Meta returned the same verdict, so the window logic
was independently correct.

Error 130497 is an account-level restriction on messaging Indonesian numbers. It
stands until Meta business verification completes and no code change affects it,
which is why the demonstrated path ends at a report rather than at an outbound
reply. The two outbound nodes remain in the workflow, disconnected, ready to be
reattached when verification clears.

## Workflow shape

```text
Meta Verify (GET)      webhook, GET, verification handshake
Check Verify Token     compares the verify token
Echo Challenge         returns hub.challenge verbatim, or 403

WhatsApp Inbound       webhook, POST, messages and status callbacks
Dispatch Brain         job state, supplier ranking, window decision
Route Action           dispatch, assign, or reply
Record Job             appends to the durable log
Ack To Meta            responds to the webhook

Report Request (GET)   webhook, GET, the report page
Render Report          builds the HTML
Report Response        returns it

Send To Supplier       Graph API call, currently disconnected
Reply To Sender        Graph API call, currently disconnected
```

Meta sends `GET` with `hub.challenge` for verification and `POST` for events. An
n8n webhook node binds one HTTP method, so the two paths need separate nodes. A
workflow carrying only the POST node fails verification with no useful error.

## Reproducing this

The export contains no credentials.

1. Import `workflow-whatsapp-dispatch.json` into n8n.
2. Replace `SET_YOUR_OWN_VERIFY_TOKEN` in `Check Verify Token`.
3. Set `WHATSAPP_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID` as environment variables.
   n8n ships `N8N_BLOCK_ENV_ACCESS_IN_NODE=true`, so set it to `false` as well or
   the HTTP nodes cannot read those variables.
4. Activate the workflow before registering the webhook in Meta. The path is only
   registered once the workflow is active, so verification returns 404 if the
   order is reversed.
5. Subscribe the app to the WhatsApp Business Account with
   `POST /{waba-id}/subscribed_apps`. Setting the callback URL alone is not
   enough. Without this step the console test button works while real messages
   never arrive, which is a confusing failure to debug.
