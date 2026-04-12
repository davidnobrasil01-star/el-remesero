"""
Constrói e configura a aplicação PTB com todos os handlers registrados.
"""

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
)
from bot.handlers.start import cmd_start, cmd_ajuda, cb_menu, cb_ajuda
from bot.handlers.enviar_flow import criar_conversation_handler
from bot.handlers.historico import cb_historico
from bot.handlers.destinatarios import cb_destinatarios, cb_deletar_destinatario, cb_confirmar_deletar
from bot.handlers.admin import (
    cmd_admin,
    cmd_stats,
    cmd_entregar_manual,
    cmd_revisao,
    cmd_bloquear,
    cb_noones_aprovar,
    cb_noones_rejeitar,
    cb_entrega_ok,
    cb_entrega_falhou,
)
from config.settings import settings


def criar_application() -> Application:
    """Cria a Application PTB com todos os handlers configurados."""
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .build()
    )

    # Comandos
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_ajuda))
    app.add_handler(CommandHandler("ajuda", cmd_ajuda))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("admin_stats", cmd_stats))
    app.add_handler(CommandHandler("admin_entregar", cmd_entregar_manual))
    app.add_handler(CommandHandler("admin_revisao", cmd_revisao))
    app.add_handler(CommandHandler("admin_bloquear", cmd_bloquear))

    # ConversationHandler (fluxo de envio) — deve vir ANTES dos CallbackQueryHandlers genéricos
    app.add_handler(criar_conversation_handler())

    # Callbacks do menu
    app.add_handler(CallbackQueryHandler(cb_menu, pattern="^menu$"))
    app.add_handler(CallbackQueryHandler(cb_ajuda, pattern="^ajuda$"))
    app.add_handler(CallbackQueryHandler(cb_historico, pattern="^historico$"))
    app.add_handler(CallbackQueryHandler(cb_destinatarios, pattern="^destinatarios$"))
    app.add_handler(CallbackQueryHandler(cb_deletar_destinatario, pattern=r"^del_"))
    app.add_handler(CallbackQueryHandler(cb_confirmar_deletar, pattern=r"^confirmar_del_"))

    # Callbacks admin — entrega manual
    app.add_handler(CallbackQueryHandler(cb_entrega_ok, pattern=r"^entrega_ok_"))
    app.add_handler(CallbackQueryHandler(cb_entrega_falhou, pattern=r"^entrega_falhou_"))

    # Callbacks admin — aprovação Noones
    app.add_handler(CallbackQueryHandler(cb_noones_aprovar, pattern=r"^noones_aprovar_"))
    app.add_handler(CallbackQueryHandler(cb_noones_rejeitar, pattern=r"^noones_rejeitar_"))

    # Callback noop (botões já processados)
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern="^noop$"))

    return app
