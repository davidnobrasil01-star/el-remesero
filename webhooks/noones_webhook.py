"""
Webhook Noones — recebe notificações de trades P2P.
Quando comprador marca como pago, encaminha comprovante ao admin para aprovação.
"""

import hashlib
import hmac
import json
import httpx
from fastapi import APIRouter, Request, Response, HTTPException
from loguru import logger
from config.settings import settings

router = APIRouter()


def _verificar_assinatura(payload_raw: bytes, assinatura: str) -> bool:
    secret = settings.noones_webhook_secret.encode("utf-8")
    esperada = hmac.new(secret, payload_raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, assinatura)


@router.post("/webhooks/noones")
async def receber_noones(request: Request) -> Response:
    """Recebe eventos do Noones P2P."""
    payload_raw = await request.body()
    assinatura = request.headers.get("x-noones-signature", "")

    if assinatura and not _verificar_assinatura(payload_raw, assinatura):
        logger.warning("Webhook Noones: assinatura inválida")
        raise HTTPException(status_code=400, detail="Assinatura inválida")

    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON inválido")

    evento = payload.get("type", "")
    logger.info(f"Webhook Noones: {evento}")

    # Comprador marcou como pago → encaminhar comprovante ao admin
    if evento in ("trade.paid", "trade_payment_proof"):
        trade_id = payload.get("trade", {}).get("trade_hash", "")
        if trade_id:
            from services.noones_service import processar_comprovante_noones
            await processar_comprovante_noones(trade_id, payload)

    return Response(status_code=200)
