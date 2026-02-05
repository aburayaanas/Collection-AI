import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr

class Settings(BaseSettings):
    # --- Application Info ---
    APP_NAME: str = "CollectionAI_Batch"
    VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=False, description="Set to True for verbose logging")

    # --- Oracle Database Config ---
    # We use SecretStr to hide passwords from logs automatically
    DB_USER: str = Field(..., description="Oracle Username")
    DB_PASSWORD: SecretStr = Field(..., description="Oracle Password")
    DB_DSN: str = Field(..., description="DSN string")
    
    DB_MIN_POOL: int = Field(default=2, ge=1)
    DB_MAX_POOL: int = Field(default=5, ge=2)
    
    BATCH_SIZE: int = 1000 
    
    # --- Execution Mode ---
    MODE: str = Field(default="SCORE", description="Execution mode: TRAIN or SCORE")
    MODEL_TYPE: str = Field(default="WILLINGNESS", description="Model type: WILLINGNESS or ABILITY")
    
    # --- Model Thresholds ---
    WILLINGNESS_THRESHOLD: float = 0.7
    ABILITY_THRESHOLD: float = 0.5

    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()

def get_secret_value(setting: SecretStr) -> str:
    return setting.get_secret_value()