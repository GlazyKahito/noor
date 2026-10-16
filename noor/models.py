"""Domain classes: Location, Region and the Resource family.

Syllabus links
* Encapsulation: Location keeps its data in _protected / __private attributes and exposes
  validated @property getters and setters.
* Composition: a Region creates and owns its Location objects.
* Inheritance + abstract base class: Resource is abstract; CoolingCentre, WaterPoint,
  MedicalUnit, ResponseTeam and OutreachTeam inherit from it.
* Polymorphism / method overriding: each resource type overrides capacity() and describe().
"""
import math
from abc import ABC, abstractmethod

from . import settings
from .exceptions import ValidationError

SHARE_FIELDS = ("elderly_share", "children_share", "outdoor_worker_share",
                "poor_housing_share", "low_income_share", "piped_water_share")


def _check_share(name, value):
    """Return value as a float in 0..1, or None if missing. Raise ValidationError otherwise."""
    if value is None or value == "":
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{name} must be a number between 0 and 1") from None
    if math.isnan(value) or not 0.0 <= value <= 1.0:
        raise ValidationError(f"{name} must be between 0 and 1")
    return value


class Location:
    """One ward or area that NOOR assesses."""

    created_count = 0  # class attribute: shared by every Location object

    def __init__(self, code, name, population=None, area_km2=None, grid_x=None, grid_y=None, **shares):
        """Create a location; the property setters below validate every value."""
        self.code = code
        self.name = name
        self.population = population
        self.area_km2 = area_km2
        self.grid_x = grid_x
        self.grid_y = grid_y
        self.__shares = {}  # private: only reachable through get_share / set_share
        for field in SHARE_FIELDS:
            self.set_share(field, shares.get(field))
        Location.created_count += 1

    # --- code -----------------------------------------------------------------------
    @property
    def code(self):
        """Short unique code such as SPR-01."""
        return self._code

    @code.setter
    def code(self, value):
        value = str(value or "").strip()
        if not 2 <= len(value) <= 20 or not value.replace("-", "").replace("_", "").isalnum():
            raise ValidationError("Location code must be 2-20 letters, digits, '-' or '_'")
        self._code = value

    # --- name -----------------------------------------------------------------------
    @property
    def name(self):
        """Display name."""
        return self._name

    @name.setter
    def name(self, value):
        value = str(value or "").strip()
        if not 1 <= len(value) <= 80:
            raise ValidationError("Location name must be 1-80 characters")
        self._name = value

    # --- population -----------------------------------------------------------------
    @property
    def population(self):
        """Number of residents, or None when unknown (never guessed)."""
        return self._population

    @population.setter
    def population(self, value):
        if value is None or value == "":
            self._population = None
            return
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise ValidationError("Population must be a whole number") from None
        if value < 0:
            raise ValidationError("Population cannot be negative")
        self._population = value

    # --- area -----------------------------------------------------------------------
    @property
    def area_km2(self):
        """Area in square kilometres, or None when unknown."""
        return self._area_km2

    @area_km2.setter
    def area_km2(self, value):
        if value is None or value == "":
            self._area_km2 = None
            return
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ValidationError("Area must be a number") from None
        if not value > 0:
            raise ValidationError("Area must be greater than zero")
        self._area_km2 = value

    # --- vulnerability shares (private dict) ---------------------------------------
    def get_share(self, field):
        """Return one vulnerability/capacity share (0..1) or None if missing."""
        return self.__shares.get(field)

    def set_share(self, field, value):
        """Validate and store one share."""
        if field not in SHARE_FIELDS:
            raise ValidationError(f"Unknown indicator '{field}'")
        self.__shares[field] = _check_share(field, value)

    @property
    def density(self):
        """People per km2, or None if population or area is unknown."""
        if self.population is None or self.area_km2 is None:
            return None
        return self.population / self.area_km2

    def distance_to(self, other):
        """Straight-line distance in km on the schematic grid (None if a position is missing)."""
        if None in (self.grid_x, self.grid_y, other.grid_x, other.grid_y):
            return 0.0 if other.code == self.code else None
        return math.hypot(self.grid_x - other.grid_x, self.grid_y - other.grid_y)

    def __repr__(self):
        """Readable form for debugging."""
        return f"Location({self.code!r}, {self.name!r}, population={self.population})"


class Region:
    """A district made of locations. Composition: the region creates and owns them."""

    def __init__(self, name, is_demo=True):
        """Start an empty region."""
        self.name = name
        self.is_demo = is_demo
        self._locations = {}

    def add_location(self, code, name, **fields):
        """Create a Location inside this region (it does not exist outside the region)."""
        if code in self._locations:
            raise ValidationError(f"Location {code} already exists in {self.name}")
        location = Location(code, name, **fields)
        self._locations[code] = location
        return location

    def get(self, code):
        """Return the location with this code, or None."""
        return self._locations.get(code)

    @property
    def locations(self):
        """A list copy so callers cannot change the region's own dict."""
        return list(self._locations.values())

    def total_population(self):
        """Sum of known populations (locations with unknown population are skipped)."""
        return sum(loc.population for loc in self._locations.values() if loc.population is not None)

    def __len__(self):
        """Number of locations in the region."""
        return len(self._locations)


