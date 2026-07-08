provider "aws" {
  region = var.region
  default_tags { tags = { project = "tcb-chatbot", stack = "main" } }
}

data "aws_caller_identity" "me" {}
