# Bonus Abuse — Case 1: clear trigger (all 5 rules TRUE)

**Expected**: `risk_score = 100`, `risk_level = critical`.

| Sub-rule                                       | Expected | Why                                            |
| ---------------------------------------------- | -------- | ---------------------------------------------- |
| `bonus_received_in_window`                     | TRUE     | one bonus event                                |
| `trades_after_bonus_in_window >= 8`            | TRUE     | 10 trades opened after the bonus               |
| `linked_account_count >= 2`                    | TRUE     | 2 linked accounts                              |
| `linked_with_opposing_trades >= 1`             | TRUE     | both linked have opposing-side activity        |
| `withdrawal_after_bonus_in_window`             | TRUE     | a withdrawal request follows the bonus         |

Classic multi-account hedging on a deposit bonus, then withdraw.

## Payload

```json
{
  "snapshots": [
    {
      "mt5_login": 80401,
      "trigger_type": "withdrawal_request",
      "start_time": "2026-05-08T00:00:00Z",
      "end_time":   "2026-05-08T23:59:59Z",
      "bonus": [
        {"id": 1, "login": 80401, "group": "real\\bonus", "time": "2026-05-08T00:30:00Z", "profit": 200.0}
      ],
      "trades": [
        {"id": 11, "login": 80401, "group": "real\\A", "symbol": "EURUSD", "volume": 1.0, "side": "buy",
         "open_time": "2026-05-08T01:00:00Z", "time": "2026-05-08T01:30:00Z",
         "open_price": 1.08500, "close_price": 1.08600,
         "bid_at_open": 1.08498, "ask_at_open": 1.08500, "profit": 100.0}
      ],
      "withdraws": [
        {"id": 21, "login": 80401, "group": "real\\A", "time": "2026-05-08T20:00:00Z", "profit": -250.0}
      ],
      "deposits": [
        {"id": 31, "login": 80401, "group": "real\\A", "time": "2026-05-08T00:25:00Z", "profit": 100.0}
      ],
      "linked_accounts": [
        {"login": 80402, "link_reasons": ["same_ip", "same_device"], "opposing_trade_count": 8},
        {"login": 80403, "link_reasons": ["same_wallet"],            "opposing_trade_count": 4}
      ]
    }
  ],
  "include_history": false
}
```

> Replicate the trade row 10× with incrementing `id` and times after
> the bonus to satisfy R2.
