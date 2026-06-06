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


def _responder_challenge(request: Request) -> Response | None:
    """
    Noones valida o webhook com X-Noones-Request-Challenge.
    O servidor deve ecoar o valor desse header de volta na resposta.
    Se o header não estiver presente, retorna None (sem challenge).
    """
    challenge = request.headers.get("x-noones-request-challenge", "")
    if challenge:
        logger.info(f"Webhook Noones: challenge recebido, ecoando de volta: {challenge[:20]}...")
        return Response(
            content=challenge,
            status_code=200,
            headers={"X-Noones-Request-Challenge": challenge},
        )
    return None


@router.get("/webhooks/noones")
async def verificar_noones(request: Request) -> Response:
    """Endpoint de verificação GET — responde ao challenge do Noones."""
    logger.info(f"Webhook Noones: GET recebido — headers: {dict(request.headers)}")
    resp = _responder_challenge(request)
    if resp:
        return resp
    return Response(status_code=200)


@router.post("/webhooks/noones")
async def receber_noones(request: Request) -> Response:
    """Recebe eventos do Noones P2P."""
    # Challenge-response: Noones valida a URL ecoando o header de volta
    resp = _responder_challenge(request)
    if resp:
        return resp

    payload_raw = await request.body()
    assinatura = request.headers.get("x-noones-signature", "")

    # Valida assinatura somente se NOONES_WEBHOOK_SECRET estiver configurado
    if assinatura and settings.noones_webhook_secret and not _verificar_assinatura(payload_raw, assinatura):
        logger.warning("Webhook Noones: assinatura inválida")
        raise HTTPException(status_code=400, detail="Assinatura inválida")

    # Corpo vazio ou não-JSON (ping de verificação) → retorna 200
    if not payload_raw or payload_raw.strip() in (b"", b"{}", b"[]"):
        return Response(status_code=200)

    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        logger.warning(f"Webhook Noones: body não é JSON: {payload_raw[:100]}")
        return Response(status_code=200)

    evento = payload.get("type", "")
    logger.info(f"Webhook Noones: {evento}")

    # Trade aberto → envia instruções imediatamente (sem esperar o monitor de 5 min)
    if evento == "trade.started":
        trade_id = payload.get("trade", {}).get("trade_hash", "")
        if trade_id:
            from services.noones_service import processar_trade_iniciado
            await processar_trade_iniciado(trade_id, payload)

    # Comprador marcou como pago → encaminhar comprovante ao admin
    elif evento in ("trade.paid", "trade_payment_proof"):
        trade_id = payload.get("trade", {}).get("trade_hash", "")
        if trade_id:
            from services.noones_service import processar_comprovante_noones
            await processar_comprovante_noones(trade_id, payload)

    return Response(status_code=200)
