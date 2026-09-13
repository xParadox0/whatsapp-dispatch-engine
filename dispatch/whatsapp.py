"""WhatsApp sending rules, simulated.

No Meta credentials are required to run this. The gateway enforces the rules
that actually break production bots and writes every message to an outbox file
so a demo can be inspected afterwards.

Rules enforced:
  - Free-form text only inside the 24-hour customer service window.
  - Outside it, only pre-approved templates.
  - Every template variable must be supplied before sending.
  - Each conversation has an independent window.
"""
import json
from pathlib import Path

WINDOW_SECONDS = 24 * 60 * 60


class MessageRejected(Exception):
    """Raised for a message Meta would refuse, caught before it is sent."""


class SessionWindow:
    def __init__(self):
        self._last_inbound: dict[str, float] = {}

    def record_inbound(self, contact, at):
        previous = self._last_inbound.get(contact)
        if previous is None or at > previous:
            self._last_inbound[contact] = at

    def can_send_free_form(self, contact, now):
        last = self._last_inbound.get(contact)
        if last is None:
            return False
        return (now - last) <= WINDOW_SECONDS

    def seconds_remaining(self, contact, now):
        last = self._last_inbound.get(contact)
        if last is None:
            return 0
        return max(0, int(WINDOW_SECONDS - (now - last)))


class WhatsAppGateway:
    def __init__(self, approved_templates, outbox_path):
        self.templates = approved_templates
        self.outbox_path = Path(outbox_path)
        self.window = SessionWindow()

    def record_inbound(self, contact, at):
        self.window.record_inbound(contact, at)

    def _write(self, message):
        self.outbox_path.parent.mkdir(parents=True, exist_ok=True)
        with self.outbox_path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(message) + '\n')
        return message

    def send_text(self, contact, body, now):
        if not self.window.can_send_free_form(contact, now):
            raise MessageRejected(
                f'free-form text to {contact} is outside the 24-hour window; '
                f'use an approved template')
        return self._write({'type': 'text', 'to': contact, 'body': body, 'at': now})

    def send_template(self, contact, name, variables, now):
        if name not in self.templates:
            raise MessageRejected(f'template {name!r} is not approved by Meta')
        required = self.templates[name]
        missing = [key for key in required if key not in variables]
        if missing:
            raise MessageRejected(f'template {name!r} is missing variables: {missing}')
        return self._write({'type': 'template', 'to': contact, 'name': name,
                            'variables': variables, 'at': now})

    def send(self, contact, now, text, template_name=None, variables=None):
        """Send free-form when the window allows it, otherwise fall back to a template."""
        if self.window.can_send_free_form(contact, now):
            return self.send_text(contact, text, now)
        if template_name is None:
            raise MessageRejected(
                f'window closed for {contact} and no template fallback was given')
        return self.send_template(contact, template_name, variables or {}, now)
