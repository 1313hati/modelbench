import unittest

from ledger import Entry, Posting, account_balances, allocate, trial_balance


class AllocationTests(unittest.TestCase):
    def test_largest_remainder(self):
        self.assertEqual(allocate(10, [6, 4, 1]), [5, 4, 1])

    def test_equal_split(self):
        self.assertEqual(allocate(5, [1, 1, 1]), [2, 2, 1])

    def test_zero_total(self):
        self.assertEqual(allocate(0, [3, 7]), [0, 0])


class ReportTests(unittest.TestCase):
    def test_natural_balances(self):
        entry = Entry("e1", (Posting("1000", 10000), Posting("4000", -10000)))
        self.assertEqual(account_balances([entry]), {"1000": 10000, "4000": 10000})

    def test_trial_balance(self):
        entry = Entry("e1", (Posting("1000", 10000), Posting("4000", -10000)))
        self.assertEqual(
            trial_balance([entry]),
            [("1000", "Cash", 10000), ("4000", "Revenue", 10000)],
        )


if __name__ == "__main__":
    unittest.main()
