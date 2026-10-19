# Regional sales report, fixed width

Produce the quarterly regional sales report as **plain text** from this data:

| region | product | units | revenue (cents) |
|---|---|---|---|
| North | Widget | 1200 | 1450050 |
| North | Gadget | 340 | 225000 |
| South | Widget | 980 | 1189999 |
| South | Doohickey | 150 | 45000 |
| East | Widget | 760 | 899995 |
| East | Industrial Bracket Assembly | 88 | 129900 |
| West | Gadget | 410 | 310050 |
| West | Widget | 600 | 725000 |
| Central | Doohickey | 220 | 99999 |

## Layout

Five columns, joined by exactly one space, in this order and with these widths:

| column | width | alignment | format |
|---|---|---|---|
| REGION | 8 | left | as given |
| PRODUCT | 16 | left | as given |
| UNITS | 6 | right | thousands separator, no decimals |
| REVENUE | 12 | right | `$` then thousands separator and exactly two decimals |
| SHARE | 7 | right | one decimal and `%` |

Every line is exactly 53 characters and has no trailing spaces.

## Rules

1. Header line: the five column names in upper case, each padded to its width.
2. Second line: 53 `-` characters.
3. Data rows: sort by revenue **descending**; break ties by region A–Z, then product A–Z.
4. SHARE is that row's revenue as a percentage of total revenue, rounded half away
   from zero to one decimal (for example `28.565…` becomes `28.6%`). Do not force
   the shares to add up to 100.
5. If a REGION or PRODUCT value is longer than its column, keep the first
   `width - 1` characters and append `…` (U+2026).
6. Last line: `TOTAL` in the REGION column, PRODUCT column left blank, the sum of
   UNITS, the sum of REVENUE, and `100.0%`.
7. Nothing before the header, nothing after the total line.

Return the finished report in a ```text fence.
