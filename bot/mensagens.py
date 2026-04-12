"""
Todas as strings de texto do bot em Português do Brasil.
Centralizado aqui para facilitar edição e futuras traduções.
"""

# ── Boas-vindas ──────────────────────────────────────────────────────────────

MSG_START = (
    "👋 Olá, <b>{nome}</b>! Bem-vindo ao <b>El Remesero</b> 🇧🇷→🇨🇺\n\n"
    "Envie dinheiro para seus familiares em Cuba de forma <b>rápida e segura</b>, "
    "diretamente pelo Telegram.\n\n"
    "Pague com <b>PIX</b> e seu familiar recebe em <b>Pesos Cubanos (CUP)</b>.\n\n"
    "O que deseja fazer?"
)

MSG_AJUDA = (
    "ℹ️ <b>Como funciona o El Remesero?</b>\n\n"
    "1️⃣ Escolha o destinatário em Cuba\n"
    "2️⃣ Informe o valor em Reais (R$)\n"
    "3️⃣ Veja quanto seu familiar vai receber em CUP\n"
    "4️⃣ Pague via PIX\n"
    "5️⃣ Pronto! O dinheiro chega em minutos 🚀\n\n"
    "📌 Limites:\n"
    "• Mínimo: R$ 50,00\n"
    "• Máximo por transação: R$ 3.000,00\n\n"
    "💬 Suporte: @suporte_elremesero"
)

# ── Fluxo de Envio ───────────────────────────────────────────────────────────

MSG_SELECIONAR_DESTINATARIO = (
    "📋 <b>Para quem deseja enviar?</b>\n\n"
    "Escolha um destinatário salvo ou adicione um novo:"
)

MSG_SEM_DESTINATARIOS = (
    "Você ainda não tem destinatários salvos.\n\n"
    "Clique em <b>+ Novo Destinatário</b> para adicionar o primeiro."
)

MSG_NOVO_DEST_METODO = (
    "📲 <b>Novo destinatário</b>\n\n"
    "Como seu familiar vai receber o dinheiro?\n\n"
    "💳 <b>Cartão MLC</b> — entrega automática no cartão MLC (Transfermovil)\n"
    "🪙 <b>Pesos CUP</b> — entrega em CUP via cartão cubano\n\n"
    "Escolha uma opção:"
)

MSG_NOVO_DEST_NUMERO_CARTAO = (
    "💳 <b>Número do cartão</b>\n\n"
    "Digite o número do cartão cubano do seu familiar:\n"
    "<i>Ex: 9234 5678 9012 3456</i>"
)

MSG_CARTAO_INVALIDO = (
    "❌ Número de cartão inválido.\n\n"
    "Digite apenas os números do cartão (16 dígitos):\n"
    "<i>Ex: 9234567890123456 ou 9234 5678 9012 3456</i>"
)

MSG_NOVO_DEST_NOME_TITULAR = (
    "👤 <b>Nome do titular</b>\n\n"
    "Digite o nome completo do titular do cartão:\n"
    "<i>Ex: Juan García Pérez</i>"
)

MSG_NOVO_DESTINATARIO_NOME = (
    "✅ Cartão registrado!\n\n"
    "Como você quer chamar este destinatário?\n"
    "<i>Ex: Mamãe, Juan, Tia Rosa...</i>"
)

MSG_CONFIRMAR_SALVAR = (
    "💾 Deseja salvar <b>{apelido}</b> como destinatário para usar novamente?"
)

MSG_DESTINATARIO_SALVO = "✅ <b>{apelido}</b> salvo nos seus destinatários!"

MSG_INFORMAR_VALOR = (
    "💸 <b>Quanto deseja enviar para {nome}?</b>\n\n"
    "Digite o valor em Reais (somente números).\n"
    "<i>Ex: 200 ou 150.50</i>\n\n"
    "Mínimo: <b>R$ 50,00</b> | Máximo: <b>R$ 3.000,00</b>"
)

MSG_VALOR_INVALIDO = (
    "❌ Valor inválido. Por favor, informe apenas números.\n"
    "<i>Ex: 200 ou 150.50</i>"
)

MSG_COTACAO = (
    "💸 <b>Resumo da transferência</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━\n"
    "Você envia:          <b>R$ {valor_brl}</b> via PIX\n"
    "Seu familiar recebe: <b>{valor_cup} CUP</b>\n"
    "Taxa de hoje:        <b>{taxa} CUP por R$1,00</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━\n"
    "📍 Destinatário: <b>{nome_dest}</b>\n\n"
    "Confirma o envio?"
)

