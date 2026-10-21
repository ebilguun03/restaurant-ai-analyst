"""Run the transform on your laptop, no AWS needed.

    python scripts/run_local.py data/raw/*.xlsx

Prints a check for each file and writes the clean rows to data/curated/,
in the same layout the Lambda writes to S3.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "transform"))

from toast_parser import ParseError, parse_product_mix  # noqa: E402


def main(paths):
    if not paths:
        print(__doc__)
        return 1
    total_rows = 0
    started = time.time()
    for path in map(Path, paths):
        try:
            result = parse_product_mix(path.read_bytes(), path.name)
        except ParseError as exc:
            print(f"REJECTED {path.name}: {exc}")
            continue
        out = ROOT / "data" / "curated" / "fact_item_sales" / f"month={result['month']}"
        out.mkdir(parents=True, exist_ok=True)
        rid = result["restaurant"]["restaurant_id"]
        with open(out / f"{rid}.jsonl", "w", encoding="utf-8") as fh:
            for row in result["rows"]:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        c = result["check"]
        total_rows += c["rows"]
        print(f"OK {result['month']} {rid}: {c['rows']} rows, {c['qty_sold']:,} sold, "
              f"${c['net_sales']:,.2f} net (matches Toast within ${c['net_diff']:.2f})")
    print(f"{total_rows} rows in {time.time() - started:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
