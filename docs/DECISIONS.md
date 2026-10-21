# Design decisions

Short records of the choices made and why. Interviewers care more about these than
about the code.

## 1. Serverless (Lambda + Athena) over a server and a database
Exports arrive monthly, data is small, and there's one user. Paying for an always-on
server or database would be waste. Revisit if data volume or users grow a lot.

## 2. Reconcile every file to Toast's grand total
Wrong numbers are worse than no numbers for a business owner. The check is cheap and
caught a real rule on day one: Toast excludes gift-card sales from its total, because
gift cards are owed back as food, not earned revenue. Gift-card rows are kept but
flagged `is_revenue = false`.

## 3. Idempotency via a DynamoDB ledger and overwrite-per-month output
S3 can deliver the same event more than once, and people re-upload files. The ledger
skips exact repeats (same ETag); a corrected export (different ETag) for the same month
overwrites that month's output file instead of adding to it, so totals stay right.

## 4. JSON lines now, Parquet later
At ~200 rows a month, JSON is easier to read and debug. Parquet would cut scan cost and
time at larger scale; switching means changing the writer and the Glue table format.

## 5. Partition by month with partition projection
Queries usually filter by month, so partitioning keeps scans small. Projection means no
Glue crawler and no `MSCK REPAIR`: a new month is queryable as soon as its file lands.

## 6. Least-privilege IAM
The Lambda can read only `raw/toast/*`, write only `curated/fact_item_sales/*`, and
read/write only its ledger table. A bug can't touch anything else.

## 7. Cost guardrails built in
A 1 GB per-query scan limit in the Athena workgroup, 7-day expiry on query results,
14-day log retention, and an optional budget email.

## 8. Real data stays out of git
The sales data belongs to the restaurant. Tests use a small fake export with the same
layout, so the repo can be public without exposing anything.
