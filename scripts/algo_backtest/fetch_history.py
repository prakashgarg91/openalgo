import sys
import time

import yfinance as yf

out = sys.argv[1]
syms = {
    "nsei": "^NSEI",
    "vix": "^INDIAVIX",
    "spx": "^GSPC",
    "ndx": "^IXIC",
    "crude": "CL=F",
    "dxy": "DX-Y.NYB",
}
for name, sym in syms.items():
    for attempt in range(6):
        df = yf.download(
            sym, start="2018-01-01", end="2026-10-27", auto_adjust=False, progress=False
        )
        if len(df):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            df.to_csv(f"{out}/{name}.csv")
            print(name, len(df), df.index.min().date(), df.index.max().date(), flush=True)
            break
        print(name, "retry", attempt, flush=True)
        time.sleep(20 * (attempt + 1))
    else:
        print(name, "FAILED")
