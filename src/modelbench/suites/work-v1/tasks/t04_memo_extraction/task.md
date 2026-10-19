# Turn the memo into commitments

Read the memo below and extract every **commitment** as structured data.

```text
Northwind Q4 planning note — Monday 3 November 2025

Attendees: Priya, Marcus, Ana, Tom, Elena, plus Legal and Finance on the call.

Priya will send the revised pricing sheet to the sales team by 14 November.

Marcus committed to booking the Berlin venue by Friday 21 November, with a budget of $4,800.

Legal must return the data-processing addendum before the end of November.

The support rotation moves to Ana on 1 December.

Tom will draft the incident review by 5 December and circulate it to the board.

Finance will reconcile the Q3 rebates by 12 December.

Elena is to renew the SOC 2 certificate by 31 January 2026; the renewal quote is $12,500.

Priya will send the revised pricing sheet to the sales team by 14 November.

Nobody owns the churn spike yet, and the dashboard refresh can wait until someone has time.

We also discussed whether to revisit the office lease at some point next year, but no decision was made.
```

## What counts

A commitment is one sentence that names both a responsible person or team and
an explicit due date. Sentences missing either are not commitments; ignore
them, including any aside about something that "should" happen eventually.

## Output

A JSON array of objects with **exactly** these keys:

| key | value |
|---|---|
| `owner` | the responsible person or team, spelled as in the memo |
| `due` | ISO date `YYYY-MM-DD` |
| `amount_usd` | the amount in whole US dollars as a number, or `null` if the sentence names none |
| `source` | the complete sentence, verbatim, including its final period |

Rules:

1. Resolve relative dates against the memo date (3 November 2025). "The end of
   November" means 30 November; "Friday 21 November" means 21 November 2025.
2. Amounts lose the `$` and the thousands comma: `$4,800` becomes `4800`.
3. If the identical sentence appears twice, emit one record.
4. Sort by `due` ascending, then `owner` A–Z.
5. No prose, no comments, no trailing commas.

Return only the JSON array in a ```json fence.
