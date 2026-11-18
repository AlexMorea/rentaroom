from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from listings.views.static_pages import CONTACT_MAX_ATTEMPTS

VALID_MESSAGE = {
    "name": "Thandi",
    "email": "thandi@example.com",
    "reason": "general",
    "message": "Hi, I'd like to list my rooms.",
}


class ContactFormSpamProtectionTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_real_message_is_emailed(self):
        resp = self.client.post(reverse("contact"), VALID_MESSAGE)

        self.assertRedirects(resp, reverse("contact"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Thandi", mail.outbox[0].subject)

    def test_honeypot_looks_successful_but_sends_nothing(self):
        resp = self.client.post(reverse("contact"), {**VALID_MESSAGE, "website": "http://spam.example"}, follow=True)

        self.assertContains(resp, "Thanks for getting in touch")
        self.assertEqual(len(mail.outbox), 0)

    def test_network_is_throttled_after_limit(self):
        for _ in range(CONTACT_MAX_ATTEMPTS):
            self.client.post(reverse("contact"), VALID_MESSAGE)

        resp = self.client.post(reverse("contact"), VALID_MESSAGE)

        self.assertContains(resp, "Too many messages from this network")
        self.assertEqual(len(mail.outbox), CONTACT_MAX_ATTEMPTS)

    def test_honeypot_field_is_hidden_from_people(self):
        resp = self.client.get(reverse("contact"))

        self.assertContains(resp, 'class="ct-hp-field" aria-hidden="true"')
        self.assertContains(resp, 'tabindex="-1"')
