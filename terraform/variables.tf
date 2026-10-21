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
