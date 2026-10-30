# Phase 1 build guide

Work through one step at a time. Each step says what to do, what you're learning,
and how to say it in an interview. Don't move on until you could explain the step
to a friend without looking.

Budget: about 1–2 hours a day for 2 weeks. AWS cost: under $1 if you follow step 9.

---

## Step 0. Set up your tools (30 min)

```bash
brew install awscli terraform python@3.12
cd ~/my-workspace/ozora-app/restaurant-ai-analyst
python3 -m venv .venv && source .venv/bin/activate
pip install -r src/transform/requirements.txt -r requirements-dev.txt
cp ../hearth-app/scripts/ProductMix_*.xlsx data/raw/
```

## Step 1. Run it locally and read the code (day 1–2)

```bash
pytest -q
python scripts/run_local.py data/raw/*.xlsx
```

You should see three months, each "matches Toast within $0.00".

Read `src/transform/toast_parser.py` top to bottom. Then open one export in Excel
and find the rows the code keeps and skips.

**What you're learning:** ETL (extract, transform, load), and data validation.

**Things to notice:**
- The "All levels" sheet mixes real items with subtotal rows. We keep only item rows
  and recompute subtotals ourselves.
- **Gift cards aren't revenue.** Toast leaves them out of its grand total, because the
  money is owed back later as food. Our first version counted them and the totals
  didn't match. That mismatch is why the reconciliation check exists. This is a great
  interview story: the check caught a real business rule.

**Interview line:** "Before loading anything, the pipeline checks that the cleaned
rows add up to Toast's own total, to the cent. If they don't, the file is rejected
instead of quietly putting wrong numbers in front of the owner."

## Step 2. Understand the tests (day 2)

Read `tests/test_parser.py`, then `tests/test_handler.py`. The handler tests use
**moto**, which fakes S3 and DynamoDB in memory, so you can test AWS code without
an AWS account.

Break something on purpose (e.g. delete the `if line_type not in KEEP_TYPES` check)
and watch a test fail. Then undo it.

**Interview line:** "I split the pure parsing logic from the AWS code, so most of it
is tested in milliseconds, and I test the Lambda end to end against mocked AWS."

## Step 3. Create your AWS account safely (day 3)

1. Sign up at aws.amazon.com. New accounts get free-tier credits.
2. **Turn on MFA for the root user**, then never use root again.
3. In IAM Identity Center, create a user for yourself with AdministratorAccess.
4. `aws configure sso`, then `aws sts get-caller-identity` to check it works.

**Cloud Practitioner topics covered:** shared responsibility model, IAM users vs roles,
MFA, least privilege, root account protection.

## Step 4. Read the Terraform before running it (day 3–4)

Read the files in `terraform/` in this order: `variables.tf`, `storage.tf`,
`lambda.tf`, `analytics.tf`, `budget.tf`. For every resource, say out loud what it
is and why it's there.

| Resource | Plain English |
|---|---|
| S3 buckets | Folders in the cloud. raw = untouched originals, curated = clean data |
| Versioning on raw | Every upload is kept, even if overwritten |
| DynamoDB ledger | A list of files already processed, so nothing counts twice |
| IAM role + policy | The Lambda's permission slip: read raw, write curated, nothing else |
| Lambda | Runs our Python only when a file arrives; costs nothing when idle |
| S3 notification | The trigger that calls the Lambda on upload |
| Glue table | Tells Athena what columns the JSON files have |
| Partition projection | Athena finds new months by itself, no extra step |
| Athena workgroup | Where queries run, with a 1 GB scan limit per query |
| Budget | Emails you before costs surprise you |

**Interview line:** "All of it is defined in Terraform, so anyone can recreate the
whole environment with one command, and `terraform destroy` removes it cleanly."

## Step 5. Deploy (day 5)

```bash
./scripts/build_lambda.sh
terraform -chdir=terraform init
terraform -chdir=terraform plan   # read this! it lists everything it will create
terraform -chdir=terraform apply -var="alert_email=you@example.com"
```