class Resource(ABC):
    """Abstract emergency resource. Subclasses say how their size turns into people per day."""

    type_name = "resource"   # overridden by each subclass
    label = "Resource"
    unit = "units"

    def __init__(self, code, name, location_code, amount, status="available", radius_km=3.0,
                 staff=0, daily_cost=0, kind="synthetic"):
        """Store the inventory fields shared by every resource type."""
        if status not in settings.STATUS_FACTOR:
            raise ValidationError("Status must be available, limited or offline")
        if float(amount) <= 0:
            raise ValidationError("Amount must be greater than zero")
        if float(radius_km) <= 0:
            raise ValidationError("Service radius must be greater than zero")
        self.code = code
        self.name = name
        self.location_code = location_code
        self.amount = float(amount)
        self.status = status
        self.radius_km = float(radius_km)
        self.staff = int(staff)
        self.daily_cost = int(daily_cost)
        self.kind = kind

    def status_factor(self):
        """Share of the resource that is usable: 1.0 available, 0.5 limited, 0.0 offline."""
        return settings.STATUS_FACTOR[self.status]

    @abstractmethod
    def capacity(self):
        """People this resource can serve per day (after status)."""

    @abstractmethod
    def describe(self):
        """One-line description for tables and reports."""

    def serves(self, home, target):
        """True if `target` lies inside this resource's service radius from its `home` location."""
        distance = home.distance_to(target)
        return distance is not None and distance <= self.radius_km

    def __repr__(self):
        """Readable form for debugging."""
        return f"{self.__class__.__name__}({self.code!r}, capacity={self.capacity():.0f}/day)"


class CoolingCentre(Resource):
    """A cooled public space. Amount = places per day."""

    type_name = "cooling_centre"
    label = "Cooling centre"
    unit = "places/day"

    def capacity(self):
        """Places per day, reduced by status."""
        return self.amount * self.status_factor()

    def describe(self):
        """Cooling centre summary."""
        return f"{self.name}: {self.amount:.0f} places/day ({self.status})"


class WaterPoint(Resource):
    """A drinking-water point. Amount = litres per day."""

    type_name = "water_point"
    label = "Drinking-water point"
    unit = "litres/day"

    def capacity(self):
        """People served = litres / litres needed per person, reduced by status."""
        return self.amount / settings.LITRES_PER_PERSON * self.status_factor()

    def describe(self):
        """Water point summary."""
        return f"{self.name}: {self.amount:,.0f} L/day ≈ {self.capacity():,.0f} people ({self.status})"


class MedicalUnit(Resource):
    """A medical support unit. Amount = patients it can see per day."""

    type_name = "medical_unit"
    label = "Medical support unit"
    unit = "patients/day"

    def capacity(self):
        """Patients per day, reduced by status."""
        return self.amount * self.status_factor()

    def describe(self):
        """Medical unit summary."""
        return f"{self.name}: {self.amount:.0f} patients/day ({self.status})"


class ResponseTeam(Resource):
    """An emergency response team. Amount = number of members."""

    type_name = "response_team"
    label = "Emergency response team"
    unit = "members"

    def capacity(self):
        """Visits per day = members * visits per member, reduced by status."""
        return self.amount * settings.VISITS_PER_RESPONDER * self.status_factor()

    def describe(self):
        """Response team summary."""
        return f"{self.name}: {self.amount:.0f} members ≈ {self.capacity():.0f} visits/day ({self.status})"


class OutreachTeam(Resource):
    """A community outreach team. Amount = number of volunteers."""

    type_name = "outreach_team"
    label = "Community outreach team"
    unit = "volunteers"

    def capacity(self):
        """Contacts per day = volunteers * contacts per volunteer, reduced by status."""
        return self.amount * settings.CONTACTS_PER_VOLUNTEER * self.status_factor()

    def describe(self):
        """Outreach team summary."""
        return f"{self.name}: {self.amount:.0f} volunteers ≈ {self.capacity():.0f} contacts/day ({self.status})"


RESOURCE_CLASSES = {cls.type_name: cls for cls in
                    (CoolingCentre, WaterPoint, MedicalUnit, ResponseTeam, OutreachTeam)}


def make_resource(type_name, **fields):
    """Factory: build the right Resource subclass from its type name."""
    cls = RESOURCE_CLASSES.get(type_name)
    if cls is None:
        raise ValidationError(f"Unknown resource type '{type_name}'")
    return cls(**fields)
