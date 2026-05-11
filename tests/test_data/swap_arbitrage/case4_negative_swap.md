# Swap Arbitrage — Case 4: negative-swap carry (rule R3 must NOT trigger)

**Expected**: only R2 TRUE → `risk_score = 25`, `risk_level = low`.

Edge case: trader is on the wrong side of carry — paying negative swap.
R3 explicitly excludes negative-swap trades, so it must stay FALSE.

| Sub-rule                               | Expected | Why                                              |
| -------------------------------------- | -------- | ------------------------------------------------ |
| `swap_profit_ratio >= 0.6`             | FALSE    | total swap is negative                           |
| `positions_held_across_rollover >= 1`  | TRUE     | trades span 2+ UTC days                          |
| `swap_dominant_closed_positions >= 5`  | FALSE    | every trade has `swaps < 0` → excluded           |
| `average_price_movement_pnl_low`       | FALSE    | insufficient_data: no positive-swap activity     |

## Payload

```json
{
  "snapshots": [
    {
      "mt5_login": 80304,
      "trigger_type": "scheduled_scan",
      "start_time": "2026-05-05T00:00:00Z",
      "end_time":   "2026-05-08T23:59:59Z",
      "trades": [
        {"id": 1, "login": 80304, "group": "real\\A", "symbol": "AUDJPY", "volume": 1.0, "side": "sell",
         "open_time": "2026-05-05T08:00:00Z", "time": "2026-05-06T08:00:00Z",
         "open_price": 100.00, "close_price": 99.95,
         "bid_at_open": 100.00, "ask_at_open": 100.01,
         "swaps": -18.0, "commission": -2.0, "profit": 30.0},
        {"id": 2, "login": 80304, "group": "real\\A", "symbol": "AUDJPY", "volume": 1.0, "side": "sell",
         "open_time": "2026-05-06T08:00:00Z", "time": "2026-05-07T08:00:00Z",
         "open_price": 100.05, "close_price": 99.90,
         "bid_at_open": 100.05, "ask_at_open": 100.06,
         "swaps": -18.0, "commission": -2.0, "profit": 130.0}
      ],
      "deposits": [], "withdraws": [], "bonus": [], "linked_accounts": []
    }
  ],
  "include_history": false
}
```
