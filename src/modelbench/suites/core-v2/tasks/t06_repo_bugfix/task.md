The small `reservations` package has a failing test suite. Actual run output:

```
ERROR: test_back_to_back_reservations_are_allowed
  ConflictError: room A is already booked
FAIL: test_friday_and_saturday_are_weekend_nights
  AssertionError: 35000 != 40000
FAIL: test_two_weekend_nights
  AssertionError: 25000 != 30000
FAIL: test_week_long_stay_gets_discount_before_tax
  AssertionError: 6400 != 5760
Ran 5 tests - FAILED (failures=3, errors=1)
```

Find and fix the defects. The public API (module names, class names, function
signatures, return dictionary keys) must not change. Hidden tests cover the same
rules with more edge cases: half-open reservation intervals, Friday/Saturday
weekend pricing, 7-night and 28-night discounts applied before 8% tax, and
cent-level rounding.

Return only the files you changed, using the `### FILE:` format.
