# ── The transform function ─────────────────────────────────────────────────
# Build the package first: ./scripts/build_lambda.sh  (puts code + openpyxl in build/lambda)

data "archive_file" "transform" {
  type        = "zip"
  source_dir  = "${path.module}/../build/lambda"
  output_path = "${path.module}/../build/transform.zip"
}

resource "aws_cloudwatch_log_group" "transform" {
  name              = "/aws/lambda/${var.project}-transform"
  retention_in_days = 14
}

resource "aws_iam_role" "transform" {
  name = "${var.project}-transform"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# Least privilege: the function can only do exactly what it needs.
resource "aws_iam_role_policy" "transform" {
  name = "transform-access"
  role = aws_iam_role.transform.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "WriteLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.transform.arn}:*"
      },
      {
        Sid      = "ReadRawExports"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.this["raw"].arn}/toast/*"
      },
      {
        Sid      = "WriteCuratedData"
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${aws_s3_bucket.this["curated"].arn}/fact_item_sales/*"
      },
      {
        Sid      = "UseLedger"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem"]
        Resource = aws_dynamodb_table.ledger.arn
      },
    ]
  })
}

resource "aws_lambda_function" "transform" {
  function_name    = "${var.project}-transform"
  role             = aws_iam_role.transform.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.transform.output_path
  source_code_hash = data.archive_file.transform.output_base64sha256
  timeout          = 60
  memory_size      = 512

  environment {
    variables = {
      CURATED_BUCKET = aws_s3_bucket.this["curated"].id
      LEDGER_TABLE   = aws_dynamodb_table.ledger.name
    }
  }

  depends_on = [aws_cloudwatch_log_group.transform, aws_iam_role_policy.transform]
}

# ── Trigger: run the function whenever a Toast export lands in raw/ ────────
resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowRawBucketInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.transform.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.this["raw"].arn
}

resource "aws_s3_bucket_notification" "raw" {
  bucket = aws_s3_bucket.this["raw"].id

  lambda_function {
    lambda_function_arn = aws_lambda_function.transform.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "toast/product_mix/"
    filter_suffix       = ".xlsx"
  }

  depends_on = [aws_lambda_permission.allow_s3]
}

# ── Monitoring: count files the pipeline refused (bad format, totals off) ──
resource "aws_cloudwatch_log_metric_filter" "rejected" {
  name           = "${var.project}-rejected-files"
  log_group_name = aws_cloudwatch_log_group.transform.name
  pattern        = "{ $.event = \"rejected\" }"

  metric_transformation {
    name      = "RejectedFiles"
    namespace = var.project
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "rejected" {
  alarm_name          = "${var.project}-rejected-files"
  alarm_description   = "A Toast export was rejected. Check the transform logs for the reason."
  namespace           = var.project
  metric_name         = "RejectedFiles"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
}
