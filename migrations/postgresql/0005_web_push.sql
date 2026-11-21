CREATE TABLE IF NOT EXISTS public.web_push_subscriptions (
    endpoint_id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL REFERENCES public.auth_tokens(token_hash) ON DELETE CASCADE,
    endpoint TEXT NOT NULL,
    p256dh TEXT NOT NULL,
    auth_secret TEXT NOT NULL,
    expires_at TIMESTAMPTZ,
    registered_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS web_push_subscriptions_token ON public.web_push_subscriptions(token_hash);

CREATE TABLE IF NOT EXISTS public.web_push_test_limits (
    account_id TEXT PRIMARY KEY REFERENCES public.accounts(id) ON DELETE CASCADE,
    attempted_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS web_push_test_limits_attempted ON public.web_push_test_limits(attempted_at);
