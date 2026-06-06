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


def _texto_instrucoes(numero_cartao_cup: str, nome_titular: str, transacao_id: str) -> str:
    """Texto de instruções de pagamento enviado no chat do trade."""
    return (
        f"Realize o pagamento via Transfermovil ao cartao: {numero_cartao_cup}\n"
        f"Titular da conta: {nome_titular}\n"
        f"Referencia da transferencia: {transacao_id[:8].upper()}\n"
        f"Apos realizar o pagamento, envie o comprovante (screenshot) neste chat. "
        f"O USDT sera liberado assim que o pagamento for confirmado. "
        f"Prazo maximo para pagamento: 30 minutos."
    )


async def criar_oferta_venda(
    valor_usdt: float,
    numero_cartao_cup: str,
    nome_titular: str,
    transacao_id: str,
) -> dict:
    """
    Cria uma oferta de venda de USDT no Noones P2P.
    O comprador pagará CUP via Transfermovil para o cartão especificado.

    Campos confirmados pela API Noones (other-bank-transfer):
    - payment_method: "other-bank-transfer" — não exige bank_accounts, sem payment_method_label
    - default_flow_type: "default"
    - payment_details NÃO enviado: causa 500 para other-bank-transfer (bug Noones API)
      As instruções são enviadas via chat do trade em enviar_instrucoes_trade().
    - range_min/range_max: inteiros como string ("10" não "10.0")

    Returns:
        dict com: oferta_id, link_oferta, instrucoes (para envio no chat do trade)
    """
    # Noones exige range_min >= 10 USD. Validar antes de tentar criar a oferta.
    NOONES_MINIMO = 10
    if valor_usdt < NOONES_MINIMO:
        raise ValueError(
            f"Noones exige mínimo de {NOONES_MINIMO} USDT por oferta. "
            f"Valor solicitado: {valor_usdt:.4f} USDT. "
            f"Aumente o valor mínimo de envio ou use entrega manual."
        )

    # range_min = range_max = valor exato em USDT (arredondado para inteiro).
    # Isso força o comprador a comprar exatamente o valor da remessa.
    # Noones exige range_max > range_min, então max = min + 1.
    # API exige strings sem decimal ("10" não "10.0")
    range_min_int = max(NOONES_MINIMO, int(valor_usdt))  # nunca abaixo do mínimo Noones
    range_max_int = range_min_int + 1                     # exatamente 1 USDT acima do mínimo

    payload = {
        "crypto_currency_code": "USDT",
        "currency": "USD",
        # "other-bank-transfer": confirmado funcionando (Teste A/B).
        # payment_details NÃO enviado — causa 500 (bug da API Noones).
        # Instruções enviadas no chat do trade via enviar_instrucoes_trade().
        "payment_method": "other-bank-transfer",
        "offer_type_field": "sell",
        "margin": "0",
        "range_min": str(range_min_int),
        "range_max": str(range_max_int),
        "payment_window": "30",
        "default_flow_type": "default",
        "label": f"Remessa #{transacao_id[:8].upper()}",
    }

    logger.debug(f"Noones offer/create payload: {payload}")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{BASE_URL}/offer/create",
            headers=await _headers(),
            data=payload,  # form-encoded conforme docs Noones
        )
        logger.debug(f"Noones HTTP status: {resp.status_code} | body: {resp.text[:500]}")
        if not resp.is_success:
            raise RuntimeError(
                f"Noones HTTP {resp.status_code}: {resp.text[:400]}"
            )
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
        # instrucoes guardadas para enviar no chat quando o trade abrir
        "instrucoes": _texto_instrucoes(numero_cartao_cup, nome_titular, transacao_id),
    }


async def enviar_instrucoes_trade(trade_id: str, mensagem: str) -> bool:
    """
    Envia uma mensagem no chat do trade (ex: instruções de pagamento).
    Chamado quando um trade é aberto pelo comprador.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{BASE_URL}/trade/{trade_id}/chat",
                headers=await _headers(),
                data={"message": mensagem},
            )
            resp.raise_for_status()
            logger.info(f"Noones instrucoes enviadas no trade {trade_id}")
            return True
    except Exception as e:
        logger.error(f"Erro ao enviar instrucoes no trade {trade_id}: {e}")
        return False


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
    """Busca trades ativos de uma oferta pelo offer_hash."""
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


async def buscar_oferta_do_trade(trade_id: str) -> str:
    """Retorna o offer_hash associado a um trade_hash."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BASE_URL}/trade/{trade_id}",
                headers=await _headers("application/json"),
            )
            resp.raise_for_status()
            dados = resp.json().get("data", {})
            # A resposta pode ter offer_hash diretamente ou aninhado
            return (
                dados.get("offer_hash") or
                dados.get("trade", {}).get("offer_hash") or
                ""
            )
    except Exception as e:
        logger.error(f"Erro ao buscar offer_hash do trade {trade_id}: {e}")
        return ""


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
