-- =============================================================
-- Syrus DB Schema — Migration 001
-- Run automatically via docker-entrypoint-initdb.d
-- =============================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- -------------------------------------------------------------
-- ORDERS table
-- Stores every order draft + its final state after execution
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_order_id VARCHAR(64) UNIQUE NOT NULL,   -- idempotency key
    symbol          VARCHAR(32) NOT NULL,
    side            VARCHAR(8)  NOT NULL CHECK (side IN ('BUY', 'SELL')),
    order_type      VARCHAR(16) NOT NULL CHECK (order_type IN ('MARKET', 'LIMIT', 'SL', 'SL-M')),
    quantity        INTEGER     NOT NULL CHECK (quantity > 0),
    price           NUMERIC(18, 4),                -- NULL for MARKET orders
    trigger_price   NUMERIC(18, 4),                -- for SL orders
    quoted_price    NUMERIC(18, 4),                -- price at draft time (for drift check)

    -- Approval lifecycle
    status          VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
                        CHECK (status IN ('DRAFT','APPROVED','REJECTED','SUBMITTED','FILLED','PARTIAL','CANCELLED','EXPIRED','FAILED')),
    approval_token  VARCHAR(256),                  -- HMAC token bound to this exact order
    token_expires_at TIMESTAMPTZ,
    approved_at     TIMESTAMPTZ,
    rejected_at     TIMESTAMPTZ,

    -- Risk checks
    risk_score      INTEGER CHECK (risk_score BETWEEN 0 AND 100),
    injection_flagged BOOLEAN DEFAULT FALSE,
    risk_check_passed BOOLEAN DEFAULT FALSE,

    -- Execution result
    filled_quantity INTEGER DEFAULT 0,
    average_price   NUMERIC(18, 4),
    exchange_order_id VARCHAR(64),
    submitted_at    TIMESTAMPTZ,
    filled_at       TIMESTAMPTZ,

    -- Origination
    raw_user_message TEXT,                         -- original plain-English request
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_symbol ON orders(symbol);
CREATE INDEX idx_orders_created_at ON orders(created_at DESC);


-- -------------------------------------------------------------
-- STANDING_INSTRUCTIONS table
-- Persistent rules that fire automatically when conditions are met
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS standing_instructions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(128) NOT NULL,
    raw_instruction TEXT NOT NULL,                 -- original plain-English

    -- Condition (evaluated against live price feed)
    symbol          VARCHAR(32) NOT NULL,
    condition_type  VARCHAR(20) NOT NULL CHECK (condition_type IN ('PRICE_ABOVE','PRICE_BELOW','PERCENT_CHANGE')),
    condition_value NUMERIC(18, 4) NOT NULL,

    -- Action
    action_side     VARCHAR(8)  NOT NULL CHECK (action_side IN ('BUY', 'SELL')),
    action_order_type VARCHAR(16) NOT NULL DEFAULT 'MARKET',
    action_quantity INTEGER     NOT NULL CHECK (action_quantity > 0),
    max_quantity    INTEGER,                       -- safety cap
    price_band_pct  NUMERIC(5,2) DEFAULT 2.0,     -- max allowed slippage %

    -- Lifecycle
    status          VARCHAR(16) NOT NULL DEFAULT 'ACTIVE'
                        CHECK (status IN ('ACTIVE','TRIGGERED','CANCELLED','EXPIRED','PAUSED')),
    expires_at      TIMESTAMPTZ,
    triggered_at    TIMESTAMPTZ,                   -- stamped on trigger, ensures fire-once
    triggered_order_id UUID REFERENCES orders(id),
    cancelled_at    TIMESTAMPTZ,

    -- Approval
    approved_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_si_status ON standing_instructions(status);
CREATE INDEX idx_si_symbol ON standing_instructions(symbol);


-- -------------------------------------------------------------
-- AUDIT_LOG table
-- Immutable record of every significant event in the system
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL PRIMARY KEY,
    event_type      VARCHAR(50) NOT NULL,          -- e.g. DRAFT_CREATED, ORDER_APPROVED, TOKEN_EXPIRED
    order_id        UUID REFERENCES orders(id),
    instruction_id  UUID REFERENCES standing_instructions(id),
    actor           VARCHAR(32) DEFAULT 'TRADER',  -- TRADER | SYSTEM | LLM
    payload         JSONB,                         -- full snapshot at the time of event
    ip_address      VARCHAR(64),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_order_id ON audit_log(order_id);
CREATE INDEX idx_audit_event_type ON audit_log(event_type);
CREATE INDEX idx_audit_created_at ON audit_log(created_at DESC);


-- -------------------------------------------------------------
-- RISK_LIMITS table
-- Trader-defined limits checked by the Risk Budget Engine
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS risk_limits (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    limit_name      VARCHAR(64) UNIQUE NOT NULL,
    limit_type      VARCHAR(32) NOT NULL CHECK (limit_type IN (
                        'MAX_ORDER_VALUE', 'MAX_DAILY_LOSS', 'MAX_POSITION_SIZE',
                        'MAX_ORDERS_PER_DAY', 'ALLOWED_SYMBOLS', 'BLOCKED_SYMBOLS'
                    )),
    value_numeric   NUMERIC(18,4),
    value_list      TEXT[],                        -- for ALLOWED/BLOCKED symbol lists
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Default limits (safe starting point)
INSERT INTO risk_limits (limit_name, limit_type, value_numeric) VALUES
    ('max_order_value',    'MAX_ORDER_VALUE',    500000),   -- ₹5 lakh per order
    ('max_daily_loss',     'MAX_DAILY_LOSS',     100000),   -- ₹1 lakh daily loss cap
    ('max_position_size',  'MAX_POSITION_SIZE',  1000),     -- 1000 shares any single stock
    ('max_orders_per_day', 'MAX_ORDERS_PER_DAY', 50);      -- 50 orders per day


-- -------------------------------------------------------------
-- Auto-update updated_at triggers
-- -------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER orders_updated_at
    BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER si_updated_at
    BEFORE UPDATE ON standing_instructions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
