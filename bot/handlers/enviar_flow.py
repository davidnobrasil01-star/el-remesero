"""
ConversationHandler completo do fluxo de envio de dinheiro.

Estados:
  SELECIONAR_DESTINATARIO
  → NOVO_DEST_METODO → NOVO_DEST_NUMERO_CARTAO → NOVO_DEST_NOME_TITULAR
  → NOVO_DESTINATARIO_NOME → CONFIRMAR_SALVAR_DESTINATARIO
  → INFORMAR_VALOR → MOSTRAR_COTACAO → AGUARDANDO_PIX
"""

import asyncio
import base64
import io
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from loguru import logger
from config.settings import settings
from bot.states import (
    SELECIONAR_DESTINATARIO,
    NOVO_DEST_METODO,
    NOVO_DEST_NUMERO_CARTAO,
    NOVO_DEST_NOME_TITULAR,
    NOVO_DESTINATARIO_NOME,
    CONFIRMAR_SALVAR_DESTINATARIO,
    INFORMAR_VALOR,
    MOSTRAR_COTACAO,
    AGUARDANDO_PIX,
)
from bot.mensagens import (
    MSG_SELECIONAR_DESTINATARIO,
    MSG_SEM_DESTINATARIOS,
    MSG_NOVO_DEST_METODO,
    MSG_NOVO_DEST_NUMERO_CARTAO,
    MSG_CARTAO_INVALIDO,
    MSG_NOVO_DEST_NOME_TITULAR,
    MSG_NOVO_DESTINATARIO_NOME,
    MSG_CONFIRMAR_SALVAR,
    MSG_DESTINATARIO_SALVO,
    MSG_INFORMAR_VALOR,
    MSG_VALOR_INVALIDO,
    MSG_COTACAO,
    MSG_AGUARDANDO_PIX,
    MSG_PIX_EXPIRADO,
    MSG_CANCELADO,
    MSG_ERRO_GENERICO,
)
from bot.keyboards.menu_principal import confirmar_ou_cancelar, sim_ou_nao, voltar_ao_menu
from bot.keyboards.destinatarios import teclado_destinatarios
from db.repositories import destinatario_repo, usuario_repo


def _teclado_metodo() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Cartão MLC", callback_data="metodo_mlc")],
        [InlineKeyboardButton("🪙 Pesos CUP", callback_data="metodo_cup")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")],
    ])


def _validar_cartao(numero: str) -> str | None:
    """Remove espaços/hifens e valida que são 16 dígitos. Retorna número limpo ou None."""
    limpo = re.sub(r"[\s\-]", "", numero)
    if re.fullmatch(r"\d{16}", limpo):
        return limpo
    return None


# ── Ponto de entrada ──────────────────────────────────────────────────────────

async def iniciar_envio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    usuario = usuario_repo.buscar_por_telegram_id(user.id)
    if not usuario:
        await query.edit_message_text(MSG_ERRO_GENERICO, parse_mode="HTML")
        return ConversationHandler.END

    destinatarios = destinatario_repo.listar_por_usuario(str(usuario.id))
    context.user_data["usuario_id"] = str(usuario.id)

    if not destinatarios:
        texto = MSG_SELECIONAR_DESTINATARIO + "\n\n" + MSG_SEM_DESTINATARIOS
    else:
        texto = MSG_SELECIONAR_DESTINATARIO

    teclado = teclado_destinatarios(destinatarios, modo="selecionar")
    await query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)
    return SELECIONAR_DESTINATARIO


# ── Destinatário existente ────────────────────────────────────────────────────

async def destinatario_selecionado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    dest_id = query.data.replace("dest_", "")
    destinatario = destinatario_repo.buscar_por_id(dest_id)
    if not destinatario:
        await query.edit_message_text(MSG_ERRO_GENERICO, parse_mode="HTML")
        return ConversationHandler.END

    context.user_data["destinatario_id"] = dest_id
    context.user_data["destinatario_nome"] = destinatario.nome_completo

    await query.edit_message_text(
        MSG_INFORMAR_VALOR.format(nome=destinatario.nome_completo),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]]),
    )
    return INFORMAR_VALOR


# ── Novo destinatário: método ─────────────────────────────────────────────────

async def novo_destinatario_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(MSG_NOVO_DEST_METODO, parse_mode="HTML", reply_markup=_teclado_metodo())
    return NOVO_DEST_METODO


async def receber_metodo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    metodo = "mlc" if query.data == "metodo_mlc" else "cup"
    context.user_data["novo_metodo"] = metodo

    label = "MLC" if metodo == "mlc" else "CUP"
    await query.edit_message_text(
        f"💳 <b>Cartão {label} do destinatário</b>\n\n" + MSG_NOVO_DEST_NUMERO_CARTAO,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]]),
    )
    return NOVO_DEST_NUMERO_CARTAO


# ── Novo destinatário: número do cartão ──────────────────────────────────────

