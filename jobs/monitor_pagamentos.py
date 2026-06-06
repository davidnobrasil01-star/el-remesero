"""
Job periódico de monitoramento de transações.
Roda a cada 5 minutos e:
  1. Expira transações com PIX não pago após 20 min
  2. Reprocessa transações travadas em pix_confirmado/convertendo
  3. Monitora trades Noones: detecta novos trades, envia instruções no chat,
     atualiza noones_trade_id (offer_hash → trade_hash real)
"""

from loguru import logger
from telegram.ext import ContextTypes
from db.repositories.transacao_repo import (
    buscar_pendentes_expiradas,
    buscar_travadas_para_reprocessar,
    atualizar_status,
)
from db.models import StatusTransacao


async def job_monitoramento(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job principal de monitoramento."""
    await _expirar_pix_vencidos(context)
    await _reprocessar_travadas()
    await _monitorar_trades_noones()


async def _expirar_pix_vencidos(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Marca como falhou as transações com PIX expirado."""
    expiradas = buscar_pendentes_expiradas()
    if not expiradas:
        return

    logger.info(f"Monitoramento: {len(expiradas)} transações PIX expiradas encontradas")

    for transacao in expiradas:
        atualizar_status(
            str(transacao.id),
            StatusTransacao.FALHOU,
            {"observacoes": "PIX expirou sem pagamento"},
        )

        # Notificar usuário
        try:
            from db.client import get_supabase
            sb = get_supabase()
            res = sb.table("usuarios").select("telegram_id").eq("id", str(transacao.usuario_id)).maybe_single().execute()
            if res.data:
                from bot.mensagens import MSG_PIX_EXPIRADO
                await context.bot.send_message(
                    chat_id=res.data["telegram_id"],
                    text=MSG_PIX_EXPIRADO,
                    parse_mode="HTML",
                )
        except Exception as e:
            logger.error(f"Erro ao notificar expiração para transação {transacao.id}: {e}")


async def _reprocessar_travadas() -> None:
    """Tenta reprocessar transações paradas há mais de 5 minutos."""
    travadas = buscar_travadas_para_reprocessar()
    if not travadas:
        return

    logger.info(f"Monitoramento: {len(travadas)} transações travadas para reprocessar")

    from services.delivery_service import entregar_transacao
    for transacao in travadas:
        try:
            logger.info(f"Reprocessando transação travada: {transacao.id}")
            await entregar_transacao(str(transacao.id))
        except Exception as e:
            logger.error(f"Erro ao reprocessar transação {transacao.id}: {e}")


async def _monitorar_trades_noones() -> None:
    """
    Para cada transação AGUARDANDO_COMPRADOR, busca trades ativos no Noones.
    Quando um trade novo é detectado:
      - Envia instruções de pagamento no chat do trade
      - Atualiza noones_trade_id com o trade_hash real (sobrescreve offer_hash)
    """
    from db.client import get_supabase
    from payments.noones_client import buscar_trades_oferta, enviar_instrucoes_trade, _texto_instrucoes
    from db.repositories import destinatario_repo

    sb = get_supabase()
    res = sb.table("transacoes").select(
        "id, noones_trade_id, destinatario_id, valor_brl, valor_usdt"
    ).eq("status", StatusTransacao.AGUARDANDO_COMPRADOR).execute()

    if not res.data:
        return

    logger.debug(f"Monitor Noones: {len(res.data)} ofertas aguardando comprador")

    for row in res.data:
        transacao_id = row["id"]
        offer_hash = row.get("noones_trade_id", "")

        # noones_trade_id pode já ser um trade_hash (se já foi atualizado)
        # Detecta: offer_hashes têm ~11 chars; trade_hashes têm ~10 chars — ambiguidade.
        # Convencão: se começa com "trade_processado:" já foi tratado. Caso contrário tentamos.
        if not offer_hash or offer_hash.startswith("trade_"):
            continue

        try:
            trades = await buscar_trades_oferta(offer_hash)
        except Exception as e:
            logger.error(f"Erro ao buscar trades para oferta {offer_hash}: {e}")
            continue

        if not trades:
            continue

        # Pega o trade mais recente (status "active" ou "paid")
        trade = trades[0]
        trade_hash = trade.get("trade_hash") or trade.get("id", "")
        if not trade_hash:
            continue

        logger.info(f"Monitor Noones: trade {trade_hash} detectado para oferta {offer_hash} | tx {transacao_id[:8]}")

        # Busca dados do destinatário para montar as instruções
        dest = destinatario_repo.buscar_por_id(str(row["destinatario_id"]))
        if dest:
            instrucoes = _texto_instrucoes(
                numero_cartao_cup=dest.numero_cartao or "",
                nome_titular=dest.nome_completo,
                transacao_id=transacao_id,
            )
            await enviar_instrucoes_trade(trade_hash, instrucoes)

        # Atualiza noones_trade_id com o trade_hash real
        # (prefix "trade_" para não reprocessar na próxima iteração)
        atualizar_status(transacao_id, StatusTransacao.AGUARDANDO_COMPRADOR, {
            "noones_trade_id": f"trade_{trade_hash}",
        })
        logger.info(f"Monitor Noones: noones_trade_id atualizado → trade_{trade_hash}")


def registrar_job(app) -> None:
    """Registra o job de monitoramento na aplicação PTB."""
    app.job_queue.run_repeating(
        job_monitoramento,
        interval=300,   # 5 minutos
        first=60,       # Primeira execução após 1 min do início
        name="monitor_pagamentos",
    )
    logger.info("Job de monitoramento registrado (intervalo: 5 min)")
