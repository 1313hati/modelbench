from .pricing import quote


class ConflictError(Exception):
    pass


class ReservationService:
    def __init__(self, rooms, storage):
        self.rooms = {room.id: room for room in rooms}
        self.storage = storage

    def _room(self, room_id):
        try:
            return self.rooms[room_id]
        except KeyError:
            raise ValueError(f"unknown room {room_id}") from None

    def _overlaps(self, room_id, start, end):
        for other in self.storage.for_room(room_id):
            if start < other.end and other.start < end:
                return True
        return False

    def book(self, reservation):
        room = self._room(reservation.room_id)
        if reservation.end <= reservation.start:
            raise ValueError("end must be after start")
        if reservation.guests < 1 or reservation.guests > room.capacity:
            raise ValueError("too many guests for this room")
        if self._overlaps(reservation.room_id, reservation.start, reservation.end):
            raise ConflictError(f"room {reservation.room_id} is already booked")
        self.storage.add(reservation)
        return quote(room, reservation.start, reservation.end)

    def cancel(self, reservation_id):
        reservation = self.storage.get(reservation_id)
        if reservation is None:
            raise KeyError(reservation_id)
        self.storage.remove(reservation_id)
        return True
