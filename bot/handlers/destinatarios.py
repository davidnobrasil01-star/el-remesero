"""
Handler para gerenciamento de destinatários salvos.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db.repositories import destinatario_repo, usuario_repo
from bot.mensagens import (
    MSG_LISTA_DESTINATARIOS,
    MSG_CONFIRMAR_DELETAR,
    MSG_DESTINATARIO_DELETADO,
    MSG_SEM_DESTINATARIOS,
)
from bot.keyboards.menu_principal import voltar_ao_menu
from bot.keyboards.destinatarios import teclado_destinatarios


async def cb_destinatarios(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Exibe a lista de destinatários com opção de deletar."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    usuario = usuario_repo.buscar_por_telegram_id(user.id)
    if not usuario:
        await query.edit_message_text("Usuário não encontrado.", reply_markup=voltar_ao_menu())
        return

    destinatarios = destinatario_repo.listar_por_usuario(str(usuario.id))

    if not destinatarios:
        await query.edit_message_text(
            MSG_SEM_DESTINATARIOS,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]),
        )
        return

    await query.edit_message_text(
        MSG_LISTA_DESTINATARIOS,
        parse_mode="HTML",
        reply_markup=teclado_destinatarios(destinatarios, modo="gerenciar"),
    )


async def cb_deletar_destinatario(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pede confirmação antes de deletar."""
    query = update.callback_query
    await query.answer()

    dest_id = query.data.replace("del_", "")
    destinatario = destinatario_repo.buscar_por_id(dest_id)
    if not destinatario:
        await query.answer("Destinatário não encontrado.", show_alert=True)
        return

    context.user_data["del_dest_id"] = dest_id

    await query.edit_message_text(
        MSG_CONFIRMAR_DELETAR.format(apelido=destinatario.apelido),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Sim, remover", callback_data=f"confirmar_del_{dest_id}"),
                InlineKeyboardButton("❌ Cancelar", callback_data="destinatarios"),
            ]
        ]),
    )


async def cb_confirmar_deletar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Efetua a deleção do destinatário."""
    query = update.callback_query
    await query.answer()

    dest_id = query.data.replace("confirmar_del_", "")
    user = update.effective_user
    usuario = usuario_repo.buscar_por_telegram_id(user.id)

    destinatario = destinatario_repo.buscar_por_id(dest_id)
    apelido = destinatario.apelido if destinatario else "Destinatário"

    if usuario:
        destinatario_repo.deletar(dest_id, str(usuario.id))

    await query.edit_message_text(
        MSG_DESTINATARIO_DELETADO.format(apelido=apelido),
        parse_mode="HTML",
        reply_markup=voltar_ao_menu(),
    )
