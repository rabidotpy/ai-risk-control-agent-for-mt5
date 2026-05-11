# Scalping — Case 4: insufficient_data (very few trades)

**Expected**: all FALSE; R3 and R4 cite `insufficient_data` (fewer than
5 trades for win-rate, fewer than 3 for pattern).

| Sub-rule                                       | Expected | Reason                                        |
| ---------------------------------------------- | -------- | --------------------------------------------- |
| `trade_count_in_window >= 25`                  | FALSE    | only 2 trades                                 |
| `short_holding_ratio_60s >= 0.7`               | TRUE/FALSE | both held < 60s → ratio 1.0 (TRUE) BUT below count thresholds for the others |
| `win_rate >= 0.75`                             | FALSE    | insufficient_data: fewer than 5 trades        |
| `repeated_lot_sl_tp_pattern_ratio >= 0.5`      | FALSE    | insufficient_data: fewer than 3 trades        |

> Even though R2 may resolve TRUE on a 100% short-hold ratio, the score
> stays at 25 (1/4) → level `low`. Use this case to verify the
> `insufficient_data` reason strings appear on R3/R4 in `evidence`.

## Payload

```json
{
  "snapshots": [
    {
      "mt5_login": 80204,
      "trigger_type": "manual_run",
      "start_time": "2026-05-08T00:00:00Z",
      "end_time":   "2026-05-08T05:59:59Z",
      "trades": [
        {"id": 1, "login": 80204, "group": "real\\A", "symbol": "EURUSD", "volume": 0.10, "side": "buy",
         "open_time": "2026-05-08T00:00:00Z", "time": "2026-05-08T00:00:30Z",
         "open_price": 1.08500, "close_price": 1.08510,
         "bid_at_open": 1.08498, "ask_at_open": 1.08500, "profit": 1.0},
        {"id": 2, "login": 80204, "group": "real\\A", "symbol": "EURUSD", "volume": 0.10, "side": "sell",
         "open_time": "2026-05-08T00:05:00Z", "time": "2026-05-08T00:05:45Z",
         "open_price": 1.08520, "close_price": 1.08510,
         "bid_at_open": 1.08520, "ask_at_open": 1.08522, "profit": 1.0}
      ],
      "deposits": [], "withdraws": [], "bonus": [], "linked_accounts": []
    }
  ],
  "include_history": false
}
```
