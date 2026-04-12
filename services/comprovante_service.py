"""
Serviço de comprovantes — gera imagem PNG profissional do comprovante
de transferência e envia ao cliente via Telegram.
"""

import io
import qrcode
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from loguru import logger
from db.repositories import transacao_repo, destinatario_repo
from db.client import get_supabase

# Cores do comprovante
COR_FUNDO = (255, 255, 255)
COR_HEADER = (0, 100, 60)       # Verde escuro
COR_TEXTO = (30, 30, 30)
COR_DESTAQUE = (0, 140, 80)
COR_LINHA = (200, 200, 200)
COR_FOOTER = (100, 100, 100)


def _gerar_qr_code(texto: str, tamanho: int = 120) -> Image.Image:
    """Gera QR Code do ID da transação."""
    qr = qrcode.QRCode(version=1, box_size=3, border=2)
    qr.add_data(texto)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    return img.resize((tamanho, tamanho))


def gerar_comprovante_imagem(
    transacao_id: str,
    nome_remetente: str,
    valor_brl: float,
    nome_destinatario: str,
    valor_cup: float,
    taxa_cup_brl: float,
    criado_em: datetime,
) -> bytes:
    """
    Gera a imagem PNG do comprovante.
    Retorna os bytes da imagem.
    """
    largura, altura = 480, 620
    img = Image.new("RGB", (largura, altura), COR_FUNDO)
    draw = ImageDraw.Draw(img)

    # Tentar carregar fontes do sistema; fallback para padrão
    try:
        fonte_titulo = ImageFont.truetype("arial.ttf", 18)
        fonte_normal = ImageFont.truetype("arial.ttf", 14)
        fonte_pequena = ImageFont.truetype("arial.ttf", 11)
        fonte_grande = ImageFont.truetype("arialbd.ttf", 22)
    except Exception:
        fonte_titulo = ImageFont.load_default()
        fonte_normal = fonte_titulo
        fonte_pequena = fonte_titulo
        fonte_grande = fonte_titulo

    # Header verde
    draw.rectangle([(0, 0), (largura, 80)], fill=COR_HEADER)
    draw.text((largura // 2, 20), "EL REMESERO", font=fonte_grande, fill="white", anchor="mm")
    draw.text((largura // 2, 52), "Comprovante de Transferência", font=fonte_normal, fill=(200, 255, 200), anchor="mm")

    # Linha divisória
    y = 90
    draw.line([(20, y), (largura - 20, y)], fill=COR_LINHA, width=1)

    # Data e ID
    data_fmt = criado_em.strftime("%d/%m/%Y às %H:%M")
    id_fmt = f"#REMESERO-{transacao_id[:12].upper()}"
    y = 100
    draw.text((largura // 2, y), data_fmt, font=fonte_pequena, fill=COR_FOOTER, anchor="mm")
    y += 18
    draw.text((largura // 2, y), id_fmt, font=fonte_normal, fill=COR_DESTAQUE, anchor="mm")

    # Divisória
    y += 20
    draw.line([(20, y), (largura - 20, y)], fill=COR_LINHA, width=1)

    # Seção Remetente
    y += 15
    draw.text((30, y), "REMETENTE", font=fonte_normal, fill=COR_DESTAQUE)
    y += 20
    draw.text((30, y), f"👤  {nome_remetente}", font=fonte_normal, fill=COR_TEXTO)
    y += 20
    draw.text((30, y), f"💳  PIX pago:  R$ {valor_brl:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), font=fonte_normal, fill=COR_TEXTO)

    # Divisória
    y += 22
    draw.line([(20, y), (largura - 20, y)], fill=COR_LINHA, width=1)

    # Seção Destinatário
    y += 15
    draw.text((30, y), "DESTINATÁRIO", font=fonte_normal, fill=COR_DESTAQUE)
    y += 20
    draw.text((30, y), f"👤  {nome_destinatario}", font=fonte_normal, fill=COR_TEXTO)
    y += 20
    cup_fmt = f"{valor_cup:,.0f}".replace(",", ".")
    draw.text((30, y), f"💰  Recebido:  {cup_fmt} CUP", font=fonte_normal, fill=COR_TEXTO)
    y += 20
    taxa_fmt = f"{taxa_cup_brl:.0f}"
    draw.text((30, y), f"📊  Taxa:  {taxa_fmt} CUP por R$1,00", font=fonte_pequena, fill=COR_FOOTER)

    # Divisória
    y += 22
    draw.line([(20, y), (largura - 20, y)], fill=COR_LINHA, width=1)

    # Status CONCLUÍDO
    y += 15
    draw.rectangle([(largura // 2 - 100, y), (largura // 2 + 100, y + 32)], fill=COR_HEADER)
    draw.text((largura // 2, y + 16), "✅  TRANSFERÊNCIA CONCLUÍDA", font=fonte_normal, fill="white", anchor="mm")

    # QR Code do ID
    y += 50
    qr_img = _gerar_qr_code(id_fmt)
    qr_x = largura // 2 - 60
    img.paste(qr_img, (qr_x, y))
    y += 130
    draw.text((largura // 2, y), "Escaneie para verificar", font=fonte_pequena, fill=COR_FOOTER, anchor="mm")

    # Footer
    y = altura - 30
    draw.text((largura // 2, y), "elremesero.com • Suporte via Telegram", font=fonte_pequena, fill=COR_FOOTER, anchor="mm")

    # Salvar em bytes
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()


async def gerar_e_enviar_comprovante(transacao_id: str, telegram_id: int) -> None:
    """Gera a imagem do comprovante e envia via Telegram como foto."""
    from services.notificacao_service import _bot_app

    transacao = transacao_repo.buscar_por_id(transacao_id)
    if not transacao:
        return

    destinatario = destinatario_repo.buscar_por_id(str(transacao.destinatario_id))

    # Buscar dados do usuário
    sb = get_supabase()
    res = sb.table("usuarios").select("nome_completo, username").eq("id", str(transacao.usuario_id)).execute()
    nome_remetente = "Remetente"
    if res and res.data:
        nome_remetente = res.data.get("nome_completo") or res.data.get("username") or "Remetente"

    nome_destinatario = destinatario.nome_completo if destinatario else "Destinatário"
    criado_em = transacao.criado_em or datetime.utcnow()

    try:
        imagem_bytes = gerar_comprovante_imagem(
            transacao_id=transacao_id,
            nome_remetente=nome_remetente,
            valor_brl=transacao.valor_brl,
            nome_destinatario=nome_destinatario,
            valor_cup=transacao.valor_cup_destinatario,
            taxa_cup_brl=transacao.taxa_cup_por_brl,
            criado_em=criado_em,
        )

        if _bot_app:
            buf = io.BytesIO(imagem_bytes)
            buf.name = "comprovante.png"
            await _bot_app.bot.send_photo(
                chat_id=telegram_id,
                photo=buf,
                caption=f"📄 Comprovante de transferência #{transacao_id[:8].upper()}",
            )
    except Exception as e:
        logger.error(f"Erro ao gerar/enviar comprovante para {transacao_id}: {e}")
