"""
"Browse More Rooms" on page 1 used to do nothing but jump to the top: page
1 has no Back button, the pager script gave up without one, and the
button's href was "#". The buttons are now real links (kept filters
included), and the script no longer needs a Back button.
"""
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from listings.models import Profile, Room

PAGE_SIZE = 8


class BrowseMorePaginationTests(TestCase):
    def setUp(self):
        cache.clear()
        owner = User.objects.create_user("sipho@example.com", "sipho@example.com", "Blue7Taxi!Rain")
        Profile.objects.filter(user=owner).update(role="landlord")
        for i in range(PAGE_SIZE + 3):
            Room.objects.create(
                owner=owner, title=f"Room number {i + 1}", description="Clean room.", price=1000 + i,
                location="Mamelodi East, Pretoria", suburb="Mamelodi East", town="Mamelodi", city="Pretoria",
                full_address="12 Example Street", postal_code="0122", room_type="Single Room",
                contact_phone="+27821234567",
            )

    def test_page_one_links_to_page_two_without_a_back_button(self):
        resp = self.client.get(reverse("room_list"))
        html = resp.content.decode()
        self.assertContains(resp, "Page 1 of 2")
        self.assertIn('href="?page=2"', html)
        self.assertNotIn('id="btnBack"', html)
        self.assertNotIn('href="#"\n    class="pagination-btn', html)

    def test_page_link_keeps_the_search(self):
        resp = self.client.get(reverse("room_list") + "?q=Room")
        self.assertContains(resp, 'href="?q=Room&amp;page=2"')

    def test_page_two_shows_the_rest_and_can_go_back(self):
        resp = self.client.get(reverse("room_list") + "?page=2")
        self.assertContains(resp, "Page 2 of 2")
        self.assertEqual(len(resp.context["rooms"]), 3)
        self.assertContains(resp, 'href="?page=1"')

    def test_browse_more_request_returns_the_next_rooms(self):
        resp = self.client.get(
            reverse("room_list") + "?page=2&ajax=1", HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        data = resp.json()
        self.assertEqual((data["page"], data["num_pages"], data["has_next"]), (2, 2, False))
        self.assertEqual(data["html"].count('class="room-card rc-card"'), 3)
