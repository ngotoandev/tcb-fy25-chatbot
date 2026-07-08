terraform {
  required_version = ">= 1.10"
  backend "s3" {
    key          = "main/terraform.tfstate"
    use_lockfile = true
    # bucket + region supplied via -backend-config at init
  }
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}
