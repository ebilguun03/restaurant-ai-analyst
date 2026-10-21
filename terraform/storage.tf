# ── S3 buckets ─────────────────────────────────────────────────────────────
# raw:      Toast exports exactly as downloaded (versioned, so nothing is ever lost)
# curated:  clean JSON lines the pipeline writes, queried by Athena
# results:  where Athena saves query results (auto-deleted after 7 days)

resource "random_id" "suffix" {
  byte_length = 3 # bucket names are global across all AWS accounts
}

locals {
  name = "${var.project}-${random_id.suffix.hex}"
  buckets = {
    raw     = "${local.name}-raw"
    curated = "${local.name}-curated"
    results = "${local.name}-athena-results"
  }
}

resource "aws_s3_bucket" "this" {
  for_each      = local.buckets
  bucket        = each.value
  force_destroy = true # lets `terraform destroy` clean up fully; turn off for real production data
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each                = aws_s3_bucket.this
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "raw" {
  bucket = aws_s3_bucket.this["raw"].id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "results" {
  bucket = aws_s3_bucket.this["results"].id
  rule {
    id     = "expire-query-results"
    status = "Enabled"
    filter {}
    expiration {
      days = 7
    }
  }
}

# ── Idempotency ledger ─────────────────────────────────────────────────────
# One row per file processed, keyed by the file's fingerprint (S3 ETag).
# If the same file shows up again, the Lambda sees it here and skips it.
resource "aws_dynamodb_table" "ledger" {
  name         = "${var.project}-processed-files"
  billing_mode = "PAY_PER_REQUEST" # no fixed cost; pay per read/write (pennies)
  hash_key     = "file_etag"

  attribute {
    name = "file_etag"
    type = "S"
  }
}
