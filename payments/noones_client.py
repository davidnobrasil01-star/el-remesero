"""
Cliente Noones P2P — venda de USDT com pagamento em CUP via Transfermovil.
Autenticação: OAuth 2.0 Client Credentials (client_id + client_secret → access_token).
Documentação: https://dev.noones.com/documentation/noones-api
"""

import time
import httpx
from loguru import logger
from config.settings import settings

BASE_URL = "https://api.noones.com/api/noones/v1"
TOKEN_URL = "https://auth.noones.com/oauth2/token"

# Cache do token para evitar chamadas desnecessárias
_token_cache: dict = {"access_token": None, "expires_at": 0.0}


async def _get_access_token() -> str:
    """
    Obtém (ou reutiliza do cache) um access token OAuth 2.0.
    Troca client_id + client_secret por Bearer token com TTL.
    """
    # Reutiliza se ainda válido (com 60s de margem)
    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]

    client_id = settings.noones_api_key          # client_id da chave gerada no portal
    client_secret = settings.noones_client_secret  # client_secret da chave gerada no portal

    if not client_id or not client_secret:
        raise RuntimeError("NOONES_API_KEY (client_id) e NOONES_CLIENT_SECRET não configurados")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        dados = resp.json()

    token = dados["access_token"]
    expires_in = dados.get("expires_in", 3600)

    _token_cache["access_token"] = token
    _token_cache["expires_at"] = time.time() + expires_in
    logger.debug(f"Noones token obtido (expira em {expires_in}s)")
    return token


async def _headers(content_type: str = "application/x-www-form-urlencoded") -> dict:
    token = await _get_access_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type,
        "Accept": "application/json; version=1",
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

    Returns:
        dict com: oferta_id, link_oferta
    """
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
        "margin": "0",
        "range_min": "1",
        "range_max": str(round(valor_usdt * 1.1, 2)),  # USD max ligeiramente acima
        "payment_window": "30",
        "payment_details": instrucoes,
        "offer_terms": instrucoes,
        "label": f"Remessa #{transacao_id[:8].upper()}",
        "require_verified_id": "false",
        "require_trusted_by_advertiser": "false",
    }

    logger.debug(f"Noones offer/create payload: {payload}")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{BASE_URL}/offer/create",
            headers=await _headers(),
            data=payload,  # form-encoded conforme docs Noones
        )
        logger.debug(f"Noones HTTP status: {resp.status_code} | body: {resp.text[:300]}")
        resp.raise_for_status()
        dados = resp.json()

    logger.debug(f"Noones offer/create resposta: {dados}")

    # Verifica status da resposta (Noones usa status no corpo, não só HTTP)
    if dados.get("status") != "success":
        erros = dados.get("errors") or dados.get("error") or dados
        raise RuntimeError(f"Noones recusou a oferta: {erros}")

    oferta_id = str(dados.get("data", {}).get("offer_hash", ""))
    if not oferta_id:
        raise RuntimeError(f"Noones não retornou offer_hash. Resposta: {dados}")

    logger.info(f"Noones oferta criada: {oferta_id} | {valor_usdt} USDT")

    return {
        "oferta_id": oferta_id,
        "link_oferta": f"https://noones.com/buy-usdt/{oferta_id}",
    }


async def listar_metodos_pagamento(busca: str = "") -> list:
    """
    Lista todos os métodos de pagamento disponíveis no Noones.
    Útil para descobrir o slug correto (ex: "transfermovil").
    busca: se fornecido, filtra resultados que contenham essa string.
    """
    resultados = []
    pagina = 1
    async with httpx.AsyncClient(timeout=15) as client:
        while True:
            resp = await client.get(
                f"{BASE_URL}/payment-method/list",
                headers=await _headers("application/json"),
                params={"page": pagina},
            )
            logger.debug(f"Noones payment-method/list p{pagina}: HTTP {resp.status_code} | {resp.text[:500]}")
            if resp.status_code != 200:
                break
            dados = resp.json()
            metodos = dados.get("data", {}).get("payment_methods", dados.get("data", []))
            if not metodos:
                break
            for m in metodos:
                if not busca or busca.lower() in str(m).lower():
                    resultados.append(m)
            # Próxima página
            total_pages = dados.get("data", {}).get("page_count", 1)
            if pagina >= total_pages:
                break
            pagina += 1
    return resultados


async def testar_criar_oferta_debug(valor_usdt: float = 10.0) -> dict:
    """
    Testa diferentes variações do payload de criação de oferta.
    Retorna um dict com os resultados de cada tentativa.
    """
    resultados = {}

    # Variações a testar
    variacoes = [
        ("transfermovil_form", {
            "currency": "USDT",
            "payment_method": "transfermovil",
            "type": "sell",
            "margin": "0",
            "range_min": "1",
            "range_max": str(round(valor_usdt * 1.1, 2)),
            "payment_window": "30",
            "payment_details": "teste",
            "offer_terms": "teste",
        }),
        ("transfermovil_offer_type_field", {
            "currency": "USDT",
            "payment_method": "transfermovil",
            "offer_type_field": "sell",
            "margin": "0",
            "range_min": "1",
            "range_max": str(round(valor_usdt * 1.1, 2)),
            "payment_window": "30",
            "payment_details": "teste",
            "offer_terms": "teste",
        }),
        ("bank_transfer_test", {
            "currency": "USDT",
            "payment_method": "bank-transfer",
            "type": "sell",
            "margin": "0",
            "range_min": "1",
            "range_max": str(round(valor_usdt * 1.1, 2)),
            "payment_window": "30",
            "payment_details": "teste",
            "offer_terms": "teste",
        }),
    ]

    async with httpx.AsyncClient(timeout=15) as client:
        for nome, payload in variacoes:
            try:
                resp = await client.post(
                    f"{BASE_URL}/offer/create",
                    headers=await _headers(),
                    data=payload,
                )
                resultados[nome] = {
                    "http_status": resp.status_code,
                    "body": resp.text[:400],
                }
                logger.info(f"Debug offer/create [{nome}]: {resp.status_code} | {resp.text[:300]}")
            except Exception as e:
                resultados[nome] = {"erro": str(e)}

    return resultados


async def desativar_oferta(oferta_id: str) -> bool:
    """Desativa uma oferta após ser completada ou cancelada."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{BASE_URL}/offer/{oferta_id}/deactivate",
                headers=await _headers(),
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
                headers=await _headers("application/json"),
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
                headers=await _headers("application/json"),
            )
            resp.raise_for_status()
            return resp.json().get("data", {}).get("messages", [])
    except Exception as e:
        logger.error(f"Erro ao buscar chat do trade {trade_id}: {e}")
        return []


async def liberar_usdt(trade_id: str) -> bool:
    """Libera o USDT do escrow para o comprador após aprovação do admin."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{BASE_URL}/trade/{trade_id}/release",
                headers=await _headers(),
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
                headers=await _headers(),
            )
            return resp.status_code == 200
    except Exception as e:
        logger.error(f"Erro ao cancelar trade Noones {trade_id}: {e}")
        return False
