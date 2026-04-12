"""
Handlers de /start, /help e menu principal.
"""

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from loguru import logger
from db.repositories import usuario_repo
from bot.mensagens import MSG_START, MSG_AJUDA, MSG_USUARIO_BLOQUEADO
from bot.keyboards.menu_principal import menu_principal, voltar_ao_menu


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler do comando /start."""
    user = update.effective_user
    logger.info(f"/start de {user.id} (@{user.username})")

    # Registrar/atualizar usuário no banco
    usuario_repo.criar_ou_atualizar(
        telegram_id=user.id,
        username=user.username,
        nome_completo=user.full_name,
    )

    # Verificar bloqueio
    if usuario_repo.esta_bloqueado(user.id):
        await update.message.reply_text(MSG_USUARIO_BLOQUEADO, parse_mode="HTML")
        return

    nome = user.first_name or user.username or "amigo(a)"
    await update.message.reply_text(
        MSG_START.format(nome=nome),
        parse_mode="HTML",
        reply_markup=menu_principal(),
    )


async def cmd_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler do comando /help."""
    await update.message.reply_text(MSG_AJUDA, parse_mode="HTML", reply_markup=voltar_ao_menu())


async def cb_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Volta ao menu principal via callback."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    nome = user.first_name or "amigo(a)"
    await query.edit_message_text(
        MSG_START.format(nome=nome),
        parse_mode="HTML",
        reply_markup=menu_principal(),
    )


async def cb_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra ajuda via callback."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(MSG_AJUDA, parse_mode="HTML", reply_markup=voltar_ao_menu())