async def receber_numero_cartao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    numero_limpo = _validar_cartao(update.message.text.strip())
    if not numero_limpo:
        await update.message.reply_text(MSG_CARTAO_INVALIDO, parse_mode="HTML")
        return NOVO_DEST_NUMERO_CARTAO

    context.user_data["novo_numero_cartao"] = numero_limpo
    await update.message.reply_text(MSG_NOVO_DEST_NOME_TITULAR, parse_mode="HTML")
    return NOVO_DEST_NOME_TITULAR


# ── Novo destinatário: nome do titular ───────────────────────────────────────

async def receber_nome_titular(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    nome = update.message.text.strip()[:80]
    if len(nome) < 3:
        await update.message.reply_text("❌ Nome muito curto. Digite o nome completo do titular:")
        return NOVO_DEST_NOME_TITULAR

    context.user_data["novo_nome_titular"] = nome
    await update.message.reply_text(MSG_NOVO_DESTINATARIO_NOME, parse_mode="HTML")
    return NOVO_DESTINATARIO_NOME


# ── Novo destinatário: apelido ────────────────────────────────────────────────

async def receber_nome_destinatario(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    apelido = update.message.text.strip()[:50]
    context.user_data["novo_apelido"] = apelido

    metodo = context.user_data.get("novo_metodo", "mlc")
    label_metodo = "💳 MLC (TropiPay)" if metodo == "mlc" else "🪙 CUP (Noones P2P)"
    cartao = context.user_data.get("novo_numero_cartao", "")
    cartao_fmt = f"{cartao[:4]} {cartao[4:8]} {cartao[8:12]} {cartao[12:]}"

    texto = (
        f"💾 Deseja salvar <b>{apelido}</b> como destinatário?\n\n"
        f"📋 <b>Resumo:</b>\n"
        f"• Nome: {context.user_data.get('novo_nome_titular')}\n"
        f"• Cartão: <code>{cartao_fmt}</code>\n"
        f"• Entrega: {label_metodo}"
    )
    await update.message.reply_text(
        texto,
        parse_mode="HTML",
        reply_markup=sim_ou_nao("salvar_dest_sim", "salvar_dest_nao"),
    )
    return CONFIRMAR_SALVAR_DESTINATARIO


# ── Confirmar salvar destinatário ─────────────────────────────────────────────

async def confirmar_salvar_destinatario(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    usuario_id = context.user_data["usuario_id"]
    metodo = context.user_data["novo_metodo"]
    numero_cartao = context.user_data["novo_numero_cartao"]
    nome = context.user_data["novo_nome_titular"]
    apelido = context.user_data["novo_apelido"]

    dest = destinatario_repo.criar(
        usuario_id=usuario_id,
        apelido=apelido,
        nome_completo=nome,
        metodo_entrega=metodo,
        numero_cartao=numero_cartao,
    )
    dest_id = str(dest.id)

    if query.data == "salvar_dest_sim":
        await query.edit_message_text(MSG_DESTINATARIO_SALVO.format(apelido=apelido), parse_mode="HTML")
    else:
        await query.edit_message_text(f"✅ Prosseguindo para <b>{apelido}</b>...", parse_mode="HTML")

    context.user_data["destinatario_id"] = dest_id
    context.user_data["destinatario_nome"] = nome

    await query.message.reply_text(
        MSG_INFORMAR_VALOR.format(nome=nome),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]]),
    )
    return INFORMAR_VALOR


# ── Valor ─────────────────────────────────────────────────────────────────────

async def receber_valor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text.strip().replace(",", ".")
    try:
        valor_brl = float(texto)
    except ValueError:
        await update.message.reply_text(MSG_VALOR_INVALIDO, parse_mode="HTML")
        return INFORMAR_VALOR

    if valor_brl < settings.limite_minimo_brl or valor_brl > settings.limite_maximo_brl:
        await update.message.reply_text(
            f"❌ Valor fora dos limites. Mínimo: R$ {settings.limite_minimo_brl:.2f} | Máximo: R$ {settings.limite_maximo_brl:.2f}",
            parse_mode="HTML",
        )
        return INFORMAR_VALOR

    await update.message.reply_text("📊 Calculando cotação...")

    from payments.calculadora_taxa import calcular_transacao
    cotacao = await calcular_transacao(valor_brl)
    context.user_data["valor_brl"] = valor_brl
    context.user_data["cotacao"] = cotacao

    nome_dest = context.user_data.get("destinatario_nome", "seu familiar")
    valor_cup_fmt = f"{cotacao['valor_cup_destinatario']:,.0f}".replace(",", ".")
    valor_brl_fmt = f"{valor_brl:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    taxa_fmt = f"{cotacao['taxa_cup_por_brl']:.0f}"

    texto_cotacao = MSG_COTACAO.format(
        valor_brl=valor_brl_fmt,
        valor_cup=valor_cup_fmt,
        taxa=taxa_fmt,
        nome_dest=nome_dest,
    )

    await update.message.reply_text(
        texto_cotacao,
        parse_mode="HTML",
        reply_markup=confirmar_ou_cancelar("confirmar_envio", "cancelar"),
    )
    return MOSTRAR_COTACAO