MSG_AGUARDANDO_PIX = (
    "⏳ <b>Aguardando seu PIX</b>\n\n"
    "Copie o código abaixo e pague no seu banco:\n\n"
    "<code>{copia_cola}</code>\n\n"
    "⏰ <b>Expira em 20 minutos</b>\n"
    "🆔 Pedido: <code>{transacao_id}</code>\n\n"
    "Após o pagamento, a confirmação é automática!"
)

MSG_PIX_EXPIRADO = (
    "⏰ <b>Tempo esgotado.</b>\n\n"
    "Seu QR Code PIX expirou. Para enviar novamente, inicie uma nova transferência."
)

# ── Status da Transação ──────────────────────────────────────────────────────

MSG_PIX_CONFIRMADO = (
    "✅ <b>PIX recebido!</b>\n\n"
    "Estamos enviando o dinheiro para <b>{nome}</b> em Cuba...\n"
    "Você receberá o comprovante em instantes. 🚀"
)

MSG_ENTREGANDO = "📤 Transferência em andamento..."

MSG_CONCLUIDO = (
    "🎉 <b>Transferência concluída com sucesso!</b>\n\n"
    "<b>{nome}</b> recebeu <b>{cup} CUP</b> em Cuba.\n\n"
    "Obrigado por usar o <b>El Remesero</b>! 🇧🇷→🇨🇺"
)

MSG_AGUARDANDO_COMPROVANTE = (
    "⏳ <b>Aguardando confirmação</b>\n\n"
    "O pagamento para <b>{nome}</b> está sendo processado.\n"
    "Você receberá uma notificação quando concluir. 🚀"
)

MSG_FALHA = (
    "⚠️ <b>Houve um problema na sua transferência.</b>\n\n"
    "Nossa equipe já foi notificada e está resolvendo.\n"
    "Entraremos em contato em breve.\n\n"
    "Não se preocupe — se o PIX foi pago, seu dinheiro está seguro."
)

# ── Admin — Noones ───────────────────────────────────────────────────────────

MSG_ADMIN_COMPROVANTE = (
    "🔔 <b>Novo comprovante Noones</b>\n\n"
    "Transação: <code>{transacao_id}</code>\n"
    "Cliente: <b>{cliente}</b>\n"
    "Destinatário: <b>{destinatario}</b>\n"
    "Valor: <b>{valor_cup} CUP</b> (R$ {valor_brl})\n"
    "Trade Noones: <code>{trade_id}</code>\n\n"
    "Verifique o comprovante e aprove ou rejeite:"
)

# ── Histórico ────────────────────────────────────────────────────────────────

MSG_HISTORICO_VAZIO = "📋 Você ainda não realizou nenhuma transferência."

MSG_HISTORICO_ITEM = (
    "📌 <b>{data}</b>\n"
    "   Para: {destinatario} | R$ {valor_brl} → {valor_cup} CUP\n"
    "   Status: {status_emoji} {status}"
)

STATUS_EMOJI = {
    "pendente": "⏳",
    "aguardando_pix": "⏳",
    "pix_confirmado": "🔄",
    "convertendo": "🔄",
    "entregando": "📤",
    "concluido": "✅",
    "falhou": "❌",
    "revisao_manual": "⚠️",
}

STATUS_LABEL = {
    "pendente": "Pendente",
    "aguardando_pix": "Aguardando PIX",
    "pix_confirmado": "PIX recebido",
    "convertendo": "Processando",
    "entregando": "Enviando",
    "concluido": "Concluído",
    "falhou": "Falhou",
    "revisao_manual": "Em revisão",
}

# ── Destinatários ────────────────────────────────────────────────────────────

MSG_LISTA_DESTINATARIOS = "📋 <b>Seus destinatários:</b>"

MSG_CONFIRMAR_DELETAR = (
    "🗑️ Tem certeza que deseja remover <b>{apelido}</b> dos seus destinatários?"
)

MSG_DESTINATARIO_DELETADO = "✅ <b>{apelido}</b> removido com sucesso."

# ── Erros gerais ─────────────────────────────────────────────────────────────

MSG_ERRO_GENERICO = (
    "😕 Ocorreu um erro inesperado. Por favor, tente novamente.\n"
    "Se o problema persistir, entre em contato: @suporte_elremesero"
)

MSG_USUARIO_BLOQUEADO = (
    "🚫 Sua conta está temporariamente bloqueada.\n"
    "Entre em contato: @suporte_elremesero"
)

MSG_CANCELADO = "❌ Operação cancelada. Use o menu para recomeçar."
