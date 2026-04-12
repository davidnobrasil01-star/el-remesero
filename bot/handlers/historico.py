"""
Handler de histórico de transações.
"""

from telegram import Update
from telegram.ext import ContextTypes
from db.repositories import transacao_repo, usuario_repo, destinatario_repo
from bot.mensagens import (
    MSG_HISTORICO_VAZIO,
    MSG_HISTORICO_ITEM,
    STATUS_EMOJI,
    STATUS_LABEL,
)
from bot.keyboards.menu_principal import voltar_ao_menu


async def cb_historico(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Exibe as últimas 10 transações do usuário."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    usuario = usuario_repo.buscar_por_telegram_id(user.id)
    if not usuario:
        await query.edit_message_text("Usuário não encontrado.", reply_markup=voltar_ao_menu())
        return

    transacoes = transacao_repo.listar_por_usuario(str(usuario.id), limite=10)

    if not transacoes:
        await query.edit_message_text(
            MSG_HISTORICO_VAZIO,
            parse_mode="HTML",
            reply_markup=voltar_ao_menu(),
        )
        return

    linhas = ["📋 <b>Suas últimas transferências:</b>\n"]
    for t in transacoes:
        dest = destinatario_repo.buscar_por_id(str(t.destinatario_id))
        nome_dest = dest.apelido if dest else "Desconhecido"
        data_fmt = t.criado_em.strftime("%d/%m/%Y") if t.criado_em else "—"
        valor_cup_fmt = f"{t.valor_cup_destinatario:,.0f}".replace(",", ".")
        valor_brl_fmt = f"R$ {t.valor_brl:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        status_key = t.status
        emoji = STATUS_EMOJI.get(status_key, "❓")
        label = STATUS_LABEL.get(status_key, status_key)

        linhas.append(MSG_HISTORICO_ITEM.format(
            data=data_fmt,
            destinatario=nome_dest,
            valor_brl=valor_brl_fmt,
            valor_cup=valor_cup_fmt,
            status_emoji=emoji,
            status=label,
        ))

    await query.edit_message_text(
        "\n".join(linhas),
        parse_mode="HTML",
        reply_markup=voltar_ao_menu(),
    )