# ── Confirmar envio → PIX ─────────────────────────────────────────────────────

async def confirmar_envio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ Gerando cobrança PIX...", parse_mode="HTML")

    user = update.effective_user
    valor_brl = context.user_data["valor_brl"]
    destinatario_id = context.user_data["destinatario_id"]

    try:
        from services.transaction_service import iniciar_transacao
        resultado = await iniciar_transacao(
            telegram_id=user.id,
            destinatario_id=destinatario_id,
            valor_brl=valor_brl,
        )

        context.user_data["transacao_id"] = resultado["transacao_id"]

        copia_cola = resultado["pix_copia_cola"]
        transacao_id_curto = resultado["transacao_id"][:8].upper()

        texto_pix = MSG_AGUARDANDO_PIX.format(
            copia_cola=copia_cola,
            transacao_id=transacao_id_curto,
        )

        qr_base64 = resultado.get("pix_qr_code", "")
        if qr_base64:
            try:
                qr_bytes = base64.b64decode(qr_base64.split(",")[-1])
                buf = io.BytesIO(qr_bytes)
                buf.name = "pix_qrcode.png"
                await query.message.reply_photo(
                    photo=buf,
                    caption="📱 Escaneie este QR Code no seu banco para pagar via PIX",
                )
            except Exception:
                pass

        await query.edit_message_text(
            texto_pix,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]),
        )

        context.job_queue.run_once(
            _verificar_expiracao,
            when=1200,
            data={"transacao_id": resultado["transacao_id"], "chat_id": user.id},
            name=f"expiracao_{resultado['transacao_id']}",
        )

    except ValueError as e:
        await query.edit_message_text(f"❌ {e}", parse_mode="HTML", reply_markup=voltar_ao_menu())
    except Exception as e:
        logger.error(f"Erro ao criar transação para {user.id}: {e}")
        await query.edit_message_text(MSG_ERRO_GENERICO, parse_mode="HTML", reply_markup=voltar_ao_menu())

    return ConversationHandler.END


async def _verificar_expiracao(context: ContextTypes.DEFAULT_TYPE) -> None:
    dados = context.job.data
    transacao_id = dados["transacao_id"]
    chat_id = dados["chat_id"]

    from db.repositories.transacao_repo import buscar_por_id, atualizar_status
    from db.models import StatusTransacao

    transacao = buscar_por_id(transacao_id)
    if transacao and transacao.status == StatusTransacao.AGUARDANDO_PIX:
        atualizar_status(transacao_id, StatusTransacao.FALHOU, {"observacoes": "PIX expirado"})
        await context.bot.send_message(chat_id=chat_id, text=MSG_PIX_EXPIRADO, parse_mode="HTML")


# ── Cancelar ──────────────────────────────────────────────────────────────────

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(MSG_CANCELADO, parse_mode="HTML", reply_markup=voltar_ao_menu())
    else:
        await update.message.reply_text(MSG_CANCELADO, parse_mode="HTML", reply_markup=voltar_ao_menu())
    context.user_data.clear()
    return ConversationHandler.END


# ── ConversationHandler ───────────────────────────────────────────────────────

def criar_conversation_handler() -> ConversationHandler:
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _build_handler()


def _build_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(iniciar_envio, pattern="^enviar$")],
        per_message=False,
        states={
            SELECIONAR_DESTINATARIO: [
                CallbackQueryHandler(destinatario_selecionado, pattern=r"^dest_"),
                CallbackQueryHandler(novo_destinatario_inicio, pattern="^novo_dest$"),
                CallbackQueryHandler(cancelar, pattern="^cancelar$"),
            ],
            NOVO_DEST_METODO: [
                CallbackQueryHandler(receber_metodo, pattern=r"^metodo_(mlc|cup)$"),
                CallbackQueryHandler(cancelar, pattern="^cancelar$"),
            ],
            NOVO_DEST_NUMERO_CARTAO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receber_numero_cartao),
            ],
            NOVO_DEST_NOME_TITULAR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome_titular),
            ],
            NOVO_DESTINATARIO_NOME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome_destinatario),
            ],
            CONFIRMAR_SALVAR_DESTINATARIO: [
                CallbackQueryHandler(confirmar_salvar_destinatario, pattern=r"^salvar_dest_"),
            ],
            INFORMAR_VALOR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receber_valor),
                CallbackQueryHandler(cancelar, pattern="^cancelar$"),
            ],
            MOSTRAR_COTACAO: [
                CallbackQueryHandler(confirmar_envio, pattern="^confirmar_envio$"),
                CallbackQueryHandler(cancelar, pattern="^cancelar$"),
            ],
        },
        fallbacks=[CallbackQueryHandler(cancelar, pattern="^cancelar$")],
        allow_reentry=True,
    )
