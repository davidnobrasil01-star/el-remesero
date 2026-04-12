"""
Cliente Mercado Pago — cria cobranças PIX e consulta status de pagamento.
"""

import httpx
from datetime import datetime, timedelta
from loguru import logger
from config.settings import settings

_BASE_URL = "https://api.mercadopago.com"


def _headers(idempotency_key: str | None = None) -> dict:
    h = {
        "Authorization": f"Bearer {settings.mercadopago_access_token}",
        "Content-Type": "application/json",
    }
    if idempotency_key:
        h["X-Idempotency-Key"] = idempotency_key
    return h


async def criar_cobranca(
    correlation_id: str,
    valor_centavos: int,
    comentario: str,
    expira_em_segundos: int = 1200,
) -> dict:
    """
    Cria um pagamento PIX no Mercado Pago.

    Returns:
        dict com pix_id, qr_code_base64, copia_cola
    """
    valor_brl = valor_centavos / 100.0
    expira_em = (datetime.now() + timedelta(seconds=expira_em_segundos)).strftime(
        "%Y-%m-%dT%H:%M:%S.000-03:00"
    )

    payload = {
        "transaction_amount": valor_brl,
        "payment_method_id": "pix",
        "payer": {
            "email": "cliente@elremesero.com",
        },
        "description": comentario,
        "external_reference": correlation_id,
        "date_of_expiration": expira_em,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{_BASE_URL}/v1/payments",
            json=payload,
            headers=_headers(idempotency_key=correlation_id),
        )

    if resp.status_code not in (200, 201):
        logger.error(f"MP criar_cobranca erro {resp.status_code}: {resp.text}")
        raise RuntimeError(f"Mercado Pago erro {resp.status_code}: {resp.text}")

    data = resp.json()
    tx_data = data.get("point_of_interaction", {}).get("transaction_data", {})

    return {
        "pix_id": str(data["id"]),
        "qr_code_base64": tx_data.get("qr_code_base64", ""),
        "copia_cola": tx_data.get("qr_code", ""),
    }


async def buscar_pagamento(payment_id: str) -> dict:
    """Consulta um pagamento por ID e retorna status e external_reference."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{_BASE_URL}/v1/payments/{payment_id}",
            headers=_headers(),
        )

    if resp.status_code != 200:
        logger.error(f"MP buscar_pagamento erro {resp.status_code}: {resp.text}")
        raise RuntimeError(f"Mercado Pago erro {resp.status_code}: {resp.text}")

    data = resp.json()
    return {
        "id": str(data["id"]),
        "status": data["status"],          # "approved", "pending", "rejected"
        "external_reference": data.get("external_reference", ""),
        "valor": data.get("transaction_amount", 0),
    }
