-- Persist bounded risk-budget change proposals before explicit approval.
CREATE TABLE IF NOT EXISTS risk_limit_drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    limit_type VARCHAR(32) NOT NULL CHECK (limit_type IN (
        'MAX_ORDER_VALUE', 'MAX_POSITION_SIZE', 'MAX_ORDERS_PER_DAY'
    )),
    old_value NUMERIC(18, 4) NOT NULL CHECK (old_value > 0),
    new_value NUMERIC(18, 4) NOT NULL CHECK (new_value > 0),
    status VARCHAR(16) NOT NULL DEFAULT 'DRAFT' CHECK (
        status IN ('DRAFT', 'APPROVED', 'REJECTED', 'EXPIRED', 'STALE')
    ),
    expires_at TIMESTAMPTZ NOT NULL,
    approved_at TIMESTAMPTZ,
    rejected_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_limit_drafts_status ON risk_limit_drafts(status, expires_at);
