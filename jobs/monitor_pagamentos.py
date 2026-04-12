"""
Job periódico de monitoramento de transações.
Roda a cada 5 minutos e:
  1. Expira transações com PIX não pago após 20 min
  2. Reprocessa transações travadas em pix_confirmado/convertendo/entregando
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


def registrar_job(app) -> None:
    """Registra o job de monitoramento na aplicação PTB."""
    app.job_queue.run_repeating(
        job_monitoramento,
        interval=300,   # 5 minutos
        first=60,       # Primeira execução após 1 min do início
        name="monitor_pagamentos",
    )
    logger.info("Job de monitoramento registrado (intervalo: 5 min)")
