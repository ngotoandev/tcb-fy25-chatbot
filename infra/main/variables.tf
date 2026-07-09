variable "region" {
  type    = string
  default = "us-east-1"
}

variable "image_tag" {
  description = "Docker image tag (git SHA) to deploy"
  type        = string
}

variable "alert_email" {
  description = "Email for the budget alert"
  type        = string
}

variable "budget_limit" {
  type    = string
  default = "10"
}

variable "llm_provider" {
  description = "bedrock (Nova + Titan) | anthropic | openai. Non-bedrock uses BM25-only retrieval and needs llm_api_key."
  type        = string
  default     = "bedrock"
}

variable "llm_api_key" {
  description = "Vendor API key for anthropic/openai providers. Supplied via CI (a GitHub Actions secret); empty for bedrock."
  type        = string
  default     = ""
  sensitive   = true
}

locals {
  name     = "tcb-chatbot"
  app_port = 8000
  image    = "${data.aws_caller_identity.me.account_id}.dkr.ecr.${var.region}.amazonaws.com/${local.name}:${var.image_tag}"
  # Direct-API providers need a vendor key injected as a container secret.
  use_api_secret = var.llm_provider != "bedrock"
  api_key_env    = { anthropic = "ANTHROPIC_API_KEY", openai = "OPENAI_API_KEY" }
}
