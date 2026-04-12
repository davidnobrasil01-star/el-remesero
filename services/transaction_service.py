"""
Serviço principal de transações — orquestra todo o fluxo:
  PIX criado → PIX confirmado → BRL→USDT → QvaPay entregue
"""

import uuid
from datetime import datetime, timedelta
from loguru import logger
from config.settings import settings
from db.models import StatusTransacao
from db.repositories import transacao_repo, usuario_repo, destinatario_repo
from payments.calculadora_taxa import calcular_transacao
from payments.mercadopago_client import criar_cobranca


async def iniciar_transacao(
    telegram_id: int,
    destinatario_id: str,
    valor_brl: float,
) -> dict:
    """
    Inicia uma nova transação: calcula cotação e cria cobrança PIX.

    Returns:
        dict com pix_qr_code, pix_copia_cola, transacao_id, cotacao
    """
    usuario = usuario_repo.buscar_por_telegram_id(telegram_id)
    if not usuario:
        raise ValueError("Usuário não encontrado")

    destinatario = destinatario_repo.buscar_por_id(destinatario_id)
    if not destinatario:
        raise ValueError("Destinatário não encontrado")

    # Verificar limites
    _verificar_limites(str(usuario.id), valor_brl)

    # Calcular cotação
    cotacao = await calcular_transacao(valor_brl)

    # Criar ID único para correlacionar com o PIX
    correlation_id = f"REMESERO-{uuid.uuid4().hex[:12].upper()}"

    # Criar cobrança PIX no OpenPix
    valor_centavos = int(round(valor_brl * 100))
    pix = await criar_cobranca(
        correlation_id=correlation_id,
        valor_centavos=valor_centavos,
        comentario=f"El Remesero - Remessa para {destinatario.nome_completo}",
        expira_em_segundos=1200,
    )

    # Salvar transação no banco
    expira_em = (datetime.utcnow() + timedelta(minutes=20)).isoformat()
    transacao = transacao_repo.criar({
        "usuario_id": str(usuario.id),
        "destinatario_id": destinatario_id,
        "valor_brl": valor_brl,
        "taxa_cup_por_brl": cotacao["taxa_cup_por_brl"],
        "valor_cup_destinatario": cotacao["valor_cup_destinatario"],
        "valor_usdt": cotacao["valor_usdt_necessario"],
        "metodo_entrega": destinatario.metodo_entrega,
        "status": StatusTransacao.AGUARDANDO_PIX,
        "pix_id": correlation_id,        # correlation_id é o external_reference no MP
        "pix_qr_code": pix["qr_code_base64"],
        "pix_copia_cola": pix["copia_cola"],
        "expira_em": expira_em,
    })

    return {
        "transacao_id": str(transacao.id),
        "pix_id": correlation_id,
        "pix_qr_code": pix["qr_code_base64"],
        "pix_copia_cola": pix["copia_cola"],
        "cotacao": cotacao,
        "expira_em": expira_em,
    }


async def processar_pix_confirmado(pix_id: str) -> None:
    """
    Chamado pelo webhook OpenPix quando um PIX é confirmado.
    Inicia o fluxo de conversão e entrega.
    """
    transacao = transacao_repo.buscar_por_pix_id(pix_id)
    if not transacao:
        logger.warning(f"PIX confirmado mas transação não encontrada: {pix_id}")
        return

    if transacao.status not in (StatusTransacao.AGUARDANDO_PIX,):
        logger.info(f"Transação {transacao.id} já em status {transacao.status}, ignorando webhook")
        return

    logger.info(f"PIX confirmado para transação {transacao.id}")

    # Atualizar status
    transacao_repo.atualizar_status(str(transacao.id), StatusTransacao.PIX_CONFIRMADO)

    # Notificar cliente via Telegram
    from services.notificacao_service import notificar_pix_confirmado
    await notificar_pix_confirmado(str(transacao.id))

    # Disparar entrega (assíncrono para não bloquear o webhook)
    from services.delivery_service import entregar_transacao
    await entregar_transacao(str(transacao.id))


def _verificar_limites(usuario_id: str, valor_brl: float) -> None:
    """Verifica limites de transferência do usuário."""
    if valor_brl < settings.limite_minimo_brl:
        raise ValueError(f"Valor mínimo é R$ {settings.limite_minimo_brl:.2f}")

    if valor_brl > settings.limite_maximo_brl:
        raise ValueError(f"Valor máximo por transação é R$ {settings.limite_maximo_brl:.2f}")

    total_hoje = transacao_repo.total_enviado_hoje(usuario_id)
    if total_hoje + valor_brl > settings.limite_diario_brl:
        restante = settings.limite_diario_brl - total_hoje
        raise ValueError(f"Limite diário atingido. Disponível hoje: R$ {restante:.2f}")

    total_mes = transacao_repo.total_enviado_mes(usuario_id)
    if total_mes + valor_brl > settings.limite_mensal_brl:
        restante = settings.limite_mensal_brl - total_mes
        raise ValueError(f"Limite mensal atingido. Disponível este mês: R$ {restante:.2f}")
