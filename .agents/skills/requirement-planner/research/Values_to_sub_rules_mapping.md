Here is the inverse mapping. For every sub rule across the four risks I'll cover what it means in plain English, the MT5 values it needs, how those values combine into the True or False answer, and whether it can fire today.

Latency Arbitrage (4 sub rules)
trade_count_6h >= 30
Plain English. Did the trader open at least 30 positions in the last 6 hours?

Values it needs.

trades array (one row per closed position in the 6 hour window)
time on each trade row (so we know it falls inside the window)
How they combine. Just count the number of rows in trades. The 6 hour window is already the call's window, so no time filtering is needed. True if the count is at least 30.

Status. Lives. Already on Alex's wire.

median_holding_time <= 30 seconds
Plain English. Half or more of this trader's positions were held for under 30 seconds.

Values it needs.

open_time on each trade
close_time on each trade (this is what Alex's time field probably is, but he needs to confirm)
How they combine. For every trade compute holding_seconds = close_time - open_time. Take the median across all trades. True if the median is at most 30.

Status. Blocked because Alex only sends one timestamp called time. Until he adds the second timestamp and tells us which one is which, holding seconds cannot be computed.

positive_slippage_ratio >= 0.5
Plain English. More than half of the trader's entries were filled at a better price than the market was showing at that moment.

Values it needs.

Per trade direction (buy or sell)
Per trade price (the fill)
Per trade bid_at_open and ask_at_open (the market quote at the moment of the open)
How they combine. For each trade where bid and ask are not null, decide if the fill was favourable. For a buy that means price < ask_at_open. For a sell it means price > bid_at_open. Count favourable fills, divide by the count of evaluable trades, and the rule fires if the ratio is at least 0.5.

Status. Blocked. Direction, bid at open, and ask at open are all missing from Alex's wire.

short_holding_ratio_30s >= 0.6
Plain English. At least 60 percent of positions were closed within 30 seconds of being opened.

Values it needs.

open_time and close_time on each trade (so we can derive holding_seconds)
How they combine. Count trades whose holding seconds are at most 30. Divide by total trade count. True if the ratio is at least 0.6.

Status. Blocked, same root cause as median_holding_time. Needs open_time from Alex.

Scalping Violation (4 sub rules)
trade_count_24h >= 100
Plain English. The trader opened at least 100 positions in the last 24 hours.

Values it needs.

Trades from the last 24 hours, just to count them
A timestamp on each trade so we can verify the trade is inside the 24 hour window
How they combine. Count trades whose open time is within the last 24 hours of end_time. True if the count is at least 100.

Status. Blocked by window. Each Alex call gives us 6 hours, so we cannot see the full 24 hours from one call. We solve this internally by aggregating four consecutive stored 6 hour pulls into a 24 hour view. No request to Alex is needed.

short_holding_ratio_60s >= 0.7
Plain English. At least 70 percent of positions were held for 60 seconds or less.

Values it needs.

open_time and close_time on each trade
How they combine. Count trades with holding seconds at most 60, divide by total. True if the ratio is at least 0.7.

Status. Blocked by holding seconds. Needs open_time from Alex.

win_rate >= 0.75
Plain English. At least 75 percent of closed positions were profitable.

Values it needs.

profit on each closed trade
How they combine. Count trades with profit > 0, divide by total. True if the ratio is at least 0.75. We require at least 5 closed positions for the answer to be meaningful, otherwise we report insufficient_data.

Status. Lives. Profit is on Alex's wire.

repeated_lot_sl_tp_pattern_present
Plain English. A large share of the trader's positions share the exact same volume, stop loss and take profit triple, suggesting an automated pattern.

Values it needs.

volume on each trade
stop_loss on each trade
take_profit on each trade
How they combine. Bucket trades by the triple (volume, stop_loss, take_profit), treating 0 and null as the same value (both meaning unset). A pattern bucket has 3 or more trades. Count trades that belong to any pattern bucket and divide by total. True if the ratio is at least 0.5.

Status. Lives. All three fields are on Alex's wire.

Swap Arbitrage (4 sub rules)
swap_profit_ratio >= 0.6
Plain English. At least 60 percent of the trader's net profit came from swap interest, not from price movement.

Values it needs.

swaps on each trade
profit on each trade
How they combine. Sum swaps and sum profit across all trades in the window. The ratio is total_swap / total_profit, only computed when total profit is positive. True if the ratio is at least 0.6.

Status. Lives on the per pull window. Cleaner over a 30 day window once we aggregate stored pulls.

positions_held_across_rollover >= 1
Plain English. At least one position was held across a daily rollover, which is when the broker posts overnight interest.

Values it needs.

open_time on each trade
close_time on each trade
How they combine. A trade spans rollover if its open and close fall on different UTC calendar dates. Count those trades. True if the count is at least 1. (UTC midnight is a rough proxy for the broker's actual rollover hour. If the broker uses a different server time we'll need to adjust.)

Status. Blocked. Needs open_time from Alex.

swap_dominant_closed_positions >= 5
Plain English. At least 5 positions look like pure carry trades, where positive swap is the bulk of the profit and price movement is essentially flat.

Values it needs.

profit on each trade
swaps on each trade
commission on each trade (assumed 0 if missing)
How they combine. For each trade compute price_pnl = profit - swaps - commission. The trade is swap dominant if swaps > 0 AND abs(price_pnl) <= 0.1 \* swaps. Count swap dominant trades. True if the count is at least 5.

Status. Lives, with the small caveat that commission is assumed 0 when not provided.

average_price_movement_pnl_low
Plain English. Looking at all positions with positive swap, the price movement portion of profit is small compared to the swap portion. The trader is not making meaningful directional money.

Values it needs.

profit, swaps, commission on each trade with positive swap
How they combine. For trades with swaps > 0, sum price_pnl across them and sum swaps across them. Compute ratio = total_price_pnl / total_positive_swap. True if the ratio is between minus 0.2 and plus 0.2 inclusive.

Status. Lives, same commission caveat as the rule above.

Bonus / Credit Abuse (5 sub rules)
bonus_active_within_30_days
Plain English. The trader received at least one bonus in the last 30 days.

Values it needs.

bonus array
time on each bonus event
How they combine. Check if any bonus event has a time greater than or equal to end_time - 30 days. True if at least one such event exists.

Status. Blocked by window. We currently only see in-window bonuses (last 6 hours). Solved internally by aggregating bonus rows across the last 120 stored 6 hour pulls (30 days). No request to Alex is needed.

trades_within_24h_of_bonus >= 30
Plain English. After the most recent bonus the trader opened at least 30 positions inside 24 hours.

Values it needs.

bonus array with timestamps (to find the most recent bonus event)
open_time on each trade (to count trades inside the 24 hour window after the bonus)
How they combine. Find bonus.time for the most recent bonus event. Count trades whose open time falls in [bonus.time, bonus.time + 24h]. True if the count is at least 30.

Status. Blocked by open_time (also needs the 24 hour window which we'll get from DB aggregation, plus the bonus history that B1 also depends on).

linked_account_count >= 2
Plain English. At least 2 other accounts are linked to this one through shared IP, device, wallet, IB, or KYC identity.

Values it needs.

A list of linked logins per account (not in the MT5 deal stream)
How they combine. Just len(linked_accounts) >= 2.

Status. Blocked. Linkage data sits outside the MT5 deal stream. The MT5 platform's login audit gives us shared IP and device. The broker's CRM gives us shared wallet, IB code, and KYC name. Alex needs to expose this, probably as its own endpoint.

linked_with_opposing_trades >= 1
Plain English. At least one of the linked accounts is running trades on the opposite side of the same instruments, which is the multi account hedging signal.

Values it needs.

The linked accounts list (from B3)
Trade activity on each linked account, with direction
How they combine. For each linked account, check if it has positions whose direction is opposite to this account's positions on the same symbol. Count linked accounts that meet that condition. True if the count is at least 1.

Status. Blocked, same root as B3. Once Alex exposes linked accounts, this rule needs the direction and symbol on the linked account's recent trades too.

withdrawal_within_72h_of_bonus
Plain English. The trader requested a withdrawal within 72 hours after receiving a bonus.

Values it needs.

bonus array with timestamps
withdraws array with timestamps
How they combine. Find the most recent bonus event. Find the earliest withdraw whose time is greater than or equal to the bonus time. Compute hours_between = (withdraw.time - bonus.time) / 3600. True if such a withdrawal exists AND hours_between <= 72.

Status. Lives within a single 6 hour window when both bonus and withdrawal land in the same window. Improves once DB aggregation lets us match bonuses from earlier windows to withdrawals in the current window.

Quick scoreboard
Rule Status Why
trade_count_6h >= 30 Lives Just count trades
median_holding_time <= 30 seconds Blocked Needs open_time from Alex
positive_slippage_ratio >= 0.5 Blocked Needs direction + bid/ask at open from Alex
short_holding_ratio_30s >= 0.6 Blocked Needs open_time from Alex
trade_count_24h >= 100 Blocked by window Solve via DB aggregation across 4 stored pulls
short_holding_ratio_60s >= 0.7 Blocked Needs open_time from Alex
win_rate >= 0.75 Lives profit is on the wire
repeated_lot_sl_tp_pattern_present Lives volume, SL, TP all on the wire
swap_profit_ratio >= 0.6 Lives swaps + profit on the wire
positions_held_across_rollover >= 1 Blocked Needs open_time from Alex
swap_dominant_closed_positions >= 5 Lives swaps + profit on the wire (commission assumed 0)
average_price_movement_pnl_low Lives same as above
bonus_active_within_30_days Blocked by window Solve via DB aggregation across 120 stored pulls
trades_within_24h_of_bonus >= 30 Blocked Needs open_time from Alex (plus 24h aggregation)
linked_account_count >= 2 Blocked Needs linked accounts data from Alex
linked_with_opposing_trades >= 1 Blocked Needs linked accounts data from Alex
withdrawal_within_72h_of_bonus Lives bonus + withdraws on the wire
So out of 17 sub rules, 7 are alive today on Alex's documented schema, 2 are blocked only by our own DB aggregation work (no Alex dependency), and 8 need fields Alex has to add. The four asks in his message cover all 8 of those Alex blockers.
