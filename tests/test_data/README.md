# Risk scenario fixtures

One folder per `risk_key`, four representative cases each:

| Case | Theme                       |
| ---- | --------------------------- |
| 1    | Clear trigger — all rules TRUE |
| 2    | Partial — mix of TRUE/FALSE     |
| 3    | Clean — all rules FALSE         |
| 4    | Edge / `insufficient_data`      |

Each `.md` file contains:

1. Expected `risk_score` and `risk_level`.
2. A truth table mapping each sub-rule to its expected boolean.
3. A JSON envelope ready to POST at `/analyse_risk`.

## How to use

```bash
# extract the JSON block from a case file
python -c "
import re, sys, pathlib, json
md = pathlib.Path(sys.argv[1]).read_text()
body = re.search(r'\`\`\`json\n(.*?)\n\`\`\`', md, re.S).group(1)
print(body)
" tests/test_data/scalping/case1_clear_trigger.md > /tmp/payload.json

curl -s -X POST http://127.0.0.1:5050/analyse_risk \
  -H 'content-type: application/json' \
  --data @/tmp/payload.json | jq
```

> Logins are partitioned per risk to avoid history collisions:
> 801xx latency arbitrage · 802xx scalping · 803xx swap arbitrage ·
> 804xx bonus abuse.
