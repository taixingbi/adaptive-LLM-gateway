from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    aws_region: str = "us-east-1"
    apps_table: str = "bedrock-platform-apps"
    rate_limits_table: str = "bedrock-platform-rate-limits"
    caller_arn_header: str = "x-caller-arn"
    model_map_json: str = "{}"
    metrics_namespace: str = "BedrockPlatform"


@lru_cache
def get_settings() -> Settings:
    return Settings()
