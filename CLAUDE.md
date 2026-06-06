# El Remesero — Guia para Claude

Bot de remessas Brasil → Cuba via Telegram. Brasileiros enviam PIX → bot compra USDT na Foxbit → cria oferta no Noones P2P → cubano paga via Transfermóvil → bot libera USDT do escrow.

## Stack

- **Python 3.12** + FastAPI (webhooks) + python-telegram-bot v21.10 (PTB)
- **Banco**: Supabase (PostgreSQL via REST)
- **Hosting**: Railway — projeto `divine-vision`, serviço `web`
- **Bot Telegram**: @Remesero0109Bot
- URL pública: `https://web-production-7c995.up.railway.app`

## Arquitetura

```
PIX (Mercado Pago)
    → webhook /webhooks/pix
    → compra USDT no Foxbit (BRL → USDT, ordem MARKET)
    → cria oferta de venda no Noones P2P
    → cubano paga via Transfermóvil (CUP)
    → admin aprova comprovante no Telegram
    → bot libera USDT do escrow (Noones release)
```

FastAPI e PTB rodam no **mesmo processo** em `main.py`. O lifespan do FastAPI inicializa o PTB. Em produção (`WEBHOOK_MODE=false`) usa long polling; quando `WEBHOOK_MODE=true` usa webhook no endpoint `/telegram`.

## Estrutura de Arquivos

```
main.py                        # Entrypoint: FastAPI + PTB lifespan
Procfile                       # web: python main.py
railway.json                   # Builder: NIXPACKS, restart ON_FAILURE
requirements.txt

config/
  settings.py                  # Pydantic-settings — todas as env vars

bot/
  application.py               # Monta PTB app com todos os handlers
  handlers/
    start.py                   # /start, /ajuda, menu principal
    enviar_flow.py             # ConversationHandler — fluxo completo de envio
    historico.py               # Histórico de transações
    destinatarios.py           # Gerenciar destinatários Cuba
    admin.py                   # /admin, aprovação manual, stats
  keyboards/
    menu_principal.py
    destinatarios.py
  states.py                    # Estados do ConversationHandler
  mensagens.py                 # Textos das mensagens

payments/
  foxbit_client.py             # Foxbit: HMAC-SHA256, BRL→USDT
  noones_client.py             # Noones: OAuth2 client_credentials, P2P Cuba
  mercadopago_client.py        # Mercado Pago: PIX
  calculadora_taxa.py          # Cálculo de taxa e cotação CUP/BRL
  binance_client.py            # Legado
  mb_client.py                 # Legado (Mercado Bitcoin)
  tropipay_client.py           # Legado (MLC)

webhooks/
  openpix_webhook.py           # /webhooks/pix — recebe PIX do Mercado Pago
  noones_webhook.py            # /webhooks/noones — eventos de trade

services/
  transaction_service.py       # Orquestra fluxo completo
  delivery_service.py          # Lógica de entrega Cuba
  noones_service.py            # Monitoramento trades Noones
  notificacao_service.py       # Notificações Telegram ao admin/user
  comprovante_service.py       # Geração de imagem de comprovante

db/
  client.py                    # Cliente Supabase
  models.py                    # Modelos de dados
  repositories/
    usuario_repo.py
    transacao_repo.py
    destinatario_repo.py

jobs/
  monitor_pagamentos.py        # Job PTB: monitora trades Noones pendentes

migrations/
  001_schema_inicial.sql
  002_atualizar_schema.sql
```

## Variáveis de Ambiente (Railway)

| Variável | Descrição |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token do @Remesero0109Bot |
| `ADMIN_TELEGRAM_ID` | ID Telegram do admin (6223341930) |
| `MERCADOPAGO_ACCESS_TOKEN` | Token Mercado Pago (PIX) |
| `MERCADOPAGO_WEBHOOK_SECRET` | Segredo HMAC para validar webhook PIX |
| `SUPABASE_URL` | https://vvhnqlwrduyyadncsxkm.supabase.co |
| `SUPABASE_SERVICE_KEY` | Chave service_role do Supabase |
| `FOXBIT_API_KEY` | API key Foxbit (exchange BRL→USDT) |
| `FOXBIT_API_SECRET` | Secret Foxbit (HMAC-SHA256) |
| `NOONES_API_KEY` | client_id OAuth2 do Noones (dev.noones.com) |
| `NOONES_CLIENT_SECRET` | client_secret OAuth2 do Noones |
| `WEBHOOK_MODE` | false = polling, true = webhook |
| `WEBHOOK_URL` | https://web-production-7c995.up.railway.app |
| `TAXA_OFERTADA_CUP_POR_BRL` | Taxa CUP/BRL ofertada (ex: 97) |
| `MARGEM_MINIMA_CUP_POR_BRL` | Margem mínima de lucro (ex: 5) |
| `LIMITE_MINIMO_BRL` | Mínimo por envio (50) |
| `LIMITE_MAXIMO_BRL` | Máximo por envio (3000) |
| `LIMITE_DIARIO_BRL` | Limite diário por usuário (3000) |
| `LIMITE_MENSAL_BRL` | Limite mensal por usuário (10000) |
| `LIMITE_REVISAO_MANUAL_BRL` | Acima disso → revisão manual (1500) |

