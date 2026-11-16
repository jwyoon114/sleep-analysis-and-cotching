CREATE TABLE IF NOT EXISTS public.account_personalization (
    account_id TEXT PRIMARY KEY NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    mbti TEXT CHECK (mbti IN ('ISTJ','ISFJ','INFJ','INTJ','ISTP','ISFP','INFP','INTP','ESTP','ESFP','ENFP','ENTP','ESTJ','ESFJ','ENFJ','ENTJ')),
    speech TEXT NOT NULL CHECK (speech IN ('polite','casual')),
    intensity TEXT NOT NULL CHECK (intensity IN ('gentle','firm','direct')),
    allow_profanity BOOLEAN NOT NULL CHECK (allow_profanity IN (FALSE, TRUE)),
    character TEXT NOT NULL CHECK (character IN ('cat','raccoon','dog','rabbit')),
    completed_at TEXT NOT NULL,
    CHECK (NOT allow_profanity OR intensity = 'direct')
);
