output "ci_role_arn" { value = aws_iam_role.ci.arn }
output "tfstate_bucket" { value = aws_s3_bucket.tfstate.bucket }
output "ecr_repo_url" { value = aws_ecr_repository.app.repository_url }
