"""
Cliente Mercado Bitcoin (MB) — conversão BRL → USDT via API v4.

Autenticação HMAC-SHA256:
  MB-ACCESS-ID        = api_key (Access ID gerado em Configurações → Chaves de API)
  MB-ACCESS-SIGN      = HMAC-SHA256(secret, {api_key}{timestamp}{METHOD}{path}{body})
  MB-ACCESS-TIMESTAMP = Unix timestamp em segundos (string)

Documentação: https://api.mercadobitcoin.net/api/v4/docs
"""

import hmac
import hashlib
import json
import time
import httpx
from loguru import logger
from config.settings import settings

BASE_URL = "https://api.mercadobitcoin.net/api/v4"
PAR = "USDT-BRL"      # Par de negociação


# ── Autenticação ──────────────────────────────────────────────────────────────

def _sign(method: str, path: str, timestamp: str, body: str = "") -> str:
    """Gera assinatura HMAC-SHA256 para a MB API."""
    msg = f"{settings.mb_api_key}{timestamp}{method.upper()}{path}{body}"
    return hmac.new(
        settings.mb_api_secret.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _auth_headers(method: str, path: str, body: str = "") -> dict:
    """Retorna headers de autenticação para a MB API."""
    ts = str(int(time.time()))
    return {
        "MB-ACCESS-ID": settings.mb_api_key,
        "MB-ACCESS-SIGN": _sign(method, path, ts, body),
        "MB-ACCESS-TIMESTAMP": ts,
        "Content-Type": "application/json",
    }


# ── Endpoints Públicos ────────────────────────────────────────────────────────

async def obter_preco_usdt_brl() -> float:
    """
    Retorna o preço atual de 1 USDT em BRL via ticker público.
    Usa o preço 'last' (última negociação).
    """
    url = f"{BASE_URL}/{PAR}/ticker"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        dados = resp.json()

    # Resposta: {"pair": "USDT-BRL", "last": "5.83", "buy": "5.82", "sell": "5.84", ...}
    preco = float(dados.get("last", 0) or dados.get("sell", 0))
    if preco <= 0:
        raise RuntimeError(f"Preço USDT/BRL inválido na MB: {dados}")

    logger.debug(f"MB ticker USDT/BRL: R${preco:.4f}")
    return preco


# ── Endpoints Privados ────────────────────────────────────────────────────────

async def _get_account_id() -> str:
    """
    Busca o ID da conta MB (necessário para ordens privadas).
    Faz cache em memória durante o processo.
    """
    if _get_account_id._cache:
        return _get_account_id._cache

    path = "/accounts"
    headers = _auth_headers("GET", path)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{BASE_URL}{path}", headers=headers)
        resp.raise_for_status()
        dados = resp.json()

    # Retorna o primeiro account_id disponível
    if isinstance(dados, list) and dados:
        account_id = str(dados[0].get("id", ""))
    elif isinstance(dados, dict):
        account_id = str(dados.get("id", ""))
    else:
        raise RuntimeError(f"Não foi possível obter account_id da MB: {dados}")

    if not account_id:
        raise RuntimeError("account_id vazio na resposta da MB")

    _get_account_id._cache = account_id
    logger.info(f"MB account_id: {account_id}")
    return account_id


_get_account_id._cache = ""   # cache simples em memória


async def comprar_usdt(valor_brl: float) -> dict:
    """
    Executa ordem de compra de USDT com BRL no Mercado Bitcoin.

    Tipo: market buy (gasta exatamente valor_brl em BRL para comprar USDT).

    Args:
        valor_brl: Valor em BRL a gastar na compra

    Returns:
        dict com: usdt_comprado, preco_executado, order_id, status
    """
    if not settings.mb_api_key or not settings.mb_api_secret:
        raise RuntimeError("MB_API_KEY e MB_API_SECRET não configurados")

    account_id = await _get_account_id()
    preco_atual = await obter_preco_usdt_brl()

    # Payload: ordem de mercado usando qty_brl (custo em BRL)
    payload = {
        "async": False,
        "cost": round(valor_brl, 2),   # BRL a gastar
        "type": "market",
        "side": "buy",
    }
    body_str = json.dumps(payload, separators=(",", ":"))
    path = f"/accounts/{account_id}/{PAR}/orders"
    headers = _auth_headers("POST", path, body_str)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BASE_URL}{path}",
            headers=headers,
            content=body_str,
        )

    if resp.status_code not in (200, 201):
        logger.error(f"MB comprar_usdt erro {resp.status_code}: {resp.text}")
        raise RuntimeError(f"MB API erro {resp.status_code}: {resp.text[:200]}")

    dados = resp.json()
    logger.debug(f"MB ordem resposta: {dados}")

    # Extrai valores da resposta
    # Formato MB: {"orderId": "...", "qty": "90.12", "cost": "500.00", "avgPrice": "5.55", "status": "filled", ...}
    order_id = str(dados.get("orderId", dados.get("id", "sem-id")))
    qty = float(dados.get("qty", 0) or dados.get("executedQty", 0) or (valor_brl / preco_atual))
    cost = float(dados.get("cost", 0) or dados.get("cummulativeQuoteQty", valor_brl))
    avg_price = float(dados.get("avgPrice", 0) or (cost / qty if qty > 0 else preco_atual))

    # Fallback se API retornou valores vazios (ordem assíncrona)
    if qty <= 0:
        qty = round(valor_brl / preco_atual, 8)
        avg_price = preco_atual
        logger.warning(f"MB ordem sem qty na resposta — estimando {qty:.8f} USDT")

    logger.info(
        f"MB USDT comprado: {qty:.4f} USDT | "
        f"Custo: R${cost:.2f} | "
        f"Preço médio: R${avg_price:.4f} | "
        f"Order ID: {order_id}"
    )

    return {
        "usdt_comprado": round(qty, 8),
        "preco_executado": round(avg_price, 4),
        "order_id": order_id,
        "status": dados.get("status", "filled"),
    }


async def verificar_saldo_usdt() -> float:
    """Retorna o saldo disponível de USDT na conta MB."""
    account_id = await _get_account_id()
    path = f"/accounts/{account_id}/balances/USDT"
    headers = _auth_headers("GET", path)

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{BASE_URL}{path}", headers=headers)
        resp.raise_for_status()
        dados = resp.json()

    # Formato: {"symbol": "USDT", "available": "150.00", "on_hold": "0.00", ...}
    saldo = float(dados.get("available", 0))
    logger.debug(f"MB saldo USDT disponível: {saldo:.4f}")
    return saldo


async def verificar_saldo_brl() -> float:
    """Retorna o saldo disponível de BRL na conta MB."""
    account_id = await _get_account_id()
    path = f"/accounts/{account_id}/balances/BRL"
    headers = _auth_headers("GET", path)

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{BASE_URL}{path}", headers=headers)
        resp.raise_for_status()
        dados = resp.json()

    saldo = float(dados.get("available", 0))
    logger.debug(f"MB saldo BRL disponível: R${saldo:.2f}")
    return saldo
