"""Tests for the OOP domain classes (encapsulation, composition, inheritance, polymorphism)."""
import unittest

from noor import settings
from noor.exceptions import ValidationError
from noor.models import (CoolingCentre, Location, MedicalUnit, OutreachTeam, Region, Resource, ResponseTeam,
                         WaterPoint, make_resource)


class LocationTests(unittest.TestCase):
    """Property setters validate every value."""

    def test_valid_location(self):
        loc = Location("A-01", "Alpha", 1000, 2.0, 0, 0, elderly_share=0.1)
        self.assertEqual(loc.density, 500)
        self.assertEqual(loc.get_share("elderly_share"), 0.1)

    def test_negative_population_rejected(self):
        with self.assertRaises(ValidationError):
            Location("A-01", "Alpha", -5)

    def test_population_text_rejected(self):
        with self.assertRaises(ValidationError):
            Location("A-01", "Alpha", "many")

    def test_unknown_population_stays_none(self):
        loc = Location("A-01", "Alpha", None, 2.0)
        self.assertIsNone(loc.population)
        self.assertIsNone(loc.density)  # never guessed

    def test_area_must_be_positive(self):
        with self.assertRaises(ValidationError):
            Location("A-01", "Alpha", 10, 0)

    def test_share_out_of_range(self):
        with self.assertRaises(ValidationError):
            Location("A-01", "Alpha", 10, 1.0, elderly_share=1.5)

    def test_bad_code(self):
        for code in ("", "A", "has space", "x" * 30, "a;drop"):
            with self.assertRaises(ValidationError, msg=code):
                Location(code, "Alpha")

    def test_private_shares_not_directly_reachable(self):
        loc = Location("A-01", "Alpha")
        self.assertFalse(hasattr(loc, "__shares"))  # name-mangled to _Location__shares

    def test_class_attribute_counts_instances(self):
        before = Location.created_count
        Location("A-02", "Beta")
        self.assertEqual(Location.created_count, before + 1)

    def test_distance(self):
        a = Location("A-01", "A", grid_x=0, grid_y=0)
        b = Location("B-01", "B", grid_x=3, grid_y=4)
        self.assertEqual(a.distance_to(b), 5)
        c = Location("C-01", "C")  # no position
        self.assertIsNone(a.distance_to(c))


class RegionTests(unittest.TestCase):
    """Composition: the region creates and owns its locations."""

    def test_add_and_total(self):
        region = Region("Test region")
        region.add_location("A-01", "A", population=100)
        region.add_location("B-01", "B", population=None)
        self.assertEqual(len(region), 2)
        self.assertEqual(region.total_population(), 100)

    def test_duplicate_code(self):
        region = Region("Test region")
        region.add_location("A-01", "A")
        with self.assertRaises(ValidationError):
            region.add_location("A-01", "Again")

    def test_locations_is_a_copy(self):
        region = Region("Test region")
        region.add_location("A-01", "A")
        region.locations.clear()
        self.assertEqual(len(region), 1)


class ResourceTests(unittest.TestCase):
    """Inheritance and polymorphism of the Resource family."""

    def test_abstract_class_cannot_be_created(self):
        with self.assertRaises(TypeError):
            Resource("X", "x", "A-01", 10)

    def test_each_type_converts_amount_differently(self):
        self.assertEqual(CoolingCentre("C", "c", "A", 100).capacity(), 100)
        self.assertEqual(WaterPoint("W", "w", "A", 400).capacity(), 400 / settings.LITRES_PER_PERSON)
        self.assertEqual(MedicalUnit("M", "m", "A", 50).capacity(), 50)
        self.assertEqual(ResponseTeam("R", "r", "A", 5).capacity(), 5 * settings.VISITS_PER_RESPONDER)
        self.assertEqual(OutreachTeam("O", "o", "A", 2).capacity(), 2 * settings.CONTACTS_PER_VOLUNTEER)

    def test_status_reduces_capacity(self):
        self.assertEqual(CoolingCentre("C", "c", "A", 100, status="limited").capacity(), 50)
        self.assertEqual(CoolingCentre("C", "c", "A", 100, status="offline").capacity(), 0)

    def test_describe_is_overridden(self):
        texts = {make_resource(t, code="X", name="Thing", location_code="A", amount=10).describe()
                 for t in ("cooling_centre", "water_point", "medical_unit", "response_team", "outreach_team")}
        self.assertEqual(len(texts), 5)  # every subclass says something different

    def test_factory_rejects_unknown_type(self):
        with self.assertRaises(ValidationError):
            make_resource("helicopter", code="X", name="x", location_code="A", amount=1)

    def test_invalid_inputs(self):
        with self.assertRaises(ValidationError):
            CoolingCentre("C", "c", "A", 0)
        with self.assertRaises(ValidationError):
            CoolingCentre("C", "c", "A", 10, status="broken")
        with self.assertRaises(ValidationError):
            CoolingCentre("C", "c", "A", 10, radius_km=0)

    def test_serves_inside_radius_only(self):
        home = Location("A-01", "A", grid_x=0, grid_y=0)
        near = Location("B-01", "B", grid_x=3, grid_y=0)
        far = Location("C-01", "C", grid_x=3.1, grid_y=0)
        centre = CoolingCentre("C", "c", "A-01", 10, radius_km=3.0)
        self.assertTrue(centre.serves(home, near))  # exactly on the edge counts
        self.assertFalse(centre.serves(home, far))


if __name__ == "__main__":
    unittest.main()
