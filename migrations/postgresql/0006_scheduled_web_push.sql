ALTER TABLE public.web_push_subscriptions
    ADD COLUMN account_id TEXT COLLATE "C" REFERENCES public.accounts(id) ON DELETE CASCADE,
    ADD COLUMN device_hash TEXT,
    ADD COLUMN reminders_enabled BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE public.web_push_subscriptions AS s
    SET account_id = t.account_id
FROM public.auth_tokens AS t
WHERE t.token_hash = s.token_hash;

ALTER TABLE public.web_push_subscriptions
    ALTER COLUMN account_id SET NOT NULL,
    ALTER COLUMN token_hash DROP NOT NULL;

CREATE UNIQUE INDEX web_push_one_subscription_per_installation
    ON public.web_push_subscriptions (device_hash) WHERE device_hash IS NOT NULL;
CREATE INDEX web_push_subscriptions_account ON public.web_push_subscriptions (account_id);

CREATE TABLE public.web_push_deliveries (
    account_id TEXT COLLATE "C" NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    device_hash TEXT NOT NULL,
    endpoint_id TEXT NOT NULL,
    bedtime_date DATE NOT NULL,
    due_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    next_attempt TIMESTAMPTZ,
    attempts SMALLINT NOT NULL CHECK (attempts BETWEEN 1 AND 2),
    state TEXT NOT NULL CHECK (state IN ('sending','sent','retry','failed','uncertain','cancelled')),
    PRIMARY KEY (account_id, device_hash, bedtime_date),
    UNIQUE (account_id, endpoint_id, bedtime_date)
);

CREATE INDEX web_push_deliveries_updated ON public.web_push_deliveries (updated_at);
