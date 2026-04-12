"""
Cliente Noones P2P — venda de USDT com pagamento em CUP via Transfermovil.
Documentação: https://docs.noones.com/
"""

import httpx
from loguru import logger
from config.settings import settings

BASE_URL = "https://noones.com/api/noones/v1"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.noones_api_key}",
        "Content-Type": "application/json",
    }


async def criar_oferta_venda(
    valor_usdt: float,
    numero_cartao_cup: str,
    nome_titular: str,
    transacao_id: str,
) -> dict:
    """
    Cria uma oferta de venda de USDT no Noones P2P.
    O comprador pagará CUP via Transfermovil para o cartão especificado.

    Args:
        valor_usdt: Quantidade de USDT a vender
        numero_cartao_cup: Cartão cubano onde o comprador enviará CUP
        nome_titular: Nome do titular do cartão
        transacao_id: ID interno da transação

    Returns:
        dict com: oferta_id, link_oferta
    """
    # Instruções de pagamento visíveis ao comprador
    instrucoes = (
        f"Envie via Transfermovil para o cartão: {numero_cartao_cup}\n"
        f"Titular: {nome_titular}\n"
        f"Referência: {transacao_id[:8].upper()}\n"
        f"Após pagar, envie o comprovante neste chat."
    )

    payload = {
        "currency": "USDT",
        "payment_method": "transfermovil",
        "type": "sell",
        "amount": str(round(valor_usdt, 2)),
        "margin": "0",
        "payment_window": 30,
        "payment_details": instrucoes,
        "offer_terms": instrucoes,
        "label": f"Remessa #{transacao_id[:8].upper()}",
        "require_verified_id": False,
        "require_trusted_by_advertiser": False,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{BASE_URL}/offer/create",
            headers=_headers(),
            json=payload,
        )
        resp.raise_for_status()
        dados = resp.json()

        oferta_id = str(dados.get("data", {}).get("offer_hash", ""))
        logger.info(f"Noones oferta criada: {oferta_id} | {valor_usdt} USDT")

        return {
            "oferta_id": oferta_id,
            "link_oferta": f"https://noones.com/buy-usdt/{oferta_id}",
        }


async def desativar_oferta(oferta_id: str) -> bool:
    """Desativa uma oferta após ser completada ou cancelada."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{BASE_URL}/offer/{oferta_id}/deactivate",
                headers=_headers(),
            )
            return resp.status_code == 200
    except Exception as e:
        logger.error(f"Erro ao desativar oferta Noones {oferta_id}: {e}")
        return False


async def buscar_trades_oferta(oferta_id: str) -> list:
    """Busca trades ativos de uma oferta."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BASE_URL}/trade/list",
                headers=_headers(),
                params={"offer_hash": oferta_id, "page": 1},
            )
            resp.raise_for_status()
            return resp.json().get("data", {}).get("trades", [])
    except Exception as e:
        logger.error(f"Erro ao buscar trades Noones: {e}")
        return []


async def buscar_mensagens_trade(trade_id: str) -> list:
    """Busca mensagens/comprovantes do chat de um trade."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BASE_URL}/trade/{trade_id}/chat",
                headers=_headers(),
            )
            resp.raise_for_status()
            return resp.json().get("data", {}).get("messages", [])
    except Exception as e:
        logger.error(f"Erro ao buscar chat do trade {trade_id}: {e}")
        return []


async def liberar_usdt(trade_id: str) -> bool:
    """
    Libera o USDT do escrow para o comprador após aprovação do admin.
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{BASE_URL}/trade/{trade_id}/release",
                headers=_headers(),
            )
            resp.raise_for_status()
            logger.info(f"Noones USDT liberado: trade {trade_id}")
            return True
    except Exception as e:
        logger.error(f"Erro ao liberar USDT Noones trade {trade_id}: {e}")
        return False


async def cancelar_trade(trade_id: str) -> bool:
    """Cancela um trade Noones."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{BASE_URL}/trade/{trade_id}/cancel",
                headers=_headers(),
            )
            return resp.status_code == 200
    except Exception as e:
        logger.error(f"Erro ao cancelar trade Noones {trade_id}: {e}")
        return False
