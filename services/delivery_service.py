"""
Serviço de entrega — roteia para automático (TropiPay/Noones) ou manual.
Modo manual ativo quando Binance ou TropiPay/Noones não estão configurados.
"""

import asyncio
from loguru import logger
from config.settings import settings
from db.models import StatusTransacao
from db.repositories import transacao_repo, destinatario_repo
from telegram import InlineKeyboardMarkup, InlineKeyboardButton


def _modo_automatico_disponivel() -> bool:
    """Retorna True apenas se Binance + pelo menos um gateway de entrega estiver configurado."""
    tem_binance = bool(settings.binance_api_key and settings.binance_api_secret)
    tem_tropipay = bool(settings.tropipay_client_id and settings.tropipay_client_secret)
    tem_noones = bool(settings.noones_api_key)
    return tem_binance and (tem_tropipay or tem_noones)


async def entregar_transacao(transacao_id: str) -> bool:
    """Ponto de entrada principal — decide entre automático e manual."""
    if _modo_automatico_disponivel():
        return await _entregar_automatico(transacao_id)
    else:
        return await _entregar_manual(transacao_id)


# ── Modo Manual ───────────────────────────────────────────────────────────────

async def _entregar_manual(transacao_id: str) -> bool:
    """
    Modo manual: notifica o admin com todos os dados e botões de confirmação.
    O admin faz a entrega manualmente e clica em Concluído ou Falhou.
    """
    from services.notificacao_service import _bot_app

    transacao = transacao_repo.buscar_por_id(transacao_id)
    if not transacao:
        logger.error(f"Entrega manual: transação não encontrada {transacao_id}")
        return False

    destinatario = destinatario_repo.buscar_por_id(str(transacao.destinatario_id))
    if not destinatario:
        logger.error(f"Entrega manual: destinatário não encontrado")
        return False

    transacao_repo.atualizar_status(transacao_id, StatusTransacao.ENTREGANDO)

    metodo = destinatario.metodo_entrega or "mlc"
    metodo_label = "MLC (cartão Visa)" if metodo == "mlc" else "CUP (Transfermovil)"
    cup_fmt = f"{transacao.valor_cup_destinatario:,.0f}".replace(",", ".")

    texto = (
        f"🔔 <b>NOVA ENTREGA PENDENTE</b>\n\n"
        f"🆔 <code>{transacao_id[:8].upper()}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Destinatário: <b>{destinatario.nome_completo}</b>\n"
        f"💳 Cartão: <code>{destinatario.numero_cartao}</code>\n"
        f"📦 Método: {metodo_label}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Valor a entregar: <b>{cup_fmt} CUP</b>\n"
        f"   (equivale a R$ {transacao.valor_brl:.2f} BRL)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Faça a entrega e confirme abaixo:"
    )

    botoes = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Entregue!", callback_data=f"entrega_ok_{transacao_id}"),
            InlineKeyboardButton("❌ Falhou", callback_data=f"entrega_falhou_{transacao_id}"),
        ]
    ])

    if _bot_app:
        await _bot_app.bot.send_message(
            chat_id=settings.admin_telegram_id,
            text=texto,
            parse_mode="HTML",
            reply_markup=botoes,
        )
        logger.info(f"Entrega manual enviada ao admin: {transacao_id}")

    return True


async def concluir_entrega_manual(transacao_id: str) -> None:
    """Chamado pelo admin via callback — marca transação como concluída."""
    transacao_repo.atualizar_status(transacao_id, StatusTransacao.CONCLUIDO)
    from services.notificacao_service import notificar_concluido
    await notificar_concluido(transacao_id)
    logger.info(f"Entrega manual concluída pelo admin: {transacao_id}")


async def falhar_entrega_manual(transacao_id: str) -> None:
    """Chamado pelo admin via callback — marca transação como revisão manual."""
    transacao_repo.atualizar_status(transacao_id, StatusTransacao.REVISAO_MANUAL, {
        "observacoes": "Admin marcou como falhou na entrega manual",
    })
    from services.notificacao_service import notificar_falha
    await notificar_falha(transacao_id)
    logger.info(f"Entrega manual falhou (marcado pelo admin): {transacao_id}")


# ── Modo Automático ───────────────────────────────────────────────────────────

