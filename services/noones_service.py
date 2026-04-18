"""
Serviço Noones — processa comprovantes P2P e encaminha ao admin para aprovação.
"""

import io
import httpx
from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config.settings import settings
from db.client import get_supabase
from db.repositories import transacao_repo
from db.models import StatusTransacao
from payments.noones_client import buscar_mensagens_trade, liberar_usdt, cancelar_trade


async def processar_comprovante_noones(trade_id: str, payload: dict) -> None:
    """
    Quando comprador marca como pago no Noones:
    1. Busca o comprovante no chat do trade
    2. Encaminha ao admin no Telegram para aprovação
    """
    from services.notificacao_service import _bot_app
    if not _bot_app:
        logger.error("Bot não disponível para encaminhar comprovante")
        return

    sb = get_supabase()

    # Busca transação pelo noones_trade_id
    res = sb.table("transacoes").select("*").eq("noones_trade_id", trade_id).execute()
    if not res or not res.data:
        logger.warning(f"Trade Noones {trade_id} não encontrado nas transações")
        return

    transacao_data = res.data[0]
    transacao_id = transacao_data["id"]

    # Atualizar status
    transacao_repo.atualizar_status(transacao_id, StatusTransacao.ENTREGANDO)

    # Buscar imagem do comprovante no chat do Noones
    mensagens = await buscar_mensagens_trade(trade_id)
    imagem_url = None
    for msg in reversed(mensagens):
        if msg.get("type") in ("image", "attachment") and msg.get("url"):
            imagem_url = msg["url"]
            break

    # Buscar dados do destinatário
    dest_res = sb.table("destinatarios").select("*").eq("id", transacao_data["destinatario_id"]).execute()
    nome_dest = dest_res.data[0]["nome_completo"] if dest_res and dest_res.data else "Destinatário"
    cartao = dest_res.data[0].get("numero_cartao", "N/A") if dest_res and dest_res.data else "N/A"
    valor_cup = transacao_data.get("valor_cup_destinatario", 0)
    valor_brl = transacao_data.get("valor_brl", 0)

    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Aprovar — liberar USDT", callback_data=f"noones_aprovar_{transacao_id}"),
            InlineKeyboardButton("❌ Rejeitar", callback_data=f"noones_rejeitar_{transacao_id}"),
        ]
    ])

    texto = (
        f"🔔 <b>COMPROVANTE RECEBIDO — APROVAÇÃO NECESSÁRIA</b>\n\n"
        f"🆔 Transação: <code>{transacao_id[:8].upper()}</code>\n"
        f"💰 Valor: R$ {valor_brl:.2f} → {valor_cup:,.0f} CUP\n"
        f"👤 Destinatário: {nome_dest}\n"
        f"💳 Cartão: {cartao}\n"
        f"🔗 Trade Noones: <code>{trade_id}</code>\n\n"
        f"Verifique o comprovante abaixo e aprove ou rejeite:"
    )

    await _bot_app.bot.send_message(
        chat_id=settings.admin_telegram_id,
        text=texto,
        parse_mode="HTML",
        reply_markup=teclado,
    )

    # Enviar imagem do comprovante se disponível
    if imagem_url:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(imagem_url)
                if resp.status_code == 200:
                    buf = io.BytesIO(resp.content)
                    buf.name = "comprovante.jpg"
                    await _bot_app.bot.send_photo(
                        chat_id=settings.admin_telegram_id,
                        photo=buf,
                        caption="📎 Comprovante enviado pelo comprador",
                    )
        except Exception as e:
            logger.error(f"Erro ao baixar comprovante Noones: {e}")
            await _bot_app.bot.send_message(
                chat_id=settings.admin_telegram_id,
                text=f"⚠️ Comprovante disponível no Noones: trade <code>{trade_id}</code>",
                parse_mode="HTML",
            )

    # Salvar URL do comprovante
    transacao_repo.atualizar_status(transacao_id, StatusTransacao.ENTREGANDO, {
        "comprovante_url": imagem_url or "",
    })


async def aprovar_trade(transacao_id: str) -> bool:
    """Admin aprovou — libera USDT no Noones e notifica cliente."""
    sb = get_supabase()
    res = sb.table("transacoes").select("noones_trade_id, usuario_id").eq("id", transacao_id).execute()
    if not res or not res.data:
        return False

    trade_id = res.data[0].get("noones_trade_id", "")
    if not trade_id:
        return False

    sucesso = await liberar_usdt(trade_id)
    if sucesso:
        transacao_repo.atualizar_status(transacao_id, StatusTransacao.CONCLUIDO, {
            "admin_aprovado": True,
        })
        from services.notificacao_service import notificar_concluido
        await notificar_concluido(transacao_id)
    return sucesso


async def rejeitar_trade(transacao_id: str) -> bool:
    """Admin rejeitou — cancela o trade no Noones e manda para revisão manual."""
    sb = get_supabase()
    res = sb.table("transacoes").select("noones_trade_id").eq("id", transacao_id).execute()
    if not res or not res.data:
        return False

    trade_id = res.data[0].get("noones_trade_id", "")
    sucesso = await cancelar_trade(trade_id) if trade_id else True
    if sucesso:
        transacao_repo.atualizar_status(transacao_id, StatusTransacao.REVISAO_MANUAL, {
            "observacoes": "Comprovante rejeitado pelo admin",
        })
    return sucesso
