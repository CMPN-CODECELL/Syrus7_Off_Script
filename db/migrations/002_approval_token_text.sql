-- HMAC approval tokens include the signed order payload and can exceed 256 chars.
ALTER TABLE orders
    ALTER COLUMN approval_token TYPE TEXT;
