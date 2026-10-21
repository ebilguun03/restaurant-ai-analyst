#!/usr/bin/env bash
# Run a .sql file in Athena from the terminal and print the result.
#   ./scripts/athena.sh sql/01_create_dim_menu_item.sql
set -euo pipefail
export AWS_PAGER=""  # print results straight to the terminal instead of a scrolling viewer
cd "$(dirname "$0")/.."

WG=$(terraform -chdir=terraform output -raw athena_workgroup)
DB=$(terraform -chdir=terraform output -raw glue_database)

id=$(aws athena start-query-execution --work-group "$WG" \
  --query-execution-context Database="$DB" \
  --query-string "$(cat "$1")" --output text --query QueryExecutionId)

while true; do
  state=$(aws athena get-query-execution --query-execution-id "$id" \
    --output text --query QueryExecution.Status.State)
  case "$state" in
    SUCCEEDED) break ;;
    FAILED|CANCELLED)
      aws athena get-query-execution --query-execution-id "$id" \
        --output text --query QueryExecution.Status.StateChangeReason
      exit 1 ;;
    *) sleep 1 ;;
  esac
done

aws athena get-query-execution --query-execution-id "$id" --output text \
  --query 'QueryExecution.[Statistics.TotalExecutionTimeInMillis,Statistics.DataScannedInBytes]' \
  | awk '{printf "Done in %d ms, scanned %d bytes\n", $1, $2}'
aws athena get-query-results --query-execution-id "$id" --max-items 26 \
  --query 'ResultSet.Rows[*].[Data[*].VarCharValue]' --output text 2>/dev/null \
  | column -t -s $'\t' || true
