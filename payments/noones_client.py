"""
Cliente Noones P2P — venda de USDT com pagamento em CUP via Transfermovil.
Autenticação: OAuth 2.0 Client Credentials (client_id + client_secret → access_token).
Documentação: https://dev.noones.com/documentation/noones-api
"""

import time
import httpx
from loguru import logger
from config.settings import settings

BASE_URL = "https://api.noones.com/noones/v1"
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
        "crypto_currency_code": "USDT",              # campo correcto (não "currency")
        "payment_method": "bank-transfer",
        "payment_method_label": "Transfermovil CUP",
        "offer_type_field": "sell",
        "margin": "0",
        "range_min": "1",
        "range_max": str(round(valor_usdt * 1.1, 2)),
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


async def buscar_slug_por_palavra(palavra: str) -> list:
    """
    Busca el slug correcto probando diferentes rutas del endpoint payment-method.
    Retorna lista de métodos que contienen la palabra buscada.
    """
    token = await _get_access_token()
    headers_auth = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    rutas_candidatas = [
        f"GET {BASE_URL}/payment-method/list",
        f"GET {BASE_URL}/payment-methods",
        f"GET {BASE_URL}/payment-method",
        f"GET {BASE_URL}/offer/payment-methods",
        f"POST {BASE_URL}/payment-method/list",
    ]

    resultados = []
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        for ruta in rutas_candidatas:
            metodo_http, url = ruta.split(" ", 1)
            try:
                if metodo_http == "GET":
                    resp = await client.get(url, headers=headers_auth, params={"page": 1})
                else:
                    resp = await client.post(url, headers=headers_auth, json={"page": 1})
                logger.info(f"payment-method probe [{ruta}]: {resp.status_code} | {resp.text[:400]}")
                if resp.status_code == 200:
                    data = resp.json()
                    metodos = (
                        data.get("data", {}).get("payment_methods") or
                        data.get("data", []) or
                        data.get("payment_methods", [])
                    )
                    for m in metodos:
                        slug = m.get("slug") or m.get("code") or m.get("id") or ""
                        nome = m.get("name") or m.get("label") or ""
                        if palavra.lower() in (str(slug) + str(nome)).lower():
                            resultados.append({"ruta": ruta, "slug": slug, "nome": nome, "raw": str(m)[:200]})
                    if metodos:
                        # Encontrou métodos — retorna todos que matcham
                        return resultados or [{"ruta": ruta, "total": len(metodos), "primeiros": str(metodos[:5])}]
            except Exception as e:
                logger.debug(f"Erro probe {ruta}: {e}")
    return resultados


async def testar_urls_base() -> dict:
    """
    Testa diferentes base URLs do Noones para encontrar a correta.
    Usa o endpoint GET /payment-method/list como sonda.
    """
    token = await _get_access_token()
    headers_auth = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    urls_candidatas = [
        ("api.noones.com/api/noones/v1", "https://api.noones.com/api/noones/v1/payment-method/list"),
        ("api.noones.com/noones/v1",     "https://api.noones.com/noones/v1/payment-method/list"),
        ("api.noones.com/v1",            "https://api.noones.com/v1/payment-method/list"),
        ("noones.com/api/noones/v1",     "https://noones.com/api/noones/v1/payment-method/list"),
        ("noones.com/api/v1",            "https://noones.com/api/v1/payment-method/list"),
    ]

    resultados = {}
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        for nome, url in urls_candidatas:
            try:
                resp = await client.get(url, headers=headers_auth)
                resultados[nome] = {
                    "http_status": resp.status_code,
                    "body": resp.text[:300],
                }
                logger.info(f"URL probe [{nome}]: {resp.status_code} | {resp.text[:200]}")
            except Exception as e:
                resultados[nome] = {"erro": str(e)}

    return resultados


async def testar_criar_oferta_debug(valor_usdt: float = 10.0) -> dict:
    """
    Prueba el payload correcto con bank-transfer + Transfermovil CUP label.
    También prueba offer_type_field vs type para confirmar el campo correcto.
    """
    casos = {
        "crypto_currency_code_USDT": {
            "crypto_currency_code": "USDT",
            "payment_method": "bank-transfer",
            "payment_method_label": "Transfermovil CUP",
            "offer_type_field": "sell",
            "margin": "0",
            "range_min": "1",
            "range_max": str(round(valor_usdt * 1.1, 2)),
            "payment_window": "30",
            "payment_details": "DIAGNÓSTICO",
            "offer_terms": "DIAGNÓSTICO",
        },
        "currency_USDT_fallback": {
            "currency": "USDT",
            "crypto_currency_code": "USDT",
            "payment_method": "bank-transfer",
            "payment_method_label": "Transfermovil CUP",
            "offer_type_field": "sell",
            "margin": "0",
            "range_min": "1",
            "range_max": str(round(valor_usdt * 1.1, 2)),
            "payment_window": "30",
            "payment_details": "DIAGNÓSTICO",
            "offer_terms": "DIAGNÓSTICO",
        },
    }

    resultados = {}
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        for nome, payload in casos.items():
            try:
                resp = await client.post(
                    f"{BASE_URL}/offer/create",
                    headers=await _headers(),
                    data=payload,
                )
                body = resp.text[:400]
                resultados[nome] = {"http_status": resp.status_code, "body": body}
                logger.info(f"Offer test [{nome}]: HTTP {resp.status_code} | {body}")
            except Exception as e:
                resultados[nome] = {"http_status": "ERR", "body": str(e)}

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
