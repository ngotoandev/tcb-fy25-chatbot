variable "github_repo" {
  description = "GitHub repo allowed to assume the CI role, e.g. yourname/tcb-fy25-chatbot"
  type        = string
}

variable "region" {
  type    = string
  default = "us-east-1"
}
