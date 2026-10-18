import unittest
from datetime import date

from reservations import (
    ConflictError,
    InMemoryStorage,
    Reservation,
    ReservationService,
    Room,
    quote,
)


def d(value):
    return date.fromisoformat(value)


ROOM = Room("A", 4, 10000, 15000)
OTHER = Room("B", 2, 8000, 12000)


def service():
    return ReservationService([ROOM, OTHER], InMemoryStorage())


class PricingTests(unittest.TestCase):
    def test_two_weekend_nights(self):
        result = quote(ROOM, d("2024-03-01"), d("2024-03-03"))
        self.assertEqual(result["room_total"], 30000)
        self.assertEqual(result["total"], 32400)

    def test_friday_and_saturday_are_weekend_nights(self):
        # Thursday, Friday, Saturday: one weekday night and two weekend nights.
        result = quote(ROOM, d("2024-03-07"), d("2024-03-10"))
        self.assertEqual(result["room_total"], 40000)
        self.assertEqual(result["tax"], 3200)

    def test_week_long_stay_gets_discount_before_tax(self):
        result = quote(ROOM, d("2024-03-04"), d("2024-03-11"))
        self.assertEqual(result["discount"], 8000)
        self.assertEqual(result["tax"], 5760)
        self.assertEqual(result["total"], 77760)


class BookingTests(unittest.TestCase):
    def test_basic_booking(self):
        svc = service()
        res = Reservation("r1", "A", d("2024-04-01"), d("2024-04-03"))
        quote_result = svc.book(res)
        self.assertEqual(quote_result["nights"], 2)
        self.assertEqual(svc.storage.get("r1"), res)

    def test_back_to_back_reservations_are_allowed(self):
        svc = service()
        svc.book(Reservation("r1", "A", d("2024-04-01"), d("2024-04-03")))
        svc.book(Reservation("r2", "A", d("2024-04-03"), d("2024-04-05")))
        self.assertEqual(len(svc.storage.all()), 2)


if __name__ == "__main__":
    unittest.main()