Then open the AWS console and find each thing you created: the buckets, the Lambda,
the DynamoDB table, the Athena workgroup.

## Step 6. Run the pipeline in the cloud (day 6)

```bash
./scripts/upload.sh data/raw/*.xlsx
aws logs tail /aws/lambda/restaurant-ai-analyst-transform --since 10m
```

Look for the `"event": "processed"` log lines and note the `seconds` field. **That's
your processing-time number for the resume.**

Now upload the same file again. You should see `skipped_duplicate`. Then upload a
random .xlsx renamed as a Toast export and watch it get `rejected` and the alarm
change state in CloudWatch.

**Interview line:** "S3 events can be delivered more than once, so I made the pipeline
idempotent: a DynamoDB ledger keyed on the file's fingerprint, and one output file per
month that gets overwritten, not appended."

## Step 7. Query it (day 7–8)

```bash
./scripts/athena.sh sql/01_create_dim_menu_item.sql
./scripts/athena.sh sql/02_create_monthly_summary.sql
./scripts/athena.sh sql/top_and_bottom_items.sql
./scripts/athena.sh sql/menu_group_month_over_month.sql
./scripts/athena.sh sql/discount_and_void_leaks.sql
```

Note the "Done in X ms, scanned Y bytes" line for each. Then write 3 queries of your
own that TJ would care about.

**What you're learning:** a star schema. `fact_item_sales` holds the numbers (what
was sold, how much); `dim_menu_item` describes each item. Facts are joined to
dimensions to answer questions.

**Findings already in the data (Jan–Mar 2026), good for interviews:**
- Net sales grew about 13% from January ($66.2K) to March ($74.9K).
- Specialty Rolls hold the top 4 items by revenue.
- Voids nearly doubled from January to February. That's a question worth asking the owner.

## Step 8. Write it up (day 9–10)

1. Push to GitHub (check that `data/raw/` is not committed: `git status`).
2. Take screenshots: the Lambda logs, an Athena query result, the architecture diagram.
3. Fill in the resume bullets below with your real measured numbers.

## Step 9. Keep costs at zero

Everything is pay-per-use, so idle cost is close to $0. If you're pausing for weeks:
`terraform -chdir=terraform destroy`. Re-deploying takes about 2 minutes.

---

## Resume bullets (fill in after step 6–7)

- Built a **serverless ETL pipeline on AWS** (S3, Lambda, DynamoDB, Athena) that turns a
  restaurant's raw Toast POS exports into a **queryable sales warehouse**, processing each
  month's file in **under [X] seconds**.
- Added a **data-quality gate** that reconciles every file to the POS's own totals **to the
  cent** and an **idempotent DynamoDB ledger** so retries never double count.
- Modeled **3 months of real sales data (about 20K items sold)** as a **star schema**,
  with SQL analyses that surfaced **13% sales growth** and a **2x jump in voids**.
- Defined all infrastructure in **Terraform** with **CI in GitHub Actions** and **cost
  guardrails** (per-query scan limit, budget alerts), running at **under $[X]/month**.

## Questions interviewers will ask, and your answers

- **Why Lambda instead of a server?** Files arrive about once a month. A server would sit
  idle and cost money 24/7; Lambda runs only when needed and costs nearly nothing.
- **Why Athena instead of a database like Postgres?** The data is small and read-mostly.
  Athena queries files in S3 directly, with nothing to run or patch. If the owner needed
  a live dashboard with many users, I'd look at Redshift or Snowflake.
- **Why JSON lines and not Parquet?** Simplicity at this size. Parquet is columnar and
  compressed, so it's cheaper and faster at scale. It's the first thing I'd change with
  more data. (Good to show you know the tradeoff.)
- **What happens if a bad file is uploaded?** The parser rejects it, logs the reason,
  and a CloudWatch alarm fires. Nothing wrong reaches the curated data.
- **What would you do with more time?** Phase 2: an AI agent that answers the owner's
  questions in plain English, then a test set to measure how often it's right.
