# Latency Arbitrage — Case 2: partial (R1 + R4 TRUE, R2/R3 FALSE)

**Expected**: 2/4 sub-rules TRUE → `risk_score = 50`, `risk_level = watch`.

| Sub-rule                                 | Expected | Why                                  |
| ---------------------------------------- | -------- | ------------------------------------ |
| `trade_count_6h >= 30`                   | TRUE     | 30 trades                            |
| `median_holding_time_seconds <= 30`      | FALSE    | median ~120s                         |
| `positive_slippage_ratio >= 0.5`         | FALSE    | buys filled at the ask, no edge      |
| `short_holding_ratio_30s >= 0.6`         | TRUE     | majority closed within 30s anyway    |

Many short trades, but slippage is neutral and the median creeps above
30s because a quarter of trades are held 2-5 minutes. Looks like an
active scalper, not latency arb.

## Payload (representative trade — duplicate to 30, vary holding time)

```json
{
  "snapshots": [
    {
      "mt5_login": 80102,
      "trigger_type": "manual_run",
      "start_time": "2026-05-08T00:00:00Z",
      "end_time":   "2026-05-08T05:59:59Z",
      "trades": [
        {"id": 1, "login": 80102, "group": "real\\A", "symbol": "GBPUSD", "volume": 0.5, "side": "buy",
         "open_time": "2026-05-08T00:00:00Z", "time": "2026-05-08T00:00:25Z",
         "open_price": 1.26000, "close_price": 1.26008,
         "bid_at_open": 1.25998, "ask_at_open": 1.26000, "profit": 4.0}
      ],
      "deposits": [], "withdraws": [], "bonus": [], "linked_accounts": []
    }
  ],
  "include_history": false
}
```

> Construct 30 rows. Set 8 of them with `time` = open_time + 3min (so
> the median crosses 30s but `short_holding_ratio_30s` stays > 0.6).
> Keep `open_price == ask_at_open` on every row to suppress R3.
