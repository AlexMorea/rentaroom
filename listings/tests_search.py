"""
Search understands misspellings ("mid-rind" -> Midrand), several words
at once, room types and budgets typed into the box, and suggests places
as you type.
"""
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from listings.models import Profile, Room
from listings.search import best_correction, parse_query


def make_room(owner, title, suburb, city="Pretoria", room_type="Single Room", price=2000, description="Clean room."):
    return Room.objects.create(
        owner=owner, title=title, description=description, price=price,
        location=f"{suburb}, {city}", suburb=suburb, town=suburb, city=city, full_address="12 Example Street",
        postal_code="0122", room_type=room_type, contact_phone="+27821234567",
    )


class ParseQueryTests(TestCase):
    def test_reads_type_place_and_budget(self):
        p = parse_query("Bachelor in Mamelodi under R2,500")
        self.assertEqual((p.room_type, p.terms, p.max_price), ("Bachelor", ["mamelodi"], 2500))

    def test_budget_forms(self):
        self.assertEqual(parse_query("2.5k ensuite").max_price, 2500)
        self.assertEqual(parse_query("R1800 soshanguve").max_price, 1800)
        self.assertEqual(parse_query("under R2 500").max_price, 2500)
        self.assertEqual(parse_query("1500 2500").max_price, 1500)  # not glued into 15002500
        p = parse_query("student res near tut 1500-2500")
        self.assertEqual((p.room_type, p.terms, p.min_price, p.max_price), ("Student Accommodation", ["tut"], 1500, 2500))

    def test_postal_code_and_short_forms(self):
        self.assertEqual(parse_query("rooms 0122").postal_code, "0122")
        self.assertEqual(parse_query("room to rent in jhb").terms, ["johannesburg"])

    def test_corrects_your_examples(self):
        for typed in ("mid-rind", "mud-rind", "midrnd", "Midrend"):
            fix = best_correction(parse_query(typed).terms[0])
            self.assertIsNotNone(fix, typed)
            assert fix is not None
            self.assertEqual(fix[0], "Midrand", typed)

    def test_leaves_real_words_alone(self):
        self.assertIsNone(best_correction("wifi"))
        self.assertIsNone(best_correction("parking"))


class RoomSearchTests(TestCase):
    def setUp(self):
        cache.clear()
        owner = User.objects.create_user("sipho@example.com", "sipho@example.com", "Blue7Taxi!Rain")
        Profile.objects.filter(user=owner).update(role="landlord")
        self.midrand = make_room(owner, "Modern room near the Gautrain", "Midrand", city="Johannesburg", price=3200)
        self.mamelodi = make_room(owner, "Sunny single room", "Mamelodi East", price=1300)
        self.bachelor = make_room(owner, "Quiet bachelor flat", "Soshanguve", room_type="Bachelor", price=2600)
        self.garankuwa = make_room(owner, "Room close to Sefako Makgatho", "Ga-Rankuwa", price=1500)

    def search(self, q, **extra):
        return self.client.get(reverse("room_list"), {"q": q, **extra})

    def titles(self, resp):
        return [r.title for r in resp.context["rooms"]]

    def test_misspelt_place_finds_it_and_says_so(self):
        for typed in ("mid-rind", "mud-rind", "midrnd"):
            resp = self.search(typed)
            self.assertEqual(self.titles(resp), [self.midrand.title], typed)
            self.assertContains(resp, "Showing results for <strong>Midrand</strong>")
            self.assertContains(resp, "exact=1")

    def test_search_exactly_what_i_typed(self):
        resp = self.search("mid-rind", exact="1")
        self.assertEqual(self.titles(resp), [])
        self.assertNotContains(resp, "Showing results for <strong>Midrand</strong>")

    def test_several_words_at_once(self):
        # The old search looked for the whole phrase in one field: nothing.
        resp = self.search("single room mamelodi")
        self.assertEqual(self.titles(resp), [self.mamelodi.title])

    def test_budget_typed_in_the_box(self):
        resp = self.search("under 2000")
        self.assertEqual(set(self.titles(resp)), {self.mamelodi.title, self.garankuwa.title})
        self.assertContains(resp, "Up to R2 000")

    def test_type_and_place(self):
        resp = self.search("bachelor soshanguve")
        self.assertEqual(self.titles(resp), [self.bachelor.title])

    def test_no_type_match_shows_the_area_instead(self):
        resp = self.search("bachelor mamelodi")
        self.assertEqual(self.titles(resp), [self.mamelodi.title])
        self.assertContains(resp, "everything in that area")

    def test_unknown_extra_word_still_shows_closest_rooms(self):
        resp = self.search("mamelodi swimming pool")
        self.assertEqual(self.titles(resp), [self.mamelodi.title])
        self.assertContains(resp, "No room matches every word")

    def test_hyphenated_place_written_without_hyphen(self):
        resp = self.search("garankuwa")
        self.assertEqual(self.titles(resp), [self.garankuwa.title])

    def test_place_with_no_rooms_points_to_areas_that_have_some(self):
        resp = self.search("centurian")
        self.assertEqual(self.titles(resp), [])
        self.assertContains(resp, "No rooms listed in Centurion yet")
        self.assertContains(resp, "Areas with rooms right now")
        self.assertContains(resp, "Mamelodi East (1)")

    def test_newest_and_oldest_sort_are_honoured(self):
        resp = self.client.get(reverse("room_list"), {"sort": "oldest"})
        self.assertEqual(self.titles(resp)[0], self.midrand.title)
        resp = self.client.get(reverse("room_list"), {"sort": "newest"})
        self.assertEqual(self.titles(resp)[0], self.garankuwa.title)


class SuggestTests(TestCase):
    def setUp(self):
        cache.clear()
        owner = User.objects.create_user("sipho@example.com", "sipho@example.com", "Blue7Taxi!Rain")
        make_room(owner, "Modern room", "Midrand", city="Johannesburg")

    def suggest(self, q):
        return self.client.get(reverse("room_search_suggest"), {"q": q}).json()["suggestions"]

    def test_suggests_place_while_typing_even_with_a_typo(self):
        for typed in ("midr", "mudr", "mid-r"):
            first = self.suggest(typed)[0]
            self.assertEqual((first["label"], first["count"]), ("Midrand", 1), typed)
            self.assertEqual(first["url"], reverse("room_list") + "?q=Midrand")

    def test_suggests_room_types(self):
        labels = [s["label"] for s in self.suggest("bach")]
        self.assertIn("Bachelor", labels)

    def test_too_short_returns_nothing(self):
        self.assertEqual(self.suggest("m"), [])
