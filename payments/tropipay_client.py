"""
Cliente TropiPay — entrega automática em cartão MLC cubano.
Documentação: https://tpp.stoplight.io/docs/tropipay-api-doc
"""

import httpx
from loguru import logger
from config.settings import settings

BASE_URL = "https://www.tropipay.com/api/v2"

_token_cache = {"token": None}


async def _get_token() -> str:
    """Obtém token de autenticação TropiPay."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{BASE_URL}/access/token",
            json={
                "client_id": settings.tropipay_client_id,
                "client_secret": settings.tropipay_client_secret,
                "grant_type": "client_credentials",
            }
        )
        resp.raise_for_status()
        _token_cache["token"] = resp.json()["access_token"]
        return _token_cache["token"]


async def enviar_para_cartao_mlc(
    numero_cartao: str,
    nome_titular: str,
    valor_usd: float,
    referencia: str,
    descricao: str = "Remessa El Remesero",
) -> dict:
    """
    Envia dinheiro para um cartão MLC cubano via TropiPay.

    Args:
        numero_cartao: Número do cartão MLC (16 dígitos)
        nome_titular: Nome completo do titular
        valor_usd: Valor em USD a enviar
        referencia: ID interno da transação
        descricao: Descrição do envio

    Returns:
        dict com: tx_id, status, valor_usd
    """
    token = await _get_token()
    valor_centavos = int(round(valor_usd * 100))

    payload = {
        "reference": referencia,
        "concept": descricao,
        "favorite": False,
        "amount": valor_centavos,
        "currency": "USD",
        "destinationCountryIso": "CU",
        "destinationAmount": valor_centavos,
        "destinationCurrency": "USD",
        "originalCurrencyAmount": valor_centavos,
        "paymentMethods": ["EXT"],
        "beneficiary": {
            "name": nome_titular.split()[0] if nome_titular else "Beneficiario",
            "lastName": " ".join(nome_titular.split()[1:]) if len(nome_titular.split()) > 1 else "Cuba",
            "cardNumber": numero_cartao.replace(" ", "").replace("-", ""),
            "countryIso": "CU",
            "phone": "00000000",
            "userId": referencia,
        },
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BASE_URL}/paymentrequest",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        dados = resp.json()

        tx_id = str(dados.get("id", dados.get("shortId", referencia)))
        status = dados.get("state", "PENDING")

        logger.info(f"TropiPay enviado: ${valor_usd} → cartão {numero_cartao[-4:]} | TX: {tx_id}")

        return {
            "tx_id": tx_id,
            "status": status,
            "valor_usd": valor_usd,
        }


async def verificar_transacao(tx_id: str) -> dict:
    """Consulta o status de um envio TropiPay."""
    try:
        token = await _get_token()
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BASE_URL}/paymentrequest/{tx_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            dados = resp.json()
            estado = dados.get("state", "UNKNOWN")
            return {
                "status": estado,
                "confirmado": estado in ("PAID", "COMPLETED", "PROCESSING"),
            }
    except Exception as e:
        logger.error(f"Erro ao verificar TropiPay TX {tx_id}: {e}")
        return {"status": "error", "confirmado": False}
