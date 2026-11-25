from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from listings.models import Profile


class SharedPhoneFlagTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin@example.com", "admin@example.com", "pw123456!")
        self.client.force_login(self.admin)
        self.a = self._user("a@example.com", "Bis", "0731112222")
        self.b = self._user("b@example.com", "Mack", "0731112222")
        self.c = self._user("c@example.com", "Thandi", "0829998888")

    def _user(self, email, first_name, phone):
        user = User.objects.create_user(username=email, email=email, first_name=first_name, password="pw123456!")
        Profile.objects.filter(user=user).update(phone_number=phone)
        return user

    def test_changelist_flags_accounts_sharing_a_phone(self):
        resp = self.client.get(reverse("admin:listings_profile_changelist"))

        self.assertContains(resp, "⚠️ 2 accounts", count=2)

    def test_filter_shows_only_shared_phone_accounts(self):
        resp = self.client.get(reverse("admin:listings_profile_changelist") + "?shared_phone=yes")

        self.assertContains(resp, "a@example.com")
        self.assertContains(resp, "b@example.com")
        self.assertNotContains(resp, "c@example.com")

    def test_change_page_lists_the_other_accounts(self):
        profile = Profile.objects.get(user=self.a)

        resp = self.client.get(reverse("admin:listings_profile_change", args=[profile.pk]))

        self.assertContains(resp, "Mack (b@example.com)")
        self.assertNotContains(resp, "Thandi (c@example.com)")

    def test_blank_phone_is_never_flagged(self):
        Profile.objects.filter(user__in=[self.a, self.b]).update(phone_number="")

        resp = self.client.get(reverse("admin:listings_profile_changelist") + "?shared_phone=yes")

        self.assertNotContains(resp, "a@example.com")
