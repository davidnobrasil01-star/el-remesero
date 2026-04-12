from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from db.models import Destinatario


def teclado_destinatarios(destinatarios: list[Destinatario], modo: str = "selecionar") -> InlineKeyboardMarkup:
    """
    Gera teclado com lista de destinatários.
    modo='selecionar': para escolher a quem enviar
    modo='gerenciar': para listar e deletar
    """
    botoes = []
    for dest in destinatarios:
        if modo == "selecionar":
            botoes.append([InlineKeyboardButton(
                f"👤 {dest.apelido} — {dest.nome_completo}",
                callback_data=f"dest_{dest.id}"
            )])
        else:
            botoes.append([
                InlineKeyboardButton(f"👤 {dest.apelido}", callback_data=f"ver_{dest.id}"),
                InlineKeyboardButton("🗑️", callback_data=f"del_{dest.id}"),
            ])

    botoes.append([InlineKeyboardButton("➕ Novo Destinatário", callback_data="novo_dest")])
    botoes.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    return InlineKeyboardMarkup(botoes)
