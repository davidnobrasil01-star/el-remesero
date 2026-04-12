from datetime import datetime
from typing import Optional
from pydantic import BaseModel, UUID4


class Usuario(BaseModel):
    id: Optional[UUID4] = None
    telegram_id: int
    username: Optional[str] = None
    nome_completo: Optional[str] = None
    telefone: Optional[str] = None
    criado_em: Optional[datetime] = None
    bloqueado: bool = False
    kyc_nivel: int = 0


class Destinatario(BaseModel):
    id: Optional[UUID4] = None
    usuario_id: UUID4
    apelido: str
    nome_completo: str
    metodo_entrega: str = "mlc"   # "mlc" = TropiPay | "cup" = Noones P2P
    numero_cartao: Optional[str] = None
    criado_em: Optional[datetime] = None


class StatusTransacao:
    PENDENTE = "pendente"
    AGUARDANDO_PIX = "aguardando_pix"
    PIX_CONFIRMADO = "pix_confirmado"
    CONVERTENDO = "convertendo"
    ENTREGANDO = "entregando"
    CONCLUIDO = "concluido"
    FALHOU = "falhou"
    REVISAO_MANUAL = "revisao_manual"


class Transacao(BaseModel):
    id: Optional[UUID4] = None
    usuario_id: UUID4
    destinatario_id: UUID4
    valor_brl: float
    taxa_cup_por_brl: float
    valor_cup_destinatario: float
    valor_usdt: Optional[float] = None
    status: str = StatusTransacao.PENDENTE
    metodo_entrega: str = "mlc"
    pix_id: Optional[str] = None
    pix_qr_code: Optional[str] = None
    pix_copia_cola: Optional[str] = None
    noones_trade_id: Optional[str] = None
    comprovante_url: Optional[str] = None
    admin_aprovado: bool = False
    tentativas_entrega: int = 0
    expira_em: Optional[datetime] = None
    criado_em: Optional[datetime] = None
    atualizado_em: Optional[datetime] = None
    observacoes: Optional[str] = None


class CotacaoCache(BaseModel):
    id: Optional[UUID4] = None
    par: str
    taxa: float
    fonte: str
    obtido_em: Optional[datetime] = None
