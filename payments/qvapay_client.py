"""
Cliente QvaPay para entrega de USDT em Cuba.
API: https://api.qvapay.com/v2/
"""

import httpx
from loguru import logger
from config.settings import settings

BASE_URL = "https://api.qvapay.com/v2"


async def _get_token() -> str:
    """Obtém token de autenticação do QvaPay."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{BASE_URL}/login",
            json={
                "app_id": settings.qvapay_app_id,
                "app_secret": settings.qvapay_app_secret,
            }
        )
        resp.raise_for_status()
        return resp.json().get("token", "")


async def verificar_usuario(qvapay_handle: str) -> dict:
    """
    Verifica se um handle QvaPay existe.

    Args:
        qvapay_handle: username ou número de telefone QvaPay do destinatário

    Returns:
        dict com: existe (bool), nome (str)
    """
    try:
        token = await _get_token()
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BASE_URL}/profile/{qvapay_handle}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                dados = resp.json()
                return {"existe": True, "nome": dados.get("name", qvapay_handle)}
            return {"existe": False, "nome": ""}
    except Exception as e:
        logger.warning(f"Erro ao verificar usuário QvaPay {qvapay_handle}: {e}")
        return {"existe": False, "nome": ""}


async def enviar_usdt(destinatario_handle: str, valor_usdt: float, descricao: str = "Remessa El Remesero") -> dict:
    """
    Envia USDT para um destinatário QvaPay em Cuba.

    Args:
        destinatario_handle: username QvaPay do destinatário
        valor_usdt: Quantidade de USDT a enviar
        descricao: Descrição da transferência

    Returns:
        dict com: tx_id, status, valor_usdt
    """
    token = await _get_token()

    payload = {
        "to": destinatario_handle,
        "amount": str(round(valor_usdt, 8)),
        "description": descricao,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BASE_URL}/transactions",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        dados = resp.json()

        tx_id = str(dados.get("uuid", dados.get("id", "")))
        status = dados.get("status", "ok")

        logger.info(f"QvaPay enviado: {valor_usdt} USDT → {destinatario_handle} | TX: {tx_id}")

        return {
            "tx_id": tx_id,
            "status": status,
            "valor_usdt": valor_usdt,
            "destinatario": destinatario_handle,
        }


async def verificar_transacao(tx_id: str) -> dict:
    """Consulta o status de uma transação QvaPay."""
    try:
        token = await _get_token()
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BASE_URL}/transactions/{tx_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            dados = resp.json()
            return {
                "status": dados.get("status", "unknown"),
                "confirmado": dados.get("status") in ("ok", "confirmed", "completed"),
            }
    except Exception as e:
        logger.error(f"Erro ao verificar transação QvaPay {tx_id}: {e}")
        return {"status": "error", "confirmado": False}
