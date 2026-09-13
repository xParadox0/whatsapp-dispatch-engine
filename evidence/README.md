# Live integration evidence

The `dispatch/` package in this repository is a self-contained state machine with
its own tests. The files in this folder come from a different place: a running
WhatsApp Cloud API integration on self-hosted n8n. They are recorded output, not
fixtures written by hand.

## What is here

```text
workflow-whatsapp-dispatch.json   the 9-node n8n workflow, secrets removed
status-callback-20.json           Meta delivery status, error 131047
status-callback-21.json           Meta delivery status, error 130497
```

## Why the callbacks matter more than the send call

The Graph API answers `HTTP 200` with a `wamid` as soon as it accepts a message.
That response says the request was queued. It does not say the message arrived.

Delivery happens asynchronously, and failures surface later through a status
callback sent back to the webhook. An integration that treats `HTTP 200` as
success will report delivery for messages that silently never land.

Both files in this folder are failures that a naive integration would have
reported as successes.

## Reading the two codes

```text
131047  Re-engagement message
        The 24-hour customer service window was closed, so free-form text was
        refused. Only a pre-approved template is allowed at that point.

130497  Business account is restricted from messaging users in this country
        Account-level country restriction. It applies until Meta business
        verification is complete, and no code change affects it.
```

The first code confirms the window logic in `Dispatch Brain` reached the correct
conclusion: it had already classified the supplier message as `template` before
Meta said the same thing.

The second is the current blocker. Business verification requires a legal
document carrying the registered organisation name, which is a paperwork
dependency rather than an engineering one.

## Workflow shape

```text
Meta Verify (GET)    webhook, GET, handshake entry point
Check Verify Token   compares the verify token
Echo Challenge       returns hub.challenge verbatim, or 403

WhatsApp Inbound     webhook, POST, messages and status callbacks
Dispatch Brain       job state, supplier ranking, 24-hour window decision
Route Action         dispatch, assign, or reply
Send To Supplier     Graph API call
Reply To Sender      Graph API call
Ack To Meta          responds to the webhook
```

Meta sends `GET` with `hub.challenge` for verification and `POST` for events.
An n8n webhook node binds a single HTTP method, so the two paths need separate
nodes. A workflow with only the POST node fails verification without an obvious
reason.

## Reproducing this

The export contains no credentials. To run it:

1. Import `workflow-whatsapp-dispatch.json` into n8n.
2. Replace `SET_YOUR_OWN_VERIFY_TOKEN` in `Check Verify Token` with your own value.
3. Set `WHATSAPP_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID` as environment variables.
   n8n ships `N8N_BLOCK_ENV_ACCESS_IN_NODE=true`, so also set it to `false` or the
   HTTP nodes cannot read those variables.
4. Activate the workflow before registering the webhook in Meta. The webhook path
   is only registered once the workflow is active, so verification returns 404
   if the order is reversed.
5. Subscribe the app to the WhatsApp Business Account with
   `POST /{waba-id}/subscribed_apps`. Setting the callback URL alone is not
   enough, and without this step the console test button works while real
   messages never arrive.
