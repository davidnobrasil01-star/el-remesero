"""
Cliente Foxbit — conversão BRL → USDT via API REST v3.

Autenticação HMAC-SHA256:
  X-FB-ACCESS-KEY       = api_key
  X-FB-ACCESS-SIGN      = HMAC-SHA256(secret, timestamp + method + path + body)
  X-FB-ACCESS-TIMESTAMP = Unix timestamp em milissegundos (string)

Documentação: https://foxbit.com.br/api-docs/
"""

import hmac
import hashlib
import json
import time
import httpx
from loguru import logger
from config.settings import settings

BASE_URL = "https://api.foxbit.com.br"
PAR = "USDTBRL"   # Par de negociação na Foxbit


# ── Autenticação ──────────────────────────────────────────────────────────────

def _sign(timestamp: str, method: str, path: str, body: str = "") -> str:
    """Gera assinatura HMAC-SHA256 para a Foxbit API."""
    msg = f"{timestamp}{method.upper()}{path}{body}"
    return hmac.new(
        settings.foxbit_api_secret.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _auth_headers(method: str, path: str, body: str = "") -> dict:
    """Retorna headers de autenticação para a Foxbit API."""
    ts = str(int(time.time() * 1000))  # milissegundos
    return {
        "X-FB-ACCESS-KEY": settings.foxbit_api_key,
        "X-FB-ACCESS-SIGN": _sign(ts, method, path, body),
        "X-FB-ACCESS-TIMESTAMP": ts,
        "Content-Type": "application/json",
    }


# ── Endpoints Públicos ────────────────────────────────────────────────────────

async def obter_preco_usdt_brl() -> float:
    """
    Retorna o preço atual de 1 USDT em BRL via ticker público.
    Usa o preço 'last' (última negociação).
    """
    url = f"{BASE_URL}/rest/v3/markets/{PAR}/ticker"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        dados = resp.json()

    # Resposta: {"best_ask": "5.84", "best_bid": "5.82", "last_price": "5.83", ...}
    preco = float(
        dados.get("last_price") or
        dados.get("ask") or
        dados.get("best_ask") or 0
    )
    if preco <= 0:
        raise RuntimeError(f"Preço USDT/BRL inválido na Foxbit: {dados}")

    logger.debug(f"Foxbit ticker USDT/BRL: R${preco:.4f}")
    return preco


# ── Endpoints Privados ────────────────────────────────────────────────────────

async def comprar_usdt(valor_brl: float) -> dict:
    """
    Executa ordem de compra de USDT com BRL na Foxbit.

    Tipo: MARKET com quoteOrderQty (gasta exatamente valor_brl em BRL).

    Args:
        valor_brl: Valor em BRL a gastar na compra

    Returns:
        dict com: usdt_comprado, preco_executado, order_id, status
    """
    if not settings.foxbit_api_key or not settings.foxbit_api_secret:
        raise RuntimeError("FOXBIT_API_KEY e FOXBIT_API_SECRET não configurados")

    preco_atual = await obter_preco_usdt_brl()

    # Payload: ordem de mercado comprando com valor fixo em BRL (quote)
    payload = {
        "market_symbol": PAR,
        "side": "BUY",
        "type": "MARKET",
        "quote_quantity": str(round(valor_brl, 2)),  # BRL a gastar
    }
    body_str = json.dumps(payload, separators=(",", ":"))
    path = "/rest/v3/orders"
    headers = _auth_headers("POST", path, body_str)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BASE_URL}{path}",
            headers=headers,
            content=body_str,
        )

    if resp.status_code not in (200, 201):
        logger.error(f"Foxbit comprar_usdt erro {resp.status_code}: {resp.text}")
        raise RuntimeError(f"Foxbit API erro {resp.status_code}: {resp.text[:200]}")

    dados = resp.json()
    logger.debug(f"Foxbit ordem resposta: {dados}")

    # Formato Foxbit: {"id": "...", "quantity": "90.12", "quote_quantity": "500.00",
    #                  "price": "5.55", "status": "FILLED", ...}
    order_id = str(dados.get("id", "sem-id"))
    qty = float(dados.get("quantity", 0) or 0)
    cost = float(dados.get("quote_quantity", valor_brl) or valor_brl)
    avg_price = float(dados.get("price", 0) or 0)

    # Fallback se ordem ainda não foi preenchida (status PENDING)
    if qty <= 0:
        qty = round(valor_brl / preco_atual, 8)
        avg_price = preco_atual
        logger.warning(f"Foxbit ordem sem qty — estimando {qty:.8f} USDT")
    elif avg_price <= 0:
        avg_price = cost / qty if qty > 0 else preco_atual

    logger.info(
        f"Foxbit USDT comprado: {qty:.4f} USDT | "
        f"Custo: R${cost:.2f} | "
        f"Preço médio: R${avg_price:.4f} | "
        f"Order ID: {order_id}"
    )

    return {
        "usdt_comprado": round(qty, 8),
        "preco_executado": round(avg_price, 4),
        "order_id": order_id,
        "status": dados.get("status", "FILLED"),
    }


async def verificar_saldo_usdt() -> float:
    """Retorna o saldo disponível de USDT na conta Foxbit."""
    path = "/rest/v3/accounts/USDT/balances"
    headers = _auth_headers("GET", path)

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{BASE_URL}{path}", headers=headers)
        resp.raise_for_status()
        dados = resp.json()

    # Formato: [{"currency_symbol": "USDT", "quantity": "150.00", "blocked_quantity": "0"}]
    if isinstance(dados, list):
        for item in dados:
            if item.get("currency_symbol") == "USDT":
                return float(item.get("quantity", 0))
    saldo = float(dados.get("quantity", 0))
    logger.debug(f"Foxbit saldo USDT: {saldo:.4f}")
    return saldo


async def verificar_saldo_brl() -> float:
    """Retorna o saldo disponível de BRL na conta Foxbit."""
    path = "/rest/v3/accounts/BRL/balances"
    headers = _auth_headers("GET", path)

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{BASE_URL}{path}", headers=headers)
        resp.raise_for_status()
        dados = resp.json()

    if isinstance(dados, list):
        for item in dados:
            if item.get("currency_symbol") == "BRL":
                return float(item.get("quantity", 0))
    saldo = float(dados.get("quantity", 0))
    logger.debug(f"Foxbit saldo BRL: R${saldo:.2f}")
    return saldo
