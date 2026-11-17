CREATE TABLE IF NOT EXISTS public.morning_plans (
    account_id TEXT NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    wake_date TEXT NOT NULL,
    timezone TEXT NOT NULL,
    activities TEXT NOT NULL,
    first_shown_at TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (account_id, wake_date)
);
