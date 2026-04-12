from typing import Optional
from db.client import get_supabase
from db.models import Destinatario


def listar_por_usuario(usuario_id: str) -> list[Destinatario]:
    sb = get_supabase()
    res = sb.table("destinatarios").select("*").eq("usuario_id", usuario_id).order("apelido").execute()
    return [Destinatario(**d) for d in res.data]


def buscar_por_id(destinatario_id: str) -> Optional[Destinatario]:
    sb = get_supabase()
    res = sb.table("destinatarios").select("*").eq("id", destinatario_id).execute()
    if res and res.data:
        return Destinatario(**res.data[0])
    return None


def criar(
    usuario_id: str,
    apelido: str,
    nome_completo: str,
    metodo_entrega: str,
    numero_cartao: str,
) -> Destinatario:
    sb = get_supabase()
    res = sb.table("destinatarios").insert({
        "usuario_id": usuario_id,
        "apelido": apelido,
        "nome_completo": nome_completo,
        "metodo_entrega": metodo_entrega,
        "numero_cartao": numero_cartao,
    }).execute()
    return Destinatario(**res.data[0])


def deletar(destinatario_id: str, usuario_id: str) -> bool:
    sb = get_supabase()
    res = sb.table("destinatarios").delete().eq("id", destinatario_id).eq("usuario_id", usuario_id).execute()
    return len(res.data) > 0
