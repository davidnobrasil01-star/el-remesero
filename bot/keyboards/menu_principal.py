from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def menu_principal() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💸 Enviar Dinheiro", callback_data="enviar")],
        [InlineKeyboardButton("👥 Meus Destinatários", callback_data="destinatarios")],
        [InlineKeyboardButton("📋 Histórico", callback_data="historico")],
        [InlineKeyboardButton("ℹ️ Ajuda", callback_data="ajuda")],
    ])


def confirmar_ou_cancelar(confirmar_data: str = "confirmar", cancelar_data: str = "cancelar") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirmar", callback_data=confirmar_data),
            InlineKeyboardButton("❌ Cancelar", callback_data=cancelar_data),
        ]
    ])


def sim_ou_nao(sim_data: str = "sim", nao_data: str = "nao") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Sim", callback_data=sim_data),
            InlineKeyboardButton("❌ Não", callback_data=nao_data),
        ]
    ])


def voltar_ao_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Menu Principal", callback_data="menu")]
    ])
