-- Relax the legacy coupling only. Preserve every preference and coaching row.
-- The other enum/boolean/FK constraints remain unchanged. Safe to repeat.
ALTER TABLE public.account_personalization
    DROP CONSTRAINT IF EXISTS account_personalization_check;