async def _entregar_automatico(transacao_id: str) -> bool:
    """Entrega automática via Binance + TropiPay/Noones."""
    transacao = transacao_repo.buscar_por_id(transacao_id)
    destinatario = destinatario_repo.buscar_por_id(str(transacao.destinatario_id))
    metodo = destinatario.metodo_entrega or "mlc"

    tentativa = transacao.tentativas_entrega + 1
    transacao_repo.atualizar_status(transacao_id, StatusTransacao.CONVERTENDO, {
        "tentativas_entrega": tentativa,
        "metodo_entrega": metodo,
    })

    try:
        from payments.binance_client import comprar_usdt
        compra = await comprar_usdt(transacao.valor_brl)
        logger.info(f"USDT comprado: {compra['usdt_comprado']} para {transacao_id}")

        if metodo == "mlc" and settings.tropipay_client_id:
            return await _entregar_tropipay(transacao_id, transacao, destinatario, compra)
        elif metodo == "cup" and settings.noones_api_key:
            return await _entregar_noones_cup(transacao_id, transacao, destinatario, compra)
        else:
            # Fallback para manual
            logger.warning(f"Automático sem gateway para '{metodo}', usando manual")
            return await _entregar_manual(transacao_id)

    except Exception as e:
        logger.error(f"Erro na entrega automática {transacao_id} tentativa {tentativa}: {e}")
        await _tratar_falha(transacao_id, tentativa, str(e))
        return False


async def _entregar_tropipay(transacao_id, transacao, destinatario, compra) -> bool:
    from payments.tropipay_client import enviar_para_cartao_mlc
    from payments.binance_client import obter_preco_usdt_brl

    transacao_repo.atualizar_status(transacao_id, StatusTransacao.ENTREGANDO)

    preco_brl = await obter_preco_usdt_brl()
    valor_usd = round(transacao.valor_brl / preco_brl, 2)

    resultado = await enviar_para_cartao_mlc(
        numero_cartao=destinatario.numero_cartao,
        nome_titular=destinatario.nome_completo,
        valor_usd=valor_usd,
        referencia=transacao_id[:20],
        descricao=f"El Remesero #{transacao_id[:8].upper()}",
    )

    transacao_repo.atualizar_status(transacao_id, StatusTransacao.CONCLUIDO, {
        "qvapay_tx_id": resultado["tx_id"],
    })

    from services.notificacao_service import notificar_concluido
    await notificar_concluido(transacao_id)
    logger.info(f"TropiPay entregue: {transacao_id} | TX: {resultado['tx_id']}")
    return True


async def _entregar_noones_cup(transacao_id, transacao, destinatario, compra) -> bool:
    from payments.noones_client import criar_oferta_venda
    from services.notificacao_service import _bot_app

    valor_usdt = transacao.valor_usdt or compra["usdt_comprado"]
    resultado = await criar_oferta_venda(
        valor_usdt=valor_usdt,
        numero_cartao_cup=destinatario.numero_cartao,
        nome_titular=destinatario.nome_completo,
        transacao_id=transacao_id,
    )

    transacao_repo.atualizar_status(transacao_id, StatusTransacao.AGUARDANDO_COMPRADOR, {
        "noones_trade_id": resultado["oferta_id"],
    })

    if _bot_app:
        await _bot_app.bot.send_message(
            chat_id=settings.admin_telegram_id,
            text=(
                f"📢 <b>Oferta publicada no Noones</b>\n\n"
                f"🆔 <code>{transacao_id[:8].upper()}</code>\n"
                f"💰 {valor_usdt:.2f} USDT à venda\n"
                f"💳 CUP → cartão {destinatario.numero_cartao}\n"
                f"🔗 <a href='{resultado['link_oferta']}'>Ver no Noones</a>"
            ),
            parse_mode="HTML",
        )

    return True


async def _tratar_falha(transacao_id: str, tentativa: int, erro: str) -> None:
    if tentativa >= 3:
        transacao_repo.atualizar_status(transacao_id, StatusTransacao.REVISAO_MANUAL, {
            "observacoes": f"Falhou após 3 tentativas: {erro}",
        })
        from services.notificacao_service import alertar_admin_revisao_manual, notificar_falha
        await alertar_admin_revisao_manual(transacao_id, erro)
        await notificar_falha(transacao_id)
    else:
        espera = 60 * (2 ** tentativa)
        transacao_repo.atualizar_status(transacao_id, StatusTransacao.PIX_CONFIRMADO)
        await asyncio.sleep(espera)
        await entregar_transacao(transacao_id)
