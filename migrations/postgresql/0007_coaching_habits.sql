CREATE TABLE public.coaching_preferences (
    account_id TEXT COLLATE "C" PRIMARY KEY REFERENCES public.accounts(id) ON DELETE CASCADE,
    age_group TEXT,
    usual_bedtime TEXT,
    usual_wake_time TEXT
);

CREATE TABLE public.coaching_daily_habits (
    account_id TEXT COLLATE "C" REFERENCES public.accounts(id) ON DELETE CASCADE,
    sleep_day TEXT NOT NULL,
    caffeine TEXT,
    satisfaction TEXT,
    PRIMARY KEY (account_id, sleep_day)
);
