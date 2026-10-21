#!/usr/bin/env bash
# Upload Toast exports to the raw bucket. The upload itself triggers the pipeline.
#   ./scripts/upload.sh data/raw/*.xlsx
set -euo pipefail
cd "$(dirname "$0")/.."

RAW_BUCKET=$(terraform -chdir=terraform output -raw raw_bucket)
for f in "$@"; do
  aws s3 cp "$f" "s3://${RAW_BUCKET}/toast/product_mix/$(basename "$f")"
done
echo "Uploaded $# file(s). Check progress: aws logs tail /aws/lambda/restaurant-ai-analyst-transform --follow"
