variable "project" {
  description = "Name prefix for every resource."
  type        = string
  default     = "restaurant-ai-analyst"
}

variable "region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-west-2"
}

variable "alert_email" {
  description = "Email for the monthly budget alert. Leave empty to skip the budget."
  type        = string
  default     = ""
}

variable "monthly_budget_usd" {
  description = "Alert when this project's AWS bill passes 80% of this amount."
  type        = number
  default     = 5
}

variable "athena_scan_limit_bytes" {
  description = "Cost guardrail: Athena cancels any single query that would scan more than this."
  type        = number
  default     = 1073741824 # 1 GB, about half a cent per query at most
}

variable "bedrock_model_id" {
  description = "Bedrock model or inference profile the analyst uses. Check Bedrock > Model catalog for the exact ID."
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "model_provider" {
  description = "Where the analyst calls Claude: \"anthropic\" (Anthropic API, key in SSM) or \"bedrock\" (needs Bedrock model access on the account)."
  type        = string
  default     = "anthropic"

  validation {
    condition     = contains(["anthropic", "bedrock"], var.model_provider)
    error_message = "model_provider must be \"anthropic\" or \"bedrock\"."
  }
}

variable "anthropic_model_id" {
  description = "Claude API model ID used when model_provider = \"anthropic\"."
  type        = string
  default     = "claude-haiku-5-5"
}

variable "anthropic_key_param" {
  description = "SSM Parameter Store name (SecureString) holding the Anthropic API key. Create it yourself so the key never lands in Terraform state."
  type        = string
  default     = "/restaurant-ai-analyst/anthropic-api-key"
}
