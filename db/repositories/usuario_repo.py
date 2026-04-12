from typing import Optional
from db.client import get_supabase
from db.models import Usuario


def buscar_por_telegram_id(telegram_id: int) -> Optional[Usuario]:
    sb = get_supabase()
    res = sb.table("usuarios").select("*").eq("telegram_id", telegram_id).execute()
    if res and res.data:
        return Usuario(**res.data[0])
    return None


def criar_ou_atualizar(telegram_id: int, username: Optional[str], nome_completo: Optional[str]) -> Usuario:
    sb = get_supabase()
    existente = buscar_por_telegram_id(telegram_id)
    if existente:
        sb.table("usuarios").update({
            "username": username,
            "nome_completo": nome_completo,
        }).eq("telegram_id", telegram_id).execute()
        return buscar_por_telegram_id(telegram_id)
    res = sb.table("usuarios").insert({
        "telegram_id": telegram_id,
        "username": username,
        "nome_completo": nome_completo,
    }).execute()
    return Usuario(**res.data[0])


def esta_bloqueado(telegram_id: int) -> bool:
    usuario = buscar_por_telegram_id(telegram_id)
    return usuario.bloqueado if usuario else False
