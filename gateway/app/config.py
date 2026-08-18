from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    aws_region: str = "us-east-1"
    apps_table: str = "bedrock-platform-apps"
    rate_limits_table: str = "bedrock-platform-rate-limits"
    tenants_table: str = "bedrock-platform-tenants"
    caller_arn_header: str = "x-caller-arn"
    model_map_json: str = "{}"
    metrics_namespace: str = "BedrockPlatform"

    # Experiment / paper path. PLATFORM_TPM_BUDGET is a synthetic capacity
    # budget, not the AWS Bedrock account quota.
    admission_policy: str = "none"
    platform_tpm_budget: int = 100000
    experiment_model_id: str = "us.amazon.nova-micro-v1:0"
    estimated_backend_ttft_ms: float = 400.0
    queue_poll_ms: int = 50
    redis_url: str = ""
    results_bucket: str = ""
    run_id: str = "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
