-- Persist a multi-order approval as one plan. Safe on existing databases.
CREATE TABLE IF NOT EXISTS order_plans (
    id UUID PRIMARY KEY,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    raw_user_message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS plan_id UUID REFERENCES order_plans(id);

CREATE INDEX IF NOT EXISTS idx_orders_plan_id ON orders(plan_id);
