# Scalping — Case 2: high freq + short holds, but no pattern, mixed wins

**Expected**: 2/4 TRUE → `risk_score = 50`, `risk_level = watch`.

| Sub-rule                                       | Expected | Why                                       |
| ---------------------------------------------- | -------- | ----------------------------------------- |
| `trade_count_in_window >= 25`                  | TRUE     | 30 trades                                 |
| `short_holding_ratio_60s >= 0.7`               | TRUE     | most trades < 60s                         |
| `win_rate >= 0.75`                             | FALSE    | ~50% wins                                 |
| `repeated_lot_sl_tp_pattern_ratio >= 0.5`      | FALSE    | varied volumes; no SL/TP                  |

Discretionary scalper, not an EA.

## Payload

```json
{
  "snapshots": [
    {
      "mt5_login": 80202,
      "trigger_type": "manual_run",
      "start_time": "2026-05-08T00:00:00Z",
      "end_time":   "2026-05-08T05:59:59Z",
      "trades": [
        {"id": 1, "login": 80202, "group": "real\\A", "symbol": "EURUSD", "volume": 0.10, "side": "buy",
         "open_time": "2026-05-08T00:00:00Z", "time": "2026-05-08T00:00:40Z",
         "open_price": 1.08500, "close_price": 1.08515,
         "bid_at_open": 1.08498, "ask_at_open": 1.08500, "profit": 1.5},
        {"id": 2, "login": 80202, "group": "real\\A", "symbol": "EURUSD", "volume": 0.20, "side": "sell",
         "open_time": "2026-05-08T00:01:00Z", "time": "2026-05-08T00:01:30Z",
         "open_price": 1.08520, "close_price": 1.08535,
         "bid_at_open": 1.08520, "ask_at_open": 1.08522, "profit": -3.0}
      ],
      "deposits": [], "withdraws": [], "bonus": [], "linked_accounts": []
    }
  ],
  "include_history": false
}
```

> Replicate to 30 rows. Vary `volume` between 0.10/0.20/0.30, alternate
> winners/losers, leave `stop_loss` and `take_profit` at 0.
