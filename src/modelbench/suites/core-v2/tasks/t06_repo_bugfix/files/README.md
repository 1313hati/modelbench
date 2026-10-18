# reservations

Tiny reservation quoting library. Money is integer cents.

Rules:

- A reservation covers `[start, end)`: the checkout day is free for the next guest.
- Weekend nights are the nights starting on **Friday or Saturday**.
- Stays of 7 nights or more get 10% off the room total; 28 nights or more get 20%.
- The discount is applied before tax. Tax is 8% of the discounted room total,
  rounded half-up to the nearest cent.
- `quote()` returns `nights`, `room_total`, `discount`, `tax`, `total`.

Run the tests with `python -m unittest discover -s tests -v`.