## Autenticação das APIs

### Foxbit (`payments/foxbit_client.py`)
- HMAC-SHA256: `timestamp + METHOD + path + body`
- Headers: `X-FB-ACCESS-KEY`, `X-FB-ACCESS-SIGN`, `X-FB-ACCESS-TIMESTAMP` (ms)
- Base URL: `https://api.foxbit.com.br`
- Par: `USDTBRL`, ordem MARKET com `quote_quantity` (gasta exato em BRL)

### Noones (`payments/noones_client.py`)
- OAuth2 `client_credentials`: POST para `https://auth.noones.com/oauth2/token`
- Token Bearer cacheado com TTL (renovação automática 60s antes de expirar)
- Base URL: `https://api.noones.com/noones/v1`
- Portal dev: `dev.noones.com/dashboard` (aprovado em maio 2026, ticket #34917)
- Campos do payload confirmados: `crypto_currency_code: "USDT"`, `currency: "USD"`, `offer_type_field: "sell"`, `payment_method: "bank-transfer"`, `payment_method_label: "Transfermovil CUP"`
- Vendor terms: aceitos via UI uma vez por conta (obrigatório antes de criar ofertas via API)

### Mercado Pago (`webhooks/openpix_webhook.py`)
- Webhook em `/webhooks/pix`
- Verificação HMAC-SHA256: `manifest = "id:{data_id};request-id:{x_request_id};ts:{ts};"`
- Processa eventos `payment.created` / `payment.updated` com status `approved`

## Fluxo de Pagamento Detalhado

1. **Usuário** envia `/start` → se registra → escolhe destinatário Cuba
2. **Bot** busca taxa CUP/BRL em eltoque.com → exibe cotação (válida 20 min)
3. **Usuário** inicia PIX no app bancário → paga o valor em BRL
4. **Mercado Pago** envia webhook → `/webhooks/pix` valida assinatura
5. **Bot** compra USDT na Foxbit (`comprar_usdt(valor_brl)`) — ordem MARKET
6. **Bot** cria oferta de venda no Noones (`criar_oferta_venda`) com instruções Transfermóvil
7. **Cubano** paga via Transfermóvil → envia comprovante no chat Noones
8. **Admin** recebe notificação no Telegram → aprova ou rejeita
9. **Bot** libera USDT do escrow (`liberar_usdt(trade_id)`) → cubano recebe

## Comandos Admin

- `/admin` — painel admin
- `/admin_stats` — estatísticas
- `/admin_revisao` — transações aguardando revisão manual
- `/admin_entregar` — entrega manual de USDT
- `/admin_bloquear` — bloquear usuário

## Observações Importantes

- **Supabase free tier pausa após 7 dias sem atividade** — enquanto o bot estiver rodando no Railway isso não acontece. Se o bot ficar offline >7 dias, reativar em supabase.com/dashboard
- **WEBHOOK_MODE=false** — bot usa long polling. Para mudar para webhook, setar `WEBHOOK_MODE=true` e registrar URL no BotFather
- **Float de USDT**: operador mantém saldo de USDT no Noones. Foxbit compra USDT com BRL do Mercado Pago; o USDT é transferido periodicamente para o Noones via TRC20
- **Taxa CUP/BRL**: buscada do eltoque.com, travada no momento da cotação por 20 minutos
- **USDT é stablecoin** (≈$1 USD): só o par BRL/USD varia, absorvido pela margem de 5-10%
- O projeto "divine-vision" no Railway É El Remesero (nome gerado automaticamente pelo Railway)
