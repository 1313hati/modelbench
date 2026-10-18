The `ledger` package has two unimplemented features; its visible tests fail with
`NotImplementedError`. Implement them without changing any public names,
signatures or the data model.

1. `ledger.allocation.allocate(total, weights)`
   Split a non-negative integer `total` proportionally across positive integer
   `weights`. Return a list of ints whose sum is exactly `total`. Use the largest
   remainder method: start from the floor of each exact share, then hand out the
   remaining units to the largest fractional remainders, breaking ties by lower
   index. Validate inputs with `ValueError`.

2. `ledger.report.account_balances(entries)` and `ledger.report.trial_balance(entries)`
   - `account_balances` sums every posting and converts each account total to its
     **natural balance**: debit-positive for `asset` and `expense`, credit-positive
     for `liability`, `equity` and `revenue`. Include every account that appears in
     any posting, even if its natural balance is zero. Return `{code: int}`.
   - `trial_balance` returns `[(code, name, balance), ...]` for accounts with a
     non-zero natural balance, sorted by code.
   - Unknown account codes raise `ValueError`.

Return only the two files you changed, using the `### FILE:` format. Keep the
rest of the package intact.
