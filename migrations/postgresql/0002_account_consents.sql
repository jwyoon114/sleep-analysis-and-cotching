CREATE TABLE public.account_consents (
    account_id TEXT PRIMARY KEY REFERENCES public.accounts(id) ON DELETE CASCADE,
    policy_version TEXT NOT NULL,
    privacy_accepted_at TEXT NOT NULL,
    health_accepted_at TEXT NOT NULL,
    overseas_accepted_at TEXT NOT NULL,
    adult_confirmed_at TEXT NOT NULL
);
