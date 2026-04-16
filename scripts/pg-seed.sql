-- Demo content for the foreign-catalog walkthrough.
--
-- Loaded by ``postgres-e2e`` on first start via
-- ``/docker-entrypoint-initdb.d/seed.sql``. Postgres' initdb hook only
-- fires on an empty volume, so every statement here is written defensively
-- with ``IF NOT EXISTS`` / ``ON CONFLICT DO NOTHING`` in case the volume
-- is reused across container restarts.

CREATE SCHEMA IF NOT EXISTS shop;

CREATE TABLE IF NOT EXISTS shop.customers (
    id         integer PRIMARY KEY,
    name       text NOT NULL,
    email      text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS shop.products (
    id    integer PRIMARY KEY,
    sku   text NOT NULL,
    name  text NOT NULL,
    price numeric(10, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS shop.orders (
    id          integer PRIMARY KEY,
    customer_id integer NOT NULL REFERENCES shop.customers(id),
    total       numeric(12, 2) NOT NULL,
    placed_at   timestamptz NOT NULL DEFAULT now()
);

INSERT INTO shop.customers (id, name, email) VALUES
    (1, 'Ada Lovelace',     'ada@example.com'),
    (2, 'Grace Hopper',     'grace@example.com'),
    (3, 'Katherine Johnson','katherine@example.com')
ON CONFLICT (id) DO NOTHING;

INSERT INTO shop.products (id, sku, name, price) VALUES
    (1, 'SKU-001', 'Analytical Engine Manual', 49.99),
    (2, 'SKU-002', 'COBOL Reference Card',     12.50),
    (3, 'SKU-003', 'Flight Trajectory Charts', 199.00)
ON CONFLICT (id) DO NOTHING;

INSERT INTO shop.orders (id, customer_id, total) VALUES
    (1001, 1, 49.99),
    (1002, 2, 25.00),
    (1003, 3, 199.00),
    (1004, 1, 61.49)
ON CONFLICT (id) DO NOTHING;
