# ── Athena: query the curated files with plain SQL, no database server ─────

resource "aws_glue_catalog_database" "this" {
  name = replace(var.project, "-", "_")
}

# The fact table: one row per item per month. Athena reads the JSON files in
# s3://<curated>/fact_item_sales/month=YYYY-MM/ directly.
resource "aws_glue_catalog_table" "fact_item_sales" {
  name          = "fact_item_sales"
  database_name = aws_glue_catalog_database.this.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    classification = "json"
    # Partition projection: Athena works out the month folders itself, so new
    # months are queryable the moment the file lands. No crawler, no repair step.
    "projection.enabled"             = "true"
    "projection.month.type"          = "date"
    "projection.month.format"        = "yyyy-MM"
    "projection.month.range"         = "2024-01,NOW"
    "projection.month.interval"      = "1"
    "projection.month.interval.unit" = "MONTHS"
    "storage.location.template"      = "s3://${aws_s3_bucket.this["curated"].id}/fact_item_sales/month=$${month}/"
  }

  partition_keys {
    name = "month"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.this["curated"].id}/fact_item_sales/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
    }

    dynamic "columns" {
      for_each = [
        ["restaurant_id", "string"],
        ["item_key", "string"],
        ["item_name", "string"],
        ["menu", "string"],
        ["menu_group", "string"],
        ["subgroup", "string"],
        ["line_type", "string"],
        ["is_revenue", "boolean"],
        ["qty_sold", "int"],
        ["avg_price", "double"],
        ["gross_sales", "double"],
        ["discount_amount", "double"],
        ["refund_amount", "double"],
        ["void_amount", "double"],
        ["net_sales", "double"],
        ["tax", "double"],
        ["source_file", "string"],
      ]
      content {
        name = columns.value[0]
        type = columns.value[1]
      }
    }
  }
}

resource "aws_athena_workgroup" "this" {
  name          = var.project
  force_destroy = true

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = var.athena_scan_limit_bytes # cost guardrail

    result_configuration {
      output_location = "s3://${aws_s3_bucket.this["results"].id}/"
      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}

# Saved queries, visible under Athena > Saved queries in the console.
resource "aws_athena_named_query" "this" {
  for_each  = fileset("${path.module}/../sql", "*.sql")
  name      = trimsuffix(each.value, ".sql")
  workgroup = aws_athena_workgroup.this.id
  database  = aws_glue_catalog_database.this.name
  query     = file("${path.module}/../sql/${each.value}")
}
