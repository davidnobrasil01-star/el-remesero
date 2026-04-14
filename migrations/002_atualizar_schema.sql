-- =============================================================
-- El Remesero — Migração 002: Atualizar schema para versão atual
-- Execute no SQL Editor do Supabase APÓS a migração 001
-- =============================================================

-- ---------------------------------------------------------------
-- DESTINATÁRIOS: adicionar colunas que faltam
-- ---------------------------------------------------------------

-- Tornar qvapay_handle opcional (era NOT NULL mas não é mais usado)
ALTER TABLE destinatarios
    ALTER COLUMN qvapay_handle DROP NOT NULL;

-- Adicionar método de entrega (mlc = TropiPay | cup = Noones P2P)
ALTER TABLE destinatarios
    ADD COLUMN IF NOT EXISTS metodo_entrega TEXT NOT NULL DEFAULT 'mlc';

-- Adicionar número do cartão cubano do destinatário
ALTER TABLE destinatarios
    ADD COLUMN IF NOT EXISTS numero_cartao TEXT;

-- ---------------------------------------------------------------
-- TRANSAÇÕES: adicionar colunas que faltam
-- ---------------------------------------------------------------

-- Método de entrega por transação
ALTER TABLE transacoes
    ADD COLUMN IF NOT EXISTS metodo_entrega TEXT DEFAULT 'mlc';

-- ID do trade no Noones (entrega CUP via P2P)
ALTER TABLE transacoes
    ADD COLUMN IF NOT EXISTS noones_trade_id TEXT;

-- URL do comprovante salvo (futuro)
ALTER TABLE transacoes
    ADD COLUMN IF NOT EXISTS comprovante_url TEXT;

-- Flag de aprovação pelo admin
ALTER TABLE transacoes
    ADD COLUMN IF NOT EXISTS admin_aprovado BOOLEAN DEFAULT FALSE;

-- Renomear qvapay_tx_id para algo mais genérico (se existir)
-- Mantemos qvapay_tx_id por compatibilidade e adicionamos alias
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'transacoes' AND column_name = 'qvapay_tx_id'
    ) THEN
        ALTER TABLE transacoes ADD COLUMN qvapay_tx_id TEXT;
    END IF;
END $$;

-- ---------------------------------------------------------------
-- Verificação final
-- ---------------------------------------------------------------
-- Confirmar colunas adicionadas:
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name IN ('destinatarios', 'transacoes')
-- ORDER BY table_name, ordinal_position;
