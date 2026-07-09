# For direct-API providers (anthropic/openai), the app needs a vendor API key.
# It lives in Secrets Manager and is injected into the container as a secret env
# var (see ecs.tf `secrets`) — never as plaintext in the task definition. The
# value comes from TF_VAR_llm_api_key (a GitHub Actions secret in CI), so the key
# is never committed to the repo or printed in the task definition.
#
# Production note: the value here lands in Terraform state (encrypted S3). For
# stricter hygiene, set the value out-of-band (aws secretsmanager put-secret-value)
# and add `ignore_changes = [secret_string]` to the version resource.
resource "aws_secretsmanager_secret" "llm_api_key" {
  count                   = local.use_api_secret ? 1 : 0
  name                    = "${local.name}-llm-api-key"
  recovery_window_in_days = 0 # allow immediate delete/recreate (take-home teardown)
}

resource "aws_secretsmanager_secret_version" "llm_api_key" {
  count         = local.use_api_secret ? 1 : 0
  secret_id     = aws_secretsmanager_secret.llm_api_key[0].id
  secret_string = var.llm_api_key
}
