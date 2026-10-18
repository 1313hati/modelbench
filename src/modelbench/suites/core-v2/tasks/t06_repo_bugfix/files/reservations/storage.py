class InMemoryStorage:
    def __init__(self):
        self._items = {}

    def add(self, reservation):
        if reservation.id in self._items:
            raise ValueError(f"duplicate reservation id {reservation.id}")
        self._items[reservation.id] = reservation

    def get(self, reservation_id):
        return self._items.get(reservation_id)

    def remove(self, reservation_id):
        return self._items.pop(reservation_id, None)

    def for_room(self, room_id):
        return [r for r in self._items.values() if r.room_id == room_id]

    def all(self):
        return list(self._items.values())
