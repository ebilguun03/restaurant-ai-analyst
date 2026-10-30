# ── Phase 2: the AI analyst ────────────────────────────────────────────────
# Browser -> API Gateway -> Lambda (agent) -> Claude (Anthropic API or Bedrock) + Athena (read-only)
# Every question, the SQL it ran and the answer are logged to DynamoDB.

data "aws_caller_identity" "me" {}
data "aws_region" "current" {}

locals {
  account  = data.aws_caller_identity.me.account_id
  region   = data.aws_region.current.name
  model_id = var.model_provider == "anthropic" ? var.anthropic_model_id : var.bedrock_model_id
}

resource "random_password" "access_key" {
  length  = 24
  special = false
}

resource "aws_dynamodb_table" "question_log" {
  name         = "${var.project}-question-log"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }
}

data "archive_file" "analyst" {
  type        = "zip"
  source_dir  = "${path.module}/../build/analyst"
  output_path = "${path.module}/../build/analyst.zip"
}

resource "aws_cloudwatch_log_group" "analyst" {
  name              = "/aws/lambda/${var.project}-analyst"
  retention_in_days = 14
}

resource "aws_iam_role" "analyst" {
  name = "${var.project}-analyst"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# Least privilege: read the sales data, write query results, call the model, log questions.
# It has no permission to change or delete any sales data.
resource "aws_iam_role_policy" "analyst" {
  name = "analyst-access"
  role = aws_iam_role.analyst.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "WriteLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.analyst.arn}:*"
      },
      {
        Sid      = "RunAthenaQueries"
        Effect   = "Allow"
        Action   = ["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults", "athena:StopQueryExecution"]
        Resource = "arn:aws:athena:${local.region}:${local.account}:workgroup/${aws_athena_workgroup.this.name}"
      },
      {
        Sid    = "ReadCatalog"
        Effect = "Allow"
        Action = ["glue:GetDatabase", "glue:GetTable", "glue:GetTables", "glue:GetPartition", "glue:GetPartitions"]
        Resource = [
          "arn:aws:glue:${local.region}:${local.account}:catalog",
          "arn:aws:glue:${local.region}:${local.account}:database/${aws_glue_catalog_database.this.name}",
          "arn:aws:glue:${local.region}:${local.account}:table/${aws_glue_catalog_database.this.name}/*",
        ]
      },
      {
        Sid      = "ReadSalesData"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:ListBucket", "s3:GetBucketLocation"]
        Resource = [aws_s3_bucket.this["curated"].arn, "${aws_s3_bucket.this["curated"].arn}/*"]
      },
      {
        Sid      = "WriteQueryResults"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:GetBucketLocation", "s3:AbortMultipartUpload"]
        Resource = [aws_s3_bucket.this["results"].arn, "${aws_s3_bucket.this["results"].arn}/*"]
      },
      {
        Sid    = "CallModel"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = [
          "arn:aws:bedrock:*::foundation-model/*",
          "arn:aws:bedrock:*:${local.account}:inference-profile/*",
        ]
      },
      {
        Sid      = "ReadModelKey"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter"]
        Resource = "arn:aws:ssm:${local.region}:${local.account}:parameter${var.anthropic_key_param}"
      },
      {
        Sid      = "DecryptModelKey"
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = "*"
        Condition = {
          StringEquals = { "kms:ViaService" = "ssm.${local.region}.amazonaws.com" }
        }
      },
      {
        Sid      = "LogQuestions"
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem"]
        Resource = aws_dynamodb_table.question_log.arn
      },
    ]
  })
}

resource "aws_lambda_function" "analyst" {
  function_name    = "${var.project}-analyst"
  role             = aws_iam_role.analyst.arn
  runtime          = "python3.12"
  handler          = "analyst_handler.lambda_handler"
  filename         = data.archive_file.analyst.output_path
  source_code_hash = data.archive_file.analyst.output_base64sha256
  timeout          = 90
  memory_size      = 512

  environment {
    variables = {
      MODEL_PROVIDER      = var.model_provider
      MODEL_ID            = local.model_id
      ANTHROPIC_KEY_PARAM = var.anthropic_key_param
      ATHENA_WORKGROUP    = aws_athena_workgroup.this.name
      GLUE_DATABASE       = aws_glue_catalog_database.this.name
      QUESTION_LOG_TABLE  = aws_dynamodb_table.question_log.name
      ACCESS_KEY          = random_password.access_key.result
    }
  }

  depends_on = [aws_cloudwatch_log_group.analyst, aws_iam_role_policy.analyst]
}

# ── Public HTTPS endpoint with throttling (cost guardrail) ──────────────────
resource "aws_apigatewayv2_api" "analyst" {
  name          = "${var.project}-analyst"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "analyst" {
  api_id                 = aws_apigatewayv2_api.analyst.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.analyst.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000 # API Gateway's maximum; answers normally take 3-10 s
}

resource "aws_apigatewayv2_route" "page" {
  api_id    = aws_apigatewayv2_api.analyst.id
  route_key = "GET /"
  target    = "integrations/${aws_apigatewayv2_integration.analyst.id}"
}

resource "aws_apigatewayv2_route" "ask" {
  api_id    = aws_apigatewayv2_api.analyst.id
  route_key = "POST /ask"
  target    = "integrations/${aws_apigatewayv2_integration.analyst.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.analyst.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = 5 # at most 5 requests at once
    throttling_rate_limit  = 2 # and 2 per second on average
  }
}

resource "aws_lambda_permission" "api" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.analyst.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.analyst.execution_arn}/*/*"
}
