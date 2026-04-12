# Estados do ConversationHandler do fluxo de envio
(
    SELECIONAR_DESTINATARIO,
    NOVO_DEST_METODO,           # escolher MLC (TropiPay) ou CUP (Noones)
    NOVO_DEST_NUMERO_CARTAO,    # digitar número do cartão cubano
    NOVO_DEST_NOME_TITULAR,     # digitar nome completo do titular
    NOVO_DESTINATARIO_NOME,     # digitar apelido para salvar
    CONFIRMAR_SALVAR_DESTINATARIO,
    INFORMAR_VALOR,
    MOSTRAR_COTACAO,
    AGUARDANDO_PIX,
) = range(9)

# Estados do gerenciamento de destinatários
(
    GERENCIAR_DESTINATARIOS,
    CONFIRMAR_DELETAR,
) = range(10, 12)
