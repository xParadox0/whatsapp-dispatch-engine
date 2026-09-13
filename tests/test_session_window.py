"""WhatsApp 24-hour session window.

Outside the 24-hour customer service window, only pre-approved template
messages may be sent. Free-form text is rejected by Meta. Bots that ignore this
work in testing, where the tester has just messaged in, and then fail silently
on real reminders and dispatch messages.

Each conversation has its own window: the client and every supplier are
separate sessions.
"""
import tempfile
import unittest
from pathlib import Path

from dispatch.whatsapp import MessageRejected, SessionWindow, WhatsAppGateway

DAY = 24 * 60 * 60


class SessionWindowTests(unittest.TestCase):
    def setUp(self):
        self.window = SessionWindow()

    def test_free_form_allowed_within_24_hours_of_an_inbound_message(self):
        self.window.record_inbound('+27820001111', at=1000.0)

        self.assertTrue(self.window.can_send_free_form('+27820001111', now=1000.0 + DAY - 1))

    def test_free_form_blocked_once_the_window_closes(self):
        self.window.record_inbound('+27820001111', at=1000.0)

        self.assertFalse(self.window.can_send_free_form('+27820001111', now=1000.0 + DAY + 1))

    def test_a_contact_who_never_messaged_has_no_open_window(self):
        self.assertFalse(self.window.can_send_free_form('+27820009999', now=1000.0))

    def test_each_conversation_has_its_own_window(self):
        self.window.record_inbound('+27820001111', at=1000.0)   # client messaged in
        now = 1000.0 + DAY + 10                                  # client window now closed

        self.window.record_inbound('+27820002222', at=now - 60)  # supplier just replied

        self.assertFalse(self.window.can_send_free_form('+27820001111', now=now))
        self.assertTrue(self.window.can_send_free_form('+27820002222', now=now))


class GatewayTemplateRulesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.gateway = WhatsAppGateway(
            approved_templates={'job_dispatch': ['reference', 'tyre_size', 'location', 'eta']},
            outbox_path=Path(self.tmp.name) / 'outbox.jsonl',
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_free_form_outside_the_window_is_rejected(self):
        with self.assertRaises(MessageRejected):
            self.gateway.send_text('+27820001111', 'Job available, can you take it?', now=5000.0)

    def test_approved_template_is_allowed_outside_the_window(self):
        sent = self.gateway.send_template(
            '+27820001111', 'job_dispatch',
            {'reference': 'CA123456', 'tyre_size': '295/80R22.5',
             'location': 'N1 north, km 43', 'eta': '45 min'},
            now=5000.0)

        self.assertEqual(sent['type'], 'template')
        self.assertEqual(sent['name'], 'job_dispatch')

    def test_unapproved_template_is_rejected(self):
        with self.assertRaises(MessageRejected):
            self.gateway.send_template('+27820001111', 'not_submitted_yet', {}, now=5000.0)

    def test_template_with_missing_variable_is_rejected_before_sending(self):
        with self.assertRaises(MessageRejected):
            self.gateway.send_template('+27820001111', 'job_dispatch',
                                       {'reference': 'CA123456'}, now=5000.0)

    def test_free_form_allowed_after_the_contact_messages_in(self):
        self.gateway.record_inbound('+27820001111', at=5000.0)

        sent = self.gateway.send_text('+27820001111', 'Thanks, sending details now.', now=5100.0)

        self.assertEqual(sent['type'], 'text')


if __name__ == '__main__':
    unittest.main()
