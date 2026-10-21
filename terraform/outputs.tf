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
