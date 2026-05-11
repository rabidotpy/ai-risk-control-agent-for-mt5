# Swap Arbitrage — Case 3: clean (no swap exposure, intraday)

**Expected**: all FALSE → `risk_score = 0`, `risk_level = low`.

Pure intraday trader; closed before 5pm NY rollover; no overnight swap.

| Sub-rule                               | Expected | Reason                                  |
| -------------------------------------- | -------- | --------------------------------------- |
| `swap_profit_ratio >= 0.6`             | FALSE    | total swap == 0                         |
| `positions_held_across_rollover >= 1`  | FALSE    | every trade opens & closes same UTC day |
| `swap_dominant_closed_positions >= 5`  | FALSE    | no `swaps > 0` trades                   |
| `average_price_movement_pnl_low`       | FALSE    | insufficient_data: no positive-swap activity |

## Payload

```json
{
  "snapshots": [
    {
      "mt5_login": 80303,
      "trigger_type": "scheduled_scan",
      "start_time": "2026-05-08T00:00:00Z",
      "end_time":   "2026-05-08T23:59:59Z",
      "trades": [
        {"id": 1, "login": 80303, "group": "real\\A", "symbol": "EURUSD", "volume": 0.5, "side": "buy",
         "open_time": "2026-05-08T01:00:00Z", "time": "2026-05-08T05:00:00Z",
         "open_price": 1.08500, "close_price": 1.08620,
         "bid_at_open": 1.08498, "ask_at_open": 1.08500,
         "swaps": 0.0, "commission": -1.0, "profit": 60.0},
        {"id": 2, "login": 80303, "group": "real\\A", "symbol": "GBPUSD", "volume": 0.5, "side": "sell",
         "open_time": "2026-05-08T08:00:00Z", "time": "2026-05-08T11:00:00Z",
         "open_price": 1.26000, "close_price": 1.25900,
         "bid_at_open": 1.26000, "ask_at_open": 1.26002,
         "swaps": 0.0, "commission": -1.0, "profit": 50.0}
      ],
      "deposits": [], "withdraws": [], "bonus": [], "linked_accounts": []
    }
  ],
  "include_history": false
}
```
