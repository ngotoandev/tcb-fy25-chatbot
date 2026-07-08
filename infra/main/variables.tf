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

locals {
  name     = "tcb-chatbot"
  app_port = 8000
  image    = "${data.aws_caller_identity.me.account_id}.dkr.ecr.${var.region}.amazonaws.com/${local.name}:${var.image_tag}"
}
