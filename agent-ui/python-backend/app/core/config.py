"""
Configuration management for the Python backend
"""

import os
from enum import Enum
from typing import List
from pydantic_settings import BaseSettings


class SecurityLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Settings(BaseSettings):
    """Application settings"""

    # Server Configuration
    PORT: int = 8003
    HOST: str = "0.0.0.0"

    # CORS Configuration
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000"

    # Logging
    LOG_LEVEL: str = "INFO"

    # Security Configuration
    DEFAULT_SECURITY_LEVEL: str = "medium"

    # Model Configuration
    MODEL_CACHE_DIR: str = "./models"
    USE_GPU: str = "auto"

    # Ollama (local LLM) Configuration
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2"

    # Database Configuration
    DATABASE_URL: str = "sqlite+aiosqlite:///./securemcp.db"

    # JWT Configuration
    JWT_SECRET: str = "change-this-in-production-use-a-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 1440  # 24 hours
    JWT_REFRESH_EXPIRY_DAYS: int = 7

    # Privacy: set to True to store raw prompt text in audit_events (off by default)
    STORE_RAW_PROMPTS: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def security_level(self) -> SecurityLevel:
        """Get security level as enum"""
        return SecurityLevel(self.DEFAULT_SECURITY_LEVEL.lower())


# Global settings instance
settings = Settings()
