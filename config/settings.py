from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Telegram
    telegram_bot_token: str
    admin_telegram_id: int

    # Mercado Pago (PIX)
    mercadopago_access_token: str = ""
    mercadopago_webhook_secret: str = ""

    # OpenPix (legado)
    openpix_app_id: str = ""
    openpix_webhook_secret: str = ""

    # Binance
    binance_api_key: str = ""
    binance_api_secret: str = ""

    # TropiPay (entrega MLC automática)
    tropipay_client_id: str = ""
    tropipay_client_secret: str = ""

    # Noones P2P (entrega CUP semi-automática)
    noones_api_key: str = ""
    noones_webhook_secret: str = ""

    # Supabase
    supabase_url: str
    supabase_service_key: str

    # Modo do bot
    webhook_mode: bool = False
    webhook_url: str = ""

    # Configurações de negócio
    margem_minima_cup_por_brl: float = Field(default=5.0)
    taxa_ofertada_cup_por_brl: float = Field(default=97.0)
    limite_minimo_brl: float = Field(default=50.0)
    limite_maximo_brl: float = Field(default=3000.0)
    limite_diario_brl: float = Field(default=3000.0)
    limite_mensal_brl: float = Field(default=10000.0)
    limite_revisao_manual_brl: float = Field(default=1500.0)


settings = Settings()
