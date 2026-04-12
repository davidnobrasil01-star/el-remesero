"""
Comandos administrativos — restritos ao ADMIN_TELEGRAM_ID.
"""

from functools import wraps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from loguru import logger
from config.settings import settings
from db.repositories import transacao_repo
from db.models import StatusTransacao


def apenas_admin(func):
    """Decorator que bloqueia o comando se não for o admin."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != settings.admin_telegram_id:
            if update.message:
                await update.message.reply_text("⛔ Acesso negado.")
            return
        return await func(update, context)
    return wrapper


def apenas_admin_callback(func):
    """Decorator para callbacks que bloqueia se não for o admin."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != settings.admin_telegram_id:
            await update.callback_query.answer("⛔ Acesso negado.", show_alert=True)
            return
        return await func(update, context)
    return wrapper


@apenas_admin
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    texto = (
        "🛠️ <b>Painel Admin — El Remesero</b>\n\n"
        "Comandos disponíveis:\n"
        "/admin_stats — Estatísticas gerais\n"
        "/admin_entregar [id] — Entregar transação manualmente\n"
        "/admin_bloquear [telegram_id] — Bloquear usuário\n"
        "/admin_revisao — Listar transações em revisão manual\n"
    )
    await update.message.reply_text(texto, parse_mode="HTML")


@apenas_admin
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from db.client import get_supabase
    sb = get_supabase()

    total_res = sb.table("transacoes").select("valor_brl, status").eq("status", "concluido").execute()
    total_transacoes = len(total_res.data)
    total_brl = sum(t["valor_brl"] for t in total_res.data)

    pendentes = sb.table("transacoes").select("id").in_("status", ["aguardando_pix", "pix_confirmado", "convertendo", "entregando"]).execute()
    revisao = sb.table("transacoes").select("id").eq("status", "revisao_manual").execute()
    usuarios = sb.table("usuarios").select("id").execute()

    await update.message.reply_text(
        f"📊 <b>Estatísticas</b>\n\n"
        f"✅ Transações concluídas: <b>{total_transacoes}</b>\n"
        f"💰 Volume total: <b>R$ {total_brl:,.2f}</b>\n"
        f"⏳ Em andamento: <b>{len(pendentes.data)}</b>\n"
        f"⚠️ Revisão manual: <b>{len(revisao.data)}</b>\n"
        f"👤 Usuários cadastrados: <b>{len(usuarios.data)}</b>",
        parse_mode="HTML",
    )


@apenas_admin
async def cmd_entregar_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Uso: /admin_entregar [transacao_id]")
        return

    transacao_id = context.args[0]
    transacao = transacao_repo.buscar_por_id(transacao_id)

    if not transacao:
        await update.message.reply_text(f"❌ Transação {transacao_id} não encontrada.")
        return

    logger.info(f"Admin: entrega manual da transação {transacao_id}")
    transacao_repo.atualizar_status(
        transacao_id,
        StatusTransacao.PIX_CONFIRMADO,
        {"tentativas_entrega": 0},
    )

    from services.delivery_service import entregar_transacao
    sucesso = await entregar_transacao(transacao_id)

    if sucesso:
        await update.message.reply_text(f"✅ Transação {transacao_id[:8].upper()} entregue com sucesso!")
    else:
        await update.message.reply_text(f"❌ Falha na entrega da transação {transacao_id[:8].upper()}. Verifique os logs.")


@apenas_admin
async def cmd_revisao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from db.client import get_supabase
    sb = get_supabase()
    res = sb.table("transacoes").select("id, valor_brl, criado_em, observacoes").eq("status", "revisao_manual").order("criado_em", desc=True).execute()

    if not res.data:
        await update.message.reply_text("✅ Nenhuma transação em revisão manual.")
        return

    linhas = ["⚠️ <b>Transações em Revisão Manual:</b>\n"]
    for t in res.data:
        data = t.get("criado_em", "")[:10]
        linhas.append(
            f"• <code>{t['id'][:8].upper()}</code> | R$ {t['valor_brl']:.2f} | {data}\n"
            f"  <i>{t.get('observacoes', 'sem detalhes')[:80]}</i>"
        )
    await update.message.reply_text("\n".join(linhas), parse_mode="HTML")


@apenas_admin
async def cmd_bloquear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Uso: /admin_bloquear [telegram_id]")
        return
    telegram_id = int(context.args[0])
    from db.client import get_supabase
    sb = get_supabase()
    sb.table("usuarios").update({"bloqueado": True}).eq("telegram_id", telegram_id).execute()
    await update.message.reply_text(f"🚫 Usuário {telegram_id} bloqueado.")


# ── Callbacks Entrega Manual ─────────────────────────────────────────────────

@apenas_admin_callback
async def cb_entrega_ok(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin confirmou entrega — marca transação como concluída."""
    query = update.callback_query
    await query.answer("Marcando como concluído...")

    transacao_id = query.data.replace("entrega_ok_", "")
    try:
        from services.delivery_service import concluir_entrega_manual
        await concluir_entrega_manual(transacao_id)
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ CONCLUÍDO", callback_data="noop")
            ]])
        )
    except Exception as e:
        logger.error(f"Erro ao concluir entrega manual {transacao_id}: {e}")
        await query.message.reply_text(f"❌ Erro: {e}")


@apenas_admin_callback
async def cb_entrega_falhou(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin marcou entrega como falhou — manda para revisão manual."""
    query = update.callback_query
    await query.answer("Marcando como falhou...")

    transacao_id = query.data.replace("entrega_falhou_", "")
    try:
        from services.delivery_service import falhar_entrega_manual
        await falhar_entrega_manual(transacao_id)
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ FALHOU — EM REVISÃO", callback_data="noop")
            ]])
        )
    except Exception as e:
        logger.error(f"Erro ao marcar falha manual {transacao_id}: {e}")
        await query.message.reply_text(f"❌ Erro: {e}")


# ── Callbacks Noones — aprovação de comprovante ───────────────────────────────

@apenas_admin_callback
async def cb_noones_aprovar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin aprova o comprovante → libera USDT e conclui transação."""
    query = update.callback_query
    await query.answer("Aprovando...")

    transacao_id = query.data.replace("noones_aprovar_", "")
    logger.info(f"Admin aprovou Noones trade — transação {transacao_id}")

    try:
        from services.noones_service import aprovar_trade
        await aprovar_trade(transacao_id)
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ APROVADO", callback_data="noop")
            ]])
        )
    except Exception as e:
        logger.error(f"Erro ao aprovar trade Noones {transacao_id}: {e}")
        await query.message.reply_text(f"❌ Erro ao aprovar: {e}")


@apenas_admin_callback
async def cb_noones_rejeitar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin rejeita o comprovante → cancela trade e envia para revisão manual."""
    query = update.callback_query
    await query.answer("Rejeitando...")

    transacao_id = query.data.replace("noones_rejeitar_", "")
    logger.info(f"Admin rejeitou Noones trade — transação {transacao_id}")

    try:
        from services.noones_service import rejeitar_trade
        await rejeitar_trade(transacao_id)
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ REJEITADO", callback_data="noop")
            ]])
        )
    except Exception as e:
        logger.error(f"Erro ao rejeitar trade Noones {transacao_id}: {e}")
        await query.message.reply_text(f"❌ Erro ao rejeitar: {e}")
