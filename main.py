"""
El Remesero — Entrypoint principal.

Inicia FastAPI + PTB no mesmo processo:
  - FastAPI serve os webhooks (OpenPix PIX, Telegram webhook)
  - PTB gerencia o bot (polling em dev, webhook em prod)
"""

import asyncio
from contextlib import asynccontextmanager
from loguru import logger
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config.settings import settings
from bot.application import criar_application
from webhooks.openpix_webhook import router as pix_router
from webhooks.noones_webhook import router as noones_router
from services.notificacao_service import set_bot_app
from jobs.monitor_pagamentos import registrar_job


def _verificar_credenciais() -> None:
    """Loga avisos para credenciais opcionais não configuradas."""
    modo = "AUTOMÁTICO" if (settings.binance_api_key and (settings.tropipay_client_id or settings.noones_api_key)) else "MANUAL"
    logger.info(f"Modo de entrega: {modo}")

    if not settings.binance_api_key:
        logger.warning("BINANCE_API_KEY não configurada — entrega automática desativada")
    if not settings.tropipay_client_id:
        logger.warning("TROPIPAY_CLIENT_ID não configurada — entrega MLC automática desativada")
    if not settings.noones_api_key:
        logger.warning("NOONES_API_KEY não configurada — entrega CUP automática desativada")
    if not settings.mercadopago_webhook_secret:
        logger.warning("MERCADOPAGO_WEBHOOK_SECRET não configurada — assinatura webhook desativada")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia o ciclo de vida do bot junto com o FastAPI."""
    logger.info("🚀 Iniciando El Remesero...")

    _verificar_credenciais()

    ptb_app = criar_application()

    # Registra o bot no serviço de notificações
    set_bot_app(ptb_app)

    # Registra job de monitoramento
    registrar_job(ptb_app)

    await ptb_app.initialize()

    # Configura lista de comandos visível no Telegram
    from telegram import BotCommand
    await ptb_app.bot.set_my_commands([
        BotCommand("start", "Menu principal"),
        BotCommand("ajuda", "Como funciona o El Remesero"),
    ])

    if settings.webhook_mode and settings.webhook_url:
        # Modo produção: Telegram envia updates via webhook
        webhook_url = f"{settings.webhook_url}/telegram"
        await ptb_app.bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook Telegram configurado: {webhook_url}")
        await ptb_app.start()
    else:
        # Modo desenvolvimento: long polling
        logger.info("Iniciando em modo polling (desenvolvimento)...")
        await ptb_app.start()
        asyncio.create_task(ptb_app.updater.start_polling(drop_pending_updates=True))

    # Salva referência para o router do Telegram webhook
    app.state.ptb_app = ptb_app

    yield

    # Shutdown
    logger.info("Encerrando El Remesero...")
    if settings.webhook_mode:
        await ptb_app.bot.delete_webhook()
    if ptb_app.updater.running:
        await ptb_app.updater.stop()
    await ptb_app.stop()
    await ptb_app.shutdown()
    logger.info("Bot encerrado com sucesso.")


# ── FastAPI App ──────────────────────────────────────────────────────────────

fastapi_app = FastAPI(
    title="El Remesero",
    description="Bot de remessas Brasil → Cuba",
    version="1.0.0",
    lifespan=lifespan,
)

# Registrar routers
fastapi_app.include_router(pix_router)
fastapi_app.include_router(noones_router)


@fastapi_app.post("/telegram")
async def telegram_webhook(request: Request) -> JSONResponse:
    """Recebe updates do Telegram (somente em modo webhook/produção)."""
    from telegram import Update
    import json

    body = await request.body()
    data = json.loads(body)
    ptb_app = request.app.state.ptb_app
    update = Update.de_json(data, ptb_app.bot)
    await ptb_app.process_update(update)
    return JSONResponse(content={"ok": True})


@fastapi_app.get("/health")
async def health() -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse(content={"status": "ok", "bot": "El Remesero"})


# ── Entrypoint ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    import uvicorn

    logger.info("=" * 50)
    logger.info("  EL REMESERO — Bot de Remessas Brasil → Cuba")
    logger.info("=" * 50)

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(
        "main:fastapi_app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
    )
