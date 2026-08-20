from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from listings.models import Favorite, Review, Room, RoomStat


def make_room(owner, title="R1", price=1000, **kwargs):
    data = {
        "title": title,
        "owner": owner,
        "description": "desc",
        "price": price,
        "location": "Loc",
        "suburb": "S",
        "town": "T",
        "city": "C",
        "full_address": "Addr",
        "postal_code": "0000",
        "room_type": Room.ROOM_TYPES[0][0],
        "contact_phone": "0123456",
        "total_units": 1,
        "available_units": 1,
        "availability_status": "now",
        "is_available": True,
    }
    data.update(kwargs)
    return Room.objects.create(**data)


class RankingTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="u", password="p")
        cache.clear()

    def test_backfill_hits_and_compute_scores(self):
        r1 = make_room(self.user, title="A", price=100)
        r2 = make_room(self.user, title="B", price=200)

        # create historical view stats
        for _ in range(5):
            RoomStat.objects.create(room=r1, stat_type="view")
        for _ in range(2):
            RoomStat.objects.create(room=r2, stat_type="view")

        # contacts and favorites
        for _ in range(1):
            RoomStat.objects.create(room=r1, stat_type="contact_email")
        Favorite.objects.create(user=self.user, room=r1)

        # backfill hits (dry-run first)
        call_command("backfill_hits")

        # apply backfill
        call_command("backfill_hits", "--force")

        r1.refresh_from_db()
        r2.refresh_from_db()

        # hits should equal view counts (composite=false default)
        self.assertGreaterEqual(r1.hits, 5)
        self.assertGreaterEqual(r2.hits, 2)

        # compute scores (apply)
        call_command("compute_scores", "--force")

        r1.refresh_from_db()
        r2.refresh_from_db()

        self.assertTrue(r1.score >= r2.score)

    @override_settings(POPULAR_SCORE_THRESHOLD=1, USE_MATERIALIZED_SCORE=True)
    def test_room_list_popular_and_ordering(self):
        # create rooms with different scores
        r1 = make_room(self.user, title="Top")
        r2 = make_room(self.user, title="Low")

        # set scores directly
        Room.objects.filter(pk=r1.pk).update(score=500)
        Room.objects.filter(pk=r2.pk).update(score=1)

        # clear cache to ensure fresh computation
        cache.clear()

        c = Client()
        resp = c.get(reverse("room_list"))

        # view context contains popular_ids
        popular_ids = resp.context.get("popular_ids")
        self.assertIsNotNone(popular_ids)
        self.assertIn(r1.id, popular_ids)
        self.assertNotIn(r2.id, popular_ids)

        # ordering: first room should be r1 (highest score)
        rooms = resp.context.get("rooms")
        self.assertTrue(len(rooms) > 0)
        self.assertEqual(rooms[0].id, r1.id)
