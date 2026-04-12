"""
Webhook Mercado Pago — recebe notificações de pagamentos PIX confirmados.
"""

import hashlib
import hmac
import json
from fastapi import APIRouter, Request, Response, HTTPException
from loguru import logger
from config.settings import settings

router = APIRouter()

_transaction_service = None


def _get_service():
    global _transaction_service
    if _transaction_service is None:
        from services.transaction_service import processar_pix_confirmado
        _transaction_service = processar_pix_confirmado
    return _transaction_service


def _verificar_assinatura_mp(request: Request, payload_raw: bytes) -> bool:
    """
    Verifica a assinatura do webhook Mercado Pago.
    Header: x-signature contém ts=...&v1=...
    Header: x-request-id contém o request ID
    """
    secret = settings.mercadopago_webhook_secret
    if not secret:
        # Sem secret configurado: aceita tudo (dev/teste)
        return True

    x_signature = request.headers.get("x-signature", "")
    x_request_id = request.headers.get("x-request-id", "")

    # Parsear ts e v1 do header x-signature
    parts = dict(p.split("=", 1) for p in x_signature.split("&") if "=" in p)
    ts = parts.get("ts", "")
    v1 = parts.get("v1", "")

    if not ts or not v1:
        return False

    # Reconstruir mensagem para validação
    # data_id vem do query param ?data.id=...
    data_id = request.query_params.get("data.id", "")
    manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"

    assinatura_esperada = hmac.new(
        secret.encode("utf-8"),
        manifest.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(assinatura_esperada, v1)


@router.post("/webhooks/pix")
async def receber_pix(request: Request) -> Response:
    """Endpoint que recebe notificações do Mercado Pago (pagamento PIX)."""
    payload_raw = await request.body()

    # Verificar assinatura se secret configurado
    if settings.mercadopago_webhook_secret:
        if not _verificar_assinatura_mp(request, payload_raw):
            logger.warning("Webhook MP: assinatura inválida rejeitada")
            raise HTTPException(status_code=400, detail="Assinatura inválida")

    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON inválido")

    tipo = payload.get("type", "")
    action = payload.get("action", "")
    logger.info(f"Webhook MP recebido: type={tipo} action={action}")

    # Processar somente pagamentos aprovados
    if tipo == "payment" and action in ("payment.created", "payment.updated"):
        data_id = payload.get("data", {}).get("id")
        if data_id:
            try:
                from payments.mercadopago_client import buscar_pagamento
                pagamento = await buscar_pagamento(str(data_id))

                if pagamento["status"] == "approved":
                    # O external_reference é o nosso correlation_id (REMESERO-XXXX)
                    correlation_id = pagamento.get("external_reference", "")
                    if correlation_id:
                        processar = _get_service()
                        await processar(correlation_id)
                        logger.info(f"PIX aprovado processado: {correlation_id}")
                    else:
                        logger.warning(f"Pagamento {data_id} aprovado sem external_reference")
                else:
                    logger.info(f"Pagamento {data_id} com status={pagamento['status']}, ignorando")

            except Exception as e:
                logger.error(f"Erro ao processar webhook MP payment {data_id}: {e}")

    # Sempre retornar 200 rapidamente
    return Response(status_code=200)
