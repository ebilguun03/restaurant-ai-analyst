output "raw_bucket" {
  description = "Upload Toast exports to s3://<this>/toast/product_mix/"
  value       = aws_s3_bucket.this["raw"].id
}

output "curated_bucket" {
  value = aws_s3_bucket.this["curated"].id
}

output "athena_workgroup" {
  value = aws_athena_workgroup.this.name
}

output "glue_database" {
  value = aws_glue_catalog_database.this.name
}

output "transform_function" {
  value = aws_lambda_function.transform.function_name
}

output "analyst_url" {
  description = "Open this in a browser to chat with the AI analyst."
  value       = aws_apigatewayv2_api.analyst.api_endpoint
}

output "analyst_access_key" {
  description = "Paste this when the chat page asks. Show it with: terraform output -raw analyst_access_key"
  value       = random_password.access_key.result
  sensitive   = true
}
