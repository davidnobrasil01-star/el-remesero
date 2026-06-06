"""
Cliente Foxbit — conversão BRL → USDT via API REST v3.

Autenticação HMAC-SHA256:
  X-FB-ACCESS-KEY       = api_key
  X-FB-ACCESS-SIGN      = HMAC-SHA256(secret, timestamp + method + path + body)
  X-FB-ACCESS-TIMESTAMP = Unix timestamp em milissegundos (string)

Notas:
  - A Foxbit NÃO tem par USDT/BRL direto.
  - Conversão BRL → USDT feita em 2 passos: BRL→BTC (btcbrl) + BTC→USDT (btcusdt).
  - Endpoint de ticker correto: /rest/v3/markets/{symbol}/ticker/24hr

Documentação: https://docs.foxbit.com.br/rest/v3/
"""

import hmac
import hashlib
import json
import time
import httpx
from loguru import logger
from config.settings import settings

BASE_URL = "https://api.foxbit.com.br"
PAR_BTC_BRL  = "btcbrl"    # compra BTC com BRL
PAR_BTC_USDT = "btcusdt"   # vende BTC por USDT


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


def _extrair_preco(dados: dict) -> float:
    """
    Extrai preço do ticker v3.
    Resposta: {last_trade: {price: ...}, best: {ask: {price: ...}, bid: {price: ...}}}
    """
    preco = (
        (dados.get("last_trade") or {}).get("price") or
        (dados.get("best") or {}).get("ask", {}).get("price") or
        (dados.get("best") or {}).get("bid", {}).get("price") or
        0
    )
    return float(preco)


# ── Endpoints Públicos ────────────────────────────────────────────────────────

async def _obter_ticker(par: str) -> dict:
    """Busca ticker 24h de um par da Foxbit."""
    url = f"{BASE_URL}/rest/v3/markets/{par}/ticker/24hr"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    return resp.json()


async def obter_preco_btc_brl() -> float:
    """Retorna o preço de 1 BTC em BRL."""
    dados = await _obter_ticker(PAR_BTC_BRL)
    preco = _extrair_preco(dados)
    if preco <= 0:
        raise RuntimeError(f"Preço BTC/BRL inválido na Foxbit: {dados}")
    logger.debug(f"Foxbit BTC/BRL: R${preco:,.2f}")
    return preco


async def obter_preco_usdt_brl() -> float:
    """
    Calcula o preço de 1 USDT em BRL via cross-rate: BTC/BRL ÷ BTC/USDT.
    A Foxbit não tem par USDT/BRL direto.
    """
    dados_brl  = await _obter_ticker(PAR_BTC_BRL)
    dados_usdt = await _obter_ticker(PAR_BTC_USDT)

    preco_btc_brl  = _extrair_preco(dados_brl)
    preco_btc_usdt = _extrair_preco(dados_usdt)

    if preco_btc_brl <= 0 or preco_btc_usdt <= 0:
        raise RuntimeError(
            f"Preços inválidos Foxbit: BTC/BRL={dados_brl}, BTC/USDT={dados_usdt}"
        )

    # USDT/BRL = (BRL por 1 BTC) ÷ (USDT por 1 BTC)
    preco_usdt_brl = preco_btc_brl / preco_btc_usdt
    logger.debug(
        f"Foxbit cross-rate USDT/BRL: R${preco_usdt_brl:.4f} "
        f"(BTC/BRL=R${preco_btc_brl:,.2f}, BTC/USDT={preco_btc_usdt:.2f})"
    )
    return preco_usdt_brl


# ── Endpoints Privados ────────────────────────────────────────────────────────

async def _executar_ordem(payload: dict) -> dict:
    """Executa uma ordem na Foxbit e retorna os dados da resposta."""
    path = "/rest/v3/orders"
    body_str = json.dumps(payload, separators=(",", ":"))
    headers = _auth_headers("POST", path, body_str)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BASE_URL}{path}",
            headers=headers,
            content=body_str,
        )

    if resp.status_code not in (200, 201):
        logger.error(f"Foxbit ordem erro {resp.status_code}: {resp.text}")
        raise RuntimeError(f"Foxbit API erro {resp.status_code}: {resp.text[:200]}")

    dados = resp.json()
    logger.debug(f"Foxbit ordem resposta: {dados}")
    return dados


async def comprar_usdt(valor_brl: float) -> dict:
    """
    Compra USDT com BRL via Foxbit em 2 passos:
      1. Compra BTC com BRL  (par btcbrl, BUY MARKET, quote_quantity = valor_brl)
      2. Vende BTC por USDT  (par btcusdt, SELL MARKET, quantity = btc_comprado)

    Args:
        valor_brl: Valor em BRL a converter em USDT

    Returns:
        dict com: usdt_comprado, preco_executado, order_id, status
    """
    if not settings.foxbit_api_key or not settings.foxbit_api_secret:
        raise RuntimeError("FOXBIT_API_KEY e FOXBIT_API_SECRET não configurados")

    # Passo 1 — Comprar BTC com BRL
    logger.info(f"Foxbit passo 1: comprando BTC com R${valor_brl:.2f}")
    dados_btc = await _executar_ordem({
        "market_symbol": PAR_BTC_BRL,
        "side": "BUY",
        "type": "MARKET",
        "quote_quantity": str(round(valor_brl, 2)),
    })

    # Formato Foxbit: {"id": "...", "quantity": "0.00089", "quote_quantity": "500.00",
    #                  "price": "560000.00", "status": "FILLED", ...}
    btc_comprado = float(dados_btc.get("quantity") or 0)
    order_id_btc = str(dados_btc.get("id", "sem-id"))

    if btc_comprado <= 0:
        preco_btc = await obter_preco_btc_brl()
        btc_comprado = round(valor_brl / preco_btc, 8)
        logger.warning(f"Foxbit BTC sem qty — estimando {btc_comprado:.8f} BTC")

    logger.info(f"Foxbit passo 1 OK: {btc_comprado:.8f} BTC (order {order_id_btc})")

    # Passo 2 — Vender BTC por USDT
    logger.info(f"Foxbit passo 2: vendendo {btc_comprado:.8f} BTC por USDT")
    dados_usdt = await _executar_ordem({
        "market_symbol": PAR_BTC_USDT,
        "side": "SELL",
        "type": "MARKET",
        "quantity": str(btc_comprado),
    })

    usdt_recebido = float(dados_usdt.get("quote_quantity") or dados_usdt.get("quantity") or 0)
    order_id_usdt = str(dados_usdt.get("id", "sem-id"))

    if usdt_recebido <= 0:
        preco_usdt_brl = await obter_preco_usdt_brl()
        usdt_recebido = round(valor_brl / preco_usdt_brl, 2)
        logger.warning(f"Foxbit USDT sem qty — estimando {usdt_recebido:.2f} USDT")

    preco_medio = round(valor_brl / usdt_recebido, 4) if usdt_recebido > 0 else 0

    logger.info(
        f"Foxbit BRL→USDT concluído: R${valor_brl:.2f} → {usdt_recebido:.4f} USDT "
        f"| Preço médio: R${preco_medio:.4f}/USDT "
        f"| Orders: {order_id_btc}, {order_id_usdt}"
    )

    return {
        "usdt_comprado": round(usdt_recebido, 8),
        "preco_executado": preco_medio,
        "order_id": order_id_usdt,
        "status": dados_usdt.get("status", "FILLED"),
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
