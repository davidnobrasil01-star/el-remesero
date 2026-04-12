"""
Cliente OpenPix (Woovi) para geração de cobranças PIX.
Documentação: https://developers.openpix.com.br/
"""

import httpx
from loguru import logger
from config.settings import settings

BASE_URL = "https://api.openpix.com.br/api/v1"


def _headers() -> dict:
    return {
        "Authorization": settings.openpix_app_id,
        "Content-Type": "application/json",
    }


async def criar_cobranca(
    correlation_id: str,
    valor_centavos: int,
    comentario: str = "Remessa El Remesero",
    expira_em_segundos: int = 1200,
) -> dict:
    """
    Cria uma cobrança PIX no OpenPix.

    Args:
        correlation_id: ID único da transação (nossa referência interna)
        valor_centavos: Valor em centavos (ex: R$100,00 = 10000)
        comentario: Descrição da cobrança
        expira_em_segundos: Tempo de validade do QR Code (padrão 20 min)

    Returns:
        dict com: qrCodeImage (base64), brCode (copia-cola), correlationID, status
    """
    payload = {
        "correlationID": correlation_id,
        "value": valor_centavos,
        "comment": comentario,
        "expiresIn": expira_em_segundos,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{BASE_URL}/charge", headers=_headers(), json=payload)
        resp.raise_for_status()
        dados = resp.json()
        charge = dados.get("charge", dados)
        return {
            "pix_id": charge.get("correlationID", correlation_id),
            "qr_code_base64": charge.get("qrCodeImage", ""),
            "copia_cola": charge.get("brCode", ""),
            "status": charge.get("status", "ACTIVE"),
        }


async def consultar_cobranca(correlation_id: str) -> dict:
    """Consulta o status de uma cobrança PIX."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{BASE_URL}/charge/{correlation_id}",
            headers=_headers()
        )
        resp.raise_for_status()
        dados = resp.json()
        charge = dados.get("charge", dados)
        return {
            "status": charge.get("status", "UNKNOWN"),
            "pago": charge.get("status") == "COMPLETED",
        }
