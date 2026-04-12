"""
Calculadora de taxas e cotações.

Lógica de negócio:
  - Busca a taxa de mercado real (CUP/BRL) combinando Banco Central + ElToque
  - Oferta ao cliente a taxa configurada (ex: 97 CUP/BRL)
  - Garante margem mínima configurada
  - Calcula o valor USDT necessário para entregar o equivalente em CUP
"""

import httpx
from datetime import datetime
from loguru import logger
from config.settings import settings
from db.client import get_supabase


async def obter_taxa_brl_usd() -> float:
    """Obtém a cotação BRL/USD do Banco Central do Brasil."""
    try:
        hoje = datetime.utcnow().strftime("%m-%d-%Y")
        url = f"https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/CotacaoDolarDia(dataCotacao=@dataCotacao)?@dataCotacao='{hoje}'&$format=json&$select=cotacaoVenda"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            dados = resp.json()
            if dados.get("value"):
                taxa = float(dados["value"][-1]["cotacaoVenda"])
                await _salvar_cotacao_cache("BRL_USD", taxa, "bcb")
                return taxa
    except Exception as e:
        logger.warning(f"Erro ao buscar cotação BRL/USD do BCB: {e}")

    # Fallback: usar cache do banco
    return await _buscar_cotacao_cache("BRL_USD", fallback=5.70)


async def obter_taxa_usd_cup() -> float:
    """Obtém a cotação informal USD/CUP via ElToque."""
    try:
        url = "https://eltoque.com/tasas-de-cambio-de-moneda-en-cuba-hoy"
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            # ElToque publica JSON embutido na página — extraímos via API não oficial
        # Alternativa: API JSON direta do ElToque
        api_url = "https://api.eltoque.com/v1/trm?date="
        hoje_iso = datetime.utcnow().strftime("%Y-%m-%d")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{api_url}{hoje_iso}")
            resp.raise_for_status()
            dados = resp.json()
            cup_por_usd = float(dados.get("USD", {}).get("value", 0))
            if cup_por_usd > 0:
                await _salvar_cotacao_cache("USD_CUP", cup_por_usd, "eltoque")
                return cup_por_usd
    except Exception as e:
        logger.warning(f"Erro ao buscar cotação USD/CUP do ElToque: {e}")

    return await _buscar_cotacao_cache("USD_CUP", fallback=587.0)


async def obter_taxa_brl_cup() -> float:
    """
    Calcula a taxa BRL/CUP de mercado real.
    BRL → USD → CUP
    """
    try:
        brl_usd = await obter_taxa_brl_usd()
        usd_cup = await obter_taxa_usd_cup()
        taxa_mercado = usd_cup / brl_usd
        await _salvar_cotacao_cache("BRL_CUP_MERCADO", taxa_mercado, "calculado")
        return taxa_mercado
    except Exception as e:
        logger.error(f"Erro ao calcular taxa BRL/CUP: {e}")
        return await _buscar_cotacao_cache("BRL_CUP_MERCADO", fallback=103.0)


def calcular_cotacao_cliente() -> float:
    """
    Retorna a taxa ofertada ao cliente (configurada no .env).
    Ex: 97 CUP por R$1,00
    """
    return settings.taxa_ofertada_cup_por_brl


async def calcular_transacao(valor_brl: float) -> dict:
    """
    Calcula todos os valores de uma transação.

    Retorna:
        valor_brl: float — valor que o cliente paga
        taxa_cup_por_brl: float — taxa mostrada ao cliente
        valor_cup_destinatario: float — CUP que o destinatário recebe
        valor_usdt_necessario: float — USDT que precisamos enviar ao QvaPay
        taxa_mercado_brl_cup: float — taxa real de mercado (para calcular lucro)
        lucro_estimado_brl: float — lucro estimado da operação
    """
    taxa_cliente = calcular_cotacao_cliente()
    taxa_mercado = await obter_taxa_brl_cup()
    brl_usd = await obter_taxa_brl_usd()

    # CUP que o destinatário recebe
    valor_cup = round(valor_brl * taxa_cliente, 0)

    # USDT que precisamos enviar ao QvaPay
    # 1 USDT = ~1 USD, QvaPay interna converte USD → CUP pelo mercado
    usd_cup = taxa_mercado * brl_usd  # taxa mercado em CUP/USD
    valor_usdt = round(valor_cup / usd_cup, 8) if usd_cup > 0 else round(valor_brl / brl_usd * 0.97, 8)

    # Custo em BRL para cobrir o USDT enviado
    custo_brl = round(valor_usdt * brl_usd, 2)

    # Lucro estimado
    lucro_brl = round(valor_brl - custo_brl, 2)

    # Verificar margem mínima
    margem_cup = (taxa_mercado - taxa_cliente)
    if margem_cup < settings.margem_minima_cup_por_brl:
        logger.warning(
            f"Margem abaixo do mínimo: {margem_cup:.2f} CUP/BRL "
            f"(mínimo: {settings.margem_minima_cup_por_brl})"
        )

    return {
        "valor_brl": valor_brl,
        "taxa_cup_por_brl": taxa_cliente,
        "valor_cup_destinatario": valor_cup,
        "valor_usdt_necessario": valor_usdt,
        "taxa_mercado_brl_cup": round(taxa_mercado, 4),
        "lucro_estimado_brl": lucro_brl,
        "custo_brl": custo_brl,
    }


async def _salvar_cotacao_cache(par: str, taxa: float, fonte: str) -> None:
    try:
        sb = get_supabase()
        sb.table("cotacoes_cache").insert({
            "par": par,
            "taxa": taxa,
            "fonte": fonte,
        }).execute()
    except Exception as e:
        logger.debug(f"Erro ao salvar cotação no cache: {e}")


async def _buscar_cotacao_cache(par: str, fallback: float) -> float:
    try:
        sb = get_supabase()
        res = (
            sb.table("cotacoes_cache")
            .select("taxa")
            .eq("par", par)
            .order("obtido_em", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            return float(res.data[0]["taxa"])
    except Exception as e:
        logger.debug(f"Erro ao buscar cotação do cache: {e}")
    return fallback
