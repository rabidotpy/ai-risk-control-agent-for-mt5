# MT5 Administrator — Deals view (screenshot notes)

> Companion file to `mt5_admin_deals_screenshot.png` (BestWingGlobalMarkets-Server, captured 2026-05-08). The image itself is the source of truth; this file captures what's in it as searchable text so the schema and prompts can be aligned.

## Window context

- App: **MetaTrader 5 Administrator** (`mt5-admin` window title).
- Connected server: `BestWingGlobalMarkets-Server` → New Server → Orders & Deals → Deals.
- Filtered by **Login = 202011** (search box top-left of the deals table).
- Symbol filter = `All Symbols`. Date range: `1970.01.01 00:00` → `2026.05.07 23:59`. Source: `Current database`.
- Footer log: `'1000': 347 deals have been requested` and `'1000': export deals, 347 records to 'Deals-202011.csv'`.

## Visible deal-table columns (left → right)

| MT5 column | Sample value             | Notes                                                                |
| ---------- | ------------------------ | -------------------------------------------------------------------- |
| Time       | `2026.04.29 07:07:41.9…` | MT5's local format with period separators + sub-second precision.    |
| Login      | `202011`                 | Account ID. Same for every row (filtered).                           |
| Deal       | `893256`                 | Unique per deal.                                                     |
| Order      | `5203167`                | The order that produced this deal. Often equal to Position on entry. |
| Position   | `5203167`                | Pair "in" with "out" by this. First "in" deal seeds the Position ID. |
| Symbol     | `XAUUSD`                 | Gold throughout this user's activity.                                |
| Act…       | `buy` / `sell`           | Truncated header — Action column.                                    |
| Entry      | `in` / `out`             |                                                                      |
| Volume     | `0.01`                   | Micro lots throughout.                                               |
| Price      | `4598.49`                | XAUUSD price.                                                        |
| S/L        | `0.00`                   | **Always 0.00 in this dataset**, never null. 0 = unset, per MT5.     |
| T/P        | `0.00`                   | Same.                                                                |
| Market…    | `4598.06`                | Probable: market_bid at deal time.                                   |
| Market…    | `4598.49`                | Probable: market_ask at deal time.                                   |
| Market…    | `0.00`                   | Probable: market_last. **Often 0.00** — meaning "not set".           |
| Rea…       | `Mobile`                 | Reason. **`Mobile` is the value seen on every row in view.**         |
| Swap       | `0.00`                   | Always 0 here — positions held too short for rollover.               |
| Profit     | `1.40`, `-9.16`, …       | 0.00 on every "in" deal; the realised P&L lands on the "out" deal.   |

## Sample rows (transcribed)

```
Time                  Login   Deal    Order   Position  Symbol  Action  Entry  Vol  Price    SL    TP    Market  Market  Market  Reason  Swap  Profit
2026.04.29 07:07:41.9 202011  893256  5203167 5203167   XAUUSD  buy     in     0.01 4598.49  0.00  0.00  4598.06 4598.49 0.00    Mobile  0.00   0.00
2026.04.29 07:09:37.1 202011  893257  5203168 5203167   XAUUSD  sell    out    0.01 4599.89  0.00  0.00  4599.91 4600.27 0.00    Mobile  0.00   1.40
2026.04.29 08:40:56.4 202011  893307  5203218 5203215   XAUUSD  buy     out    0.01 4596.83  0.00  0.00  4596.48 4596.82 0.00    Mobile  0.00   4.83
2026.04.29 08:54:12.0 202011  893339  5203250 5203250   XAUUSD  buy     in     0.01 4598.35  0.00  0.00  4597.93 4598.26 0.00    Mobile  0.00   0.00
2026.04.29 08:57:53.6 202011  893350  5203261 5203244   XAUUSD  sell    out    0.01 4593.04  0.00  0.00  4593.08 4593.49 0.00    Mobile  0.00  -9.16
2026.04.29 08:59:04.0 202011  893352  5203263 5203250   XAUUSD  sell    out    0.01 4592.22  0.00  0.00  4592.22 4592.65 0.00    Mobile  0.00  -6.13
2026.04.29 08:59:44.9 202011  893354  5203265 5203265   XAUUSD  buy     in     0.01 4592.75  0.00  0.00  4592.34 4592.75 0.00    Mobile  0.00   0.00
2026.04.29 08:59:52.9 202011  893355  5203266 5203265   XAUUSD  sell    out    0.01 4591.28  0.00  0.00  4591.28 4591.67 0.00    Mobile  0.00  -1.47
```

(Account 202011 ran ~347 deals, mostly micro-lot XAUUSD scalps via Mobile, holding seconds-to-minutes — exactly the population our latency-arb / scalping rules are aimed at.)

## Implications for our schemas / prompts

### 1. `DealReason` literal — DEFERRED, not adopted

The screenshot proves MT5 emits a `Reason` column with values like `mobile`,
`web`, `gateway`, `signal`, etc. that aren't in the original PRD-shaped
`DealReason` literal. **We did not adopt this expansion** because none of
the §6.3 rules in the current ruleset key on `reason`, and the broker's
documented wire schema does not include a per-trade `reason` field at all.
If a future rule needs reason-based filtering (e.g. "exclude SL/TP
close-outs from the holding-time average"), revisit then. The earlier
note also referenced a `dealer` reason value — that was invented; real
MT5 admin/dealer-placed deals come through as `gateway`.

### 2. SL/TP are stored as `0.00`, not `null`

The screenshot confirms MT5 stores unset SL/TP as `0.00`. Our schema already accepts both null and 0 (`sl: float | None = None`), so functionally we're fine. But the scalping pattern-bucket rule (SC-1 from the recent prompt review) treats null and 0 as different bucket keys — that's a real bug since real data is all `0.00`, never null.

**Action:** the SC-1 fix becomes more urgent — without it, scalping pattern detection fails on real data.

### 3. The three "Market…" columns are bid / ask / last

The truncated headers obscure them, but the values match: column 1 ≈ bid (slightly below price for buys), column 2 ≈ ask (slightly above for sells), column 3 = last (often `0.00`).

**Action:** confirm with Alex that System B's payload field names are exactly `bid`, `ask`, `last` (matching our `Deal` schema). If the field names differ, we'll need aliases on `Deal`.

### 4. Volume can be as small as 0.01 lots

Already supported by `volume: float`. Just noting that the dataset is full of micro-lots — our scalping/latency thresholds (counts, ratios) work the same regardless of size.

### 5. Time format on the wire

MT5 admin displays `2026.04.29 07:07:41.9` (period-separated, sub-second). System B is responsible for converting to ISO-8601 (`2026-04-29T07:07:41.900Z`) before posting to us — pydantic will not accept the MT5 dotted format. Worth confirming with Alex.

## Things the screenshot rules out

- No commission column visible. Either the admin's column set hides it or this user's account has zero commissions. Our schema keeps `commission: float = 0.0` either way.
- No `comment` column visible. Also either hidden or empty. Our schema defaults it to `""`.
- No `inout` or `out_by` entries in this view — the visible 347 deals all use `in`/`out`, suggesting hedging features aren't used by this account. Doesn't generalise; other accounts may.

## Open questions for Alex / K

- What's the canonical wire format for `time`? ISO-8601 with `Z`?
- Will System B include `commission` and `comment` fields (currently optional)?
- For `last` = 0.00 in MT5 admin, does System B post `0` or `null`? Both are accepted but it affects our latency-arb R3 (which skips deals with null bid/ask but treats 0.0 as a real value).
