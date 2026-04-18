from typing import Optional
from datetime import datetime
from db.client import get_supabase
from db.models import Transacao, StatusTransacao


def criar(transacao: dict) -> Transacao:
    sb = get_supabase()
    res = sb.table("transacoes").insert(transacao).execute()
    return Transacao(**res.data[0])


def buscar_por_id(transacao_id: str) -> Optional[Transacao]:
    sb = get_supabase()
    res = sb.table("transacoes").select("*").eq("id", transacao_id).execute()
    if res and res.data:
        return Transacao(**res.data[0])
    return None


def buscar_por_pix_id(pix_id: str) -> Optional[Transacao]:
    sb = get_supabase()
    res = sb.table("transacoes").select("*").eq("pix_id", pix_id).execute()
    if res and res.data:
        return Transacao(**res.data[0])
    return None


def atualizar_status(transacao_id: str, status: str, dados_extras: dict = None) -> Transacao:
    sb = get_supabase()
    payload = {"status": status, "atualizado_em": datetime.utcnow().isoformat()}
    if dados_extras:
        payload.update(dados_extras)
    res = sb.table("transacoes").update(payload).eq("id", transacao_id).execute()
    return Transacao(**res.data[0])


def listar_por_usuario(usuario_id: str, limite: int = 10) -> list[Transacao]:
    sb = get_supabase()
    res = (
        sb.table("transacoes")
        .select("*")
        .eq("usuario_id", usuario_id)
        .order("criado_em", desc=True)
        .limit(limite)
        .execute()
    )
    return [Transacao(**t) for t in res.data]


def buscar_pendentes_expiradas() -> list[Transacao]:
    sb = get_supabase()
    agora = datetime.utcnow().isoformat()
    res = (
        sb.table("transacoes")
        .select("*")
        .eq("status", StatusTransacao.AGUARDANDO_PIX)
        .lt("expira_em", agora)
        .execute()
    )
    return [Transacao(**t) for t in res.data]


def buscar_travadas_para_reprocessar() -> list[Transacao]:
    """
    Busca transações travadas há mais de 10 minutos.
    Exclui transações Noones em AGUARDANDO_COMPRADOR ou ENTREGANDO com trade_id
    (estão aguardando comprador P2P legitimamente — não devem ser reprocessadas).
    """
    sb = get_supabase()
    limite = (datetime.utcnow() - __import__('datetime').timedelta(minutes=10)).isoformat()
    res = (
        sb.table("transacoes")
        .select("*")
        .in_("status", [StatusTransacao.PIX_CONFIRMADO, StatusTransacao.CONVERTENDO])
        .lt("tentativas_entrega", 3)
        .lt("atualizado_em", limite)
        .is_("noones_trade_id", "null")   # exclui trades Noones ativos
        .execute()
    )
    return [Transacao(**t) for t in res.data]


def total_enviado_hoje(usuario_id: str) -> float:
    sb = get_supabase()
    hoje = datetime.utcnow().date().isoformat()
    res = (
        sb.table("transacoes")
        .select("valor_brl")
        .eq("usuario_id", usuario_id)
        .eq("status", StatusTransacao.CONCLUIDO)
        .gte("criado_em", f"{hoje}T00:00:00")
        .execute()
    )
    return sum(t["valor_brl"] for t in res.data)


def total_enviado_mes(usuario_id: str) -> float:
    sb = get_supabase()
    from datetime import date
    hoje = date.today()
    primeiro_dia = f"{hoje.year}-{hoje.month:02d}-01T00:00:00"
    res = (
        sb.table("transacoes")
        .select("valor_brl")
        .eq("usuario_id", usuario_id)
        .eq("status", StatusTransacao.CONCLUIDO)
        .gte("criado_em", primeiro_dia)
        .execute()
    )
    return sum(t["valor_brl"] for t in res.data)
