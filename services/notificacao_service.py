"""
Serviço de notificações Telegram — envia mensagens de status ao cliente
e alertas ao admin durante o ciclo de vida das transações.
"""

from loguru import logger
from db.repositories import transacao_repo, destinatario_repo, usuario_repo
from bot.mensagens import (
    MSG_PIX_CONFIRMADO,
    MSG_ENVIANDO_CUBA,
    MSG_ENTREGANDO,
    MSG_CONCLUIDO,
    MSG_FALHA,
)

_bot_app = None


def set_bot_app(app) -> None:
    """Define a instância do PTB Application para envio de mensagens."""
    global _bot_app
    _bot_app = app


async def _enviar_mensagem(telegram_id: int, texto: str, **kwargs) -> None:
    """Envia mensagem via PTB bot."""
    if _bot_app is None:
        logger.error("Bot app não configurado em notificacao_service")
        return
    try:
        await _bot_app.bot.send_message(chat_id=telegram_id, text=texto, parse_mode="HTML", **kwargs)
    except Exception as e:
        logger.error(f"Erro ao enviar notificação para {telegram_id}: {e}")


def _buscar_telegram_id(usuario_id: str) -> int | None:
    """Retorna o telegram_id de um usuário pelo seu ID interno."""
    from db.client import get_supabase
    sb = get_supabase()
    res = sb.table("usuarios").select("telegram_id").eq("id", usuario_id).maybe_single().execute()
    return res.data["telegram_id"] if res.data else None


async def notificar_pix_confirmado(transacao_id: str) -> None:
    """Notifica o cliente que o PIX foi confirmado e o envio está sendo processado."""
    transacao = transacao_repo.buscar_por_id(transacao_id)
    if not transacao:
        return
    destinatario = destinatario_repo.buscar_por_id(str(transacao.destinatario_id))
    telegram_id = _buscar_telegram_id(str(transacao.usuario_id))
    if not telegram_id:
        return
    nome = destinatario.nome_completo if destinatario else "seu familiar"
    texto = MSG_PIX_CONFIRMADO.format(nome=nome)
    await _enviar_mensagem(telegram_id, texto)


async def notificar_enviando_cuba(transacao_id: str) -> None:
    """Notifica o cliente que a transferência está a caminho de Cuba."""
    transacao = transacao_repo.buscar_por_id(transacao_id)
    if not transacao:
        return
    destinatario = destinatario_repo.buscar_por_id(str(transacao.destinatario_id))
    telegram_id = _buscar_telegram_id(str(transacao.usuario_id))
    if not telegram_id:
        return
    nome = destinatario.nome_completo if destinatario else "seu familiar"
    texto = MSG_ENVIANDO_CUBA.format(nome=nome)
    await _enviar_mensagem(telegram_id, texto)


async def notificar_concluido(transacao_id: str) -> None:
    """Notifica o cliente que a transferência foi concluída e envia o comprovante."""
    from services.comprovante_service import gerar_e_enviar_comprovante
    transacao = transacao_repo.buscar_por_id(transacao_id)
    if not transacao:
        return
    destinatario = destinatario_repo.buscar_por_id(str(transacao.destinatario_id))
    telegram_id = _buscar_telegram_id(str(transacao.usuario_id))
    if not telegram_id:
        return
    nome_dest = destinatario.nome_completo if destinatario else "seu familiar"
    texto = MSG_CONCLUIDO.format(nome=nome_dest, cup=f"{transacao.valor_cup_destinatario:,.0f}")
    await _enviar_mensagem(telegram_id, texto)
    await gerar_e_enviar_comprovante(transacao_id, telegram_id)


async def notificar_falha(transacao_id: str) -> None:
    """Notifica o cliente que houve um problema na transferência."""
    transacao = transacao_repo.buscar_por_id(transacao_id)
    if not transacao:
        return
    telegram_id = _buscar_telegram_id(str(transacao.usuario_id))
    if not telegram_id:
        return
    await _enviar_mensagem(telegram_id, MSG_FALHA)


async def alertar_admin_revisao_manual(transacao_id: str, erro: str) -> None:
    """Envia alerta ao admin sobre transação em revisão manual."""
    from config.settings import settings
    texto = (
        f"🚨 <b>REVISÃO MANUAL NECESSÁRIA</b>\n\n"
        f"Transação: <code>{transacao_id}</code>\n"
        f"Erro: {erro}\n\n"
        f"Use /admin_entregar {transacao_id} para processar manualmente."
    )
    await _enviar_mensagem(settings.admin_telegram_id, texto)
