"""Export a random sample of delivered (non-reject) listings for hand labelling.

Usage: DATABASE_URL=... uv run python scripts/export_sample.py --n 200 --out sample.csv
Then fill the `label` column with `owner` or `broker` and run scripts/precision.py.
"""
import argparse
import asyncio
import csv
import os

import asyncpg


async def main(n: int, out: str) -> None:
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    rows = await conn.fetch(
        "SELECT id, url, text, verdict, verdict_stage FROM listings WHERE verdict <> 'reject' ORDER BY random() LIMIT $1",
        n)
    await conn.close()
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["listing_id", "url", "text", "verdict", "stage", "label"])
        for r in rows:
            w.writerow([r["id"], r["url"], r["text"].replace("\n", " "), r["verdict"], r["verdict_stage"], ""])
    print(f"wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--out", default="sample.csv")
    a = p.parse_args()
    asyncio.run(main(a.n, a.out))
