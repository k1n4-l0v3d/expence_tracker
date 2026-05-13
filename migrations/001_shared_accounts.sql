-- Migration: Add shared accounts feature
-- Run against PostgreSQL production database

CREATE TABLE IF NOT EXISTS shared_accounts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    created_by_user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS shared_account_members (
    id SERIAL PRIMARY KEY,
    shared_account_id INTEGER NOT NULL REFERENCES shared_accounts(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    joined_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(shared_account_id, user_id)
);

ALTER TABLE expenses ADD COLUMN IF NOT EXISTS shared_account_id INTEGER REFERENCES shared_accounts(id);
ALTER TABLE expenses ADD COLUMN IF NOT EXISTS added_by_user_id INTEGER REFERENCES users(id);
ALTER TABLE incomes ADD COLUMN IF NOT EXISTS shared_account_id INTEGER REFERENCES shared_accounts(id);
ALTER TABLE incomes ADD COLUMN IF NOT EXISTS added_by_user_id INTEGER REFERENCES users(id);
ALTER TABLE monthly_budgets ADD COLUMN IF NOT EXISTS shared_account_id INTEGER REFERENCES shared_accounts(id);
ALTER TABLE savings_accounts ADD COLUMN IF NOT EXISTS shared_account_id INTEGER REFERENCES shared_accounts(id);

CREATE TABLE IF NOT EXISTS shared_account_invitations (
    id SERIAL PRIMARY KEY,
    shared_account_id INTEGER NOT NULL REFERENCES shared_accounts(id) ON DELETE CASCADE,
    invited_user_id INTEGER NOT NULL REFERENCES users(id),
    invited_by_user_id INTEGER NOT NULL REFERENCES users(id),
    status VARCHAR(10) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS shared_account_messages (
    id SERIAL PRIMARY KEY,
    shared_account_id INTEGER NOT NULL REFERENCES shared_accounts(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    text VARCHAR(1000) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS shared_account_reactions (
    id SERIAL PRIMARY KEY,
    message_id INTEGER NOT NULL REFERENCES shared_account_messages(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    emoji VARCHAR(5) NOT NULL,
    UNIQUE(message_id, user_id, emoji)
);
