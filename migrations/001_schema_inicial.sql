-- =============================================================
-- El Remesero — Schema Inicial
-- Execute no SQL Editor do Supabase
-- =============================================================

-- Extensão para UUIDs
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------
-- USUÁRIOS
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usuarios (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id     BIGINT UNIQUE NOT NULL,
    username        TEXT,
    nome_completo   TEXT,
    telefone        TEXT,
    kyc_nivel       SMALLINT DEFAULT 0,
    bloqueado       BOOLEAN DEFAULT FALSE,
    criado_em       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_usuarios_telegram_id ON usuarios(telegram_id);

-- ---------------------------------------------------------------
-- DESTINATÁRIOS
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS destinatarios (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id      UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    apelido         TEXT NOT NULL,
    qvapay_handle   TEXT NOT NULL,
    nome_completo   TEXT NOT NULL,
    criado_em       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_destinatarios_usuario_id ON destinatarios(usuario_id);

-- ---------------------------------------------------------------
-- TRANSAÇÕES
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transacoes (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id              UUID NOT NULL REFERENCES usuarios(id),
    destinatario_id         UUID NOT NULL REFERENCES destinatarios(id),

    -- Valores financeiros
    valor_brl               NUMERIC(12, 2) NOT NULL,
    taxa_cup_por_brl        NUMERIC(10, 4) NOT NULL,
    valor_cup_destinatario  NUMERIC(14, 2) NOT NULL,
    valor_usdt              NUMERIC(18, 8),

    -- Status do ciclo de vida
    status                  TEXT NOT NULL DEFAULT 'pendente',

    -- PIX (OpenPix)
    pix_id                  TEXT,
    pix_qr_code             TEXT,
    pix_copia_cola          TEXT,

    -- Entrega Cuba (QvaPay)
    qvapay_tx_id            TEXT,
    tentativas_entrega      SMALLINT DEFAULT 0,

    -- Controle
    expira_em               TIMESTAMPTZ,
    criado_em               TIMESTAMPTZ DEFAULT NOW(),
    atualizado_em           TIMESTAMPTZ DEFAULT NOW(),
    observacoes             TEXT
);

CREATE INDEX IF NOT EXISTS idx_transacoes_usuario_id ON transacoes(usuario_id);
CREATE INDEX IF NOT EXISTS idx_transacoes_pix_id ON transacoes(pix_id);
CREATE INDEX IF NOT EXISTS idx_transacoes_status ON transacoes(status);

-- Trigger para atualizar atualizado_em automaticamente
CREATE OR REPLACE FUNCTION atualizar_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_transacoes_atualizado_em
    BEFORE UPDATE ON transacoes
    FOR EACH ROW EXECUTE FUNCTION atualizar_timestamp();

-- ---------------------------------------------------------------
-- CACHE DE COTAÇÕES
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cotacoes_cache (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    par         TEXT NOT NULL,              -- ex: 'BRL_CUP', 'BRL_USD', 'USD_CUP'
    taxa        NUMERIC(18, 8) NOT NULL,
    fonte       TEXT NOT NULL,              -- 'eltoque', 'bcb', 'binance'
    obtido_em   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cotacoes_par ON cotacoes_cache(par);

-- ---------------------------------------------------------------
-- LOG DE AUDITORIA (ADMIN)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS log_admin (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evento      TEXT NOT NULL,
    payload     JSONB,
    criado_em   TIMESTAMPTZ DEFAULT NOW()
);
