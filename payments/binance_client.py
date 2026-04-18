"""
Cliente Binance para conversão BRL → USDT TRC20.
Usa a Binance API para executar ordens de compra de USDT com BRL.
"""

import asyncio
from loguru import logger
from binance.client import Client
from binance.exceptions import BinanceAPIException
from config.settings import settings


def _get_client() -> Client:
    return Client(settings.binance_api_key, settings.binance_api_secret)


async def obter_preco_usdt_brl() -> float:
    """Retorna o preço atual de 1 USDT em BRL."""
    loop = asyncio.get_running_loop()
    client = _get_client()
    ticker = await loop.run_in_executor(
        None,
        lambda: client.get_symbol_ticker(symbol="USDTBRL")
    )
    return float(ticker["price"])


async def comprar_usdt(valor_brl: float) -> dict:
    """
    Executa ordem de compra de USDT com BRL na Binance.

    Args:
        valor_brl: Valor em BRL a usar na compra

    Returns:
        dict com: usdt_comprado, preco_executado, order_id
    """
    loop = asyncio.get_running_loop()
    client = _get_client()

    try:
        # Obtém preço atual para calcular quantidade
        preco = await obter_preco_usdt_brl()
        qtd_usdt = round(valor_brl / preco, 2)

        # Executa ordem de mercado
        order = await loop.run_in_executor(
            None,
            lambda: client.order_market_buy(
                symbol="USDTBRL",
                quoteOrderQty=valor_brl,
            )
        )

        usdt_comprado = float(order.get("executedQty", qtd_usdt))
        preco_executado = float(order.get("cummulativeQuoteQty", valor_brl)) / usdt_comprado if usdt_comprado > 0 else preco

        logger.info(f"USDT comprado: {usdt_comprado} USDT | Preço: R${preco_executado:.4f} | Order ID: {order['orderId']}")

        return {
            "usdt_comprado": usdt_comprado,
            "preco_executado": preco_executado,
            "order_id": str(order["orderId"]),
            "status": order.get("status", "FILLED"),
        }

    except BinanceAPIException as e:
        logger.error(f"Erro Binance ao comprar USDT: {e.message}")
        raise RuntimeError(f"Erro na exchange: {e.message}")


async def verificar_saldo_usdt() -> float:
    """Retorna o saldo disponível de USDT na conta Binance."""
    loop = asyncio.get_running_loop()
    client = _get_client()
    account = await loop.run_in_executor(None, client.get_account)
    for balance in account["balances"]:
        if balance["asset"] == "USDT":
            return float(balance["free"])
    return 0.0
