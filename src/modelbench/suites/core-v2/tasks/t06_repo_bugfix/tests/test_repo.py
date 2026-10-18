from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from harness import Checks, solution_arg  # noqa: E402

C = Checks()
sys.path.insert(0, solution_arg())

try:
    from reservations import ConflictError, InMemoryStorage, Reservation, ReservationService, Room, quote
except Exception as exc:  # noqa: BLE001
    C.check("package imports", lambda: (_ for _ in ()).throw(exc))
    C.report()


def d(value):
    return date.fromisoformat(value)


ROOM = Room("A", 4, 10000, 15000)
QUIET = Room("Q", 2, 8000, 12000)
ODD = Room("O", 2, 105, 105)


def svc():
    return ReservationService([ROOM, QUIET, ODD], InMemoryStorage())


def book(s, rid, start, end, room="A", guests=1):
    return s.book(Reservation(rid, room, d(start), d(end), guests))


C.eq("one weekday night", quote(ROOM, d("2024-03-07"), d("2024-03-08"))["room_total"], 10000)
C.eq("friday night is weekend", quote(ROOM, d("2024-03-08"), d("2024-03-09"))["room_total"], 15000)
C.eq("saturday night is weekend", quote(ROOM, d("2024-03-09"), d("2024-03-10"))["room_total"], 15000)
C.eq("sunday night is weekday", quote(ROOM, d("2024-03-10"), d("2024-03-11"))["room_total"], 10000)
C.eq("fri+sat total", quote(ROOM, d("2024-03-08"), d("2024-03-10"))["total"], 32400)
C.eq("thu+fri+sat room total", quote(ROOM, d("2024-03-07"), d("2024-03-10"))["room_total"], 40000)
C.eq("week long discount", quote(ROOM, d("2024-03-04"), d("2024-03-11"))["discount"], 8000)
C.eq("week long tax after discount", quote(ROOM, d("2024-03-04"), d("2024-03-11"))["tax"], 5760)
C.eq("week long total", quote(ROOM, d("2024-03-04"), d("2024-03-11"))["total"], 77760)
C.eq("28 nights discount", quote(ROOM, d("2024-01-01"), d("2024-01-29"))["discount"], 64000)
C.eq("28 nights total", quote(ROOM, d("2024-01-01"), d("2024-01-29"))["total"], 276480)
C.eq("half-up discount and tax", quote(ODD, d("2024-03-04"), d("2024-03-11"))["total"], 714)
C.eq("quote keys", set(quote(ROOM, d("2024-03-07"), d("2024-03-08"))), {"nights", "room_total", "discount", "tax", "total"})
C.raises("zero nights", ValueError, lambda: quote(ROOM, d("2024-03-07"), d("2024-03-07")))
C.raises("negative stay", ValueError, lambda: quote(ROOM, d("2024-03-08"), d("2024-03-07")))


def back_to_back_after():
    s = svc()
    book(s, "r1", "2024-04-01", "2024-04-03")
    book(s, "r2", "2024-04-03", "2024-04-05")
    assert len(s.storage.all()) == 2


def back_to_back_before():
    s = svc()
    book(s, "r2", "2024-04-03", "2024-04-05")
    book(s, "r1", "2024-04-01", "2024-04-03")
    assert len(s.storage.all()) == 2


def same_start_conflict():
    s = svc()
    book(s, "r1", "2024-04-01", "2024-04-03")
    try:
        book(s, "r2", "2024-04-01", "2024-04-02")
    except ConflictError:
        return
    raise AssertionError("expected ConflictError")


def overlap_one_night():
    s = svc()
    book(s, "r1", "2024-04-01", "2024-04-04")
    try:
        book(s, "r2", "2024-04-03", "2024-04-05")
    except ConflictError:
        return
    raise AssertionError("expected ConflictError")


def containment_conflict():
    s = svc()
    book(s, "r1", "2024-04-01", "2024-04-10")
    try:
        book(s, "r2", "2024-04-03", "2024-04-05")
    except ConflictError:
        return
    raise AssertionError("expected ConflictError")


def different_rooms_ok():
    s = svc()
    book(s, "r1", "2024-04-01", "2024-04-03", room="A")
    book(s, "r2", "2024-04-01", "2024-04-03", room="Q")
    assert len(s.storage.all()) == 2


C.check("back-to-back after is allowed", back_to_back_after)
C.check("back-to-back before is allowed", back_to_back_before)
C.check("same start conflicts", same_start_conflict)
C.check("one-night overlap conflicts", overlap_one_night)
C.check("containment conflicts", containment_conflict)
C.check("same dates in different rooms", different_rooms_ok)


def cancel_frees_dates():
    s = svc()
    book(s, "r1", "2024-04-01", "2024-04-03")
    assert s.cancel("r1") is True
    book(s, "r2", "2024-04-02", "2024-04-04")


def cancel_missing():
    s = svc()
    try:
        s.cancel("nope")
    except KeyError:
        return
    raise AssertionError("expected KeyError")


def capacity_guard():
    s = svc()
    try:
        book(s, "r1", "2024-04-01", "2024-04-03", guests=5)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def unknown_room():
    s = svc()
    try:
        book(s, "r1", "2024-04-01", "2024-04-03", room="Z")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


C.check("cancel frees the dates", cancel_frees_dates)
C.check("cancel missing raises KeyError", cancel_missing)
C.check("capacity is enforced", capacity_guard)
C.check("unknown room rejected", unknown_room)

C.report()
