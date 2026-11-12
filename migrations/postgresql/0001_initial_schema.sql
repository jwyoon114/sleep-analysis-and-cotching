-- Daljam PostgreSQL migration 0001: initial schema.
-- Source: SQLite DDL in health_records.py, health_sync.py, sleep_alarms.py.
-- Run explicitly against an empty target only. Never invoked by the API.
-- 20 application tables + 1 migration history table; no user data is copied.
-- Intentionally fail on existing objects; do not hide incompatible schemas.
-- TEXT uses C collation to retain SQLite BINARY ordering/equality.
-- INTEGER -> BIGINT (64-bit); REAL -> DOUBLE PRECISION (64-bit).
-- PostgreSQL PKs reject NULL, including 17 columns SQLite permits as NULL.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SET LOCAL search_path = pg_catalog, public;

CREATE TABLE public.daljam_schema_migrations (
    "version" BIGINT NOT NULL,
    "name" TEXT COLLATE "C" NOT NULL,
    "applied_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT daljam_schema_migrations_pkey PRIMARY KEY ("version"),
    CONSTRAINT daljam_schema_migrations_name_key UNIQUE ("name")
);
CREATE TABLE public.accounts (
    "id" TEXT COLLATE "C" NOT NULL,
    "username" TEXT COLLATE "C" NOT NULL,
    "password_hash" TEXT COLLATE "C" NOT NULL,
    "salt" TEXT COLLATE "C" NOT NULL,
    "created_at" TEXT COLLATE "C" NOT NULL,
    CONSTRAINT accounts_pkey PRIMARY KEY ("id"),
    CONSTRAINT accounts_username_key UNIQUE ("username")
);

CREATE TABLE public.imports (
    "id" TEXT COLLATE "C" NOT NULL,
    "subject" TEXT COLLATE "C" NOT NULL,
    "filename" TEXT COLLATE "C" NOT NULL,
    "imported_at" TEXT COLLATE "C" NOT NULL,
    CONSTRAINT imports_pkey PRIMARY KEY ("id")
);

CREATE TABLE public.sessions (
    "id" TEXT COLLATE "C" NOT NULL,
    "subject" TEXT COLLATE "C" NOT NULL,
    "start" TEXT COLLATE "C" NOT NULL,
    "end" TEXT COLLATE "C" NOT NULL,
    "payload" TEXT COLLATE "C" NOT NULL,
    CONSTRAINT sessions_pkey PRIMARY KEY ("id")
);

CREATE TABLE public.import_sessions (
    "import_id" TEXT COLLATE "C" NOT NULL,
    "session_id" TEXT COLLATE "C" NOT NULL,
    CONSTRAINT import_sessions_pkey PRIMARY KEY ("import_id", "session_id"),
    CONSTRAINT import_sessions_import_id_fkey FOREIGN KEY ("import_id")
        REFERENCES public.imports ("id") ON UPDATE NO ACTION ON DELETE NO ACTION NOT DEFERRABLE,
    CONSTRAINT import_sessions_session_id_fkey FOREIGN KEY ("session_id")
        REFERENCES public.sessions ("id") ON UPDATE NO ACTION ON DELETE NO ACTION NOT DEFERRABLE
);

CREATE TABLE public.stages (
    "session_id" TEXT COLLATE "C" NOT NULL,
    "position" BIGINT NOT NULL,
    "start" TEXT COLLATE "C",
    "end" TEXT COLLATE "C",
    "stage" TEXT COLLATE "C",
    "minutes" DOUBLE PRECISION,
    CONSTRAINT stages_pkey PRIMARY KEY ("session_id", "position"),
    CONSTRAINT stages_session_id_fkey FOREIGN KEY ("session_id")
        REFERENCES public.sessions ("id") ON UPDATE NO ACTION ON DELETE NO ACTION NOT DEFERRABLE
);

CREATE TABLE public.samples (
    "id" TEXT COLLATE "C" NOT NULL,
    "subject" TEXT COLLATE "C" NOT NULL,
    "metric" TEXT COLLATE "C",
    "source" TEXT COLLATE "C",
    "unit" TEXT COLLATE "C",
    "start" TEXT COLLATE "C",
    "end" TEXT COLLATE "C",
    "value" DOUBLE PRECISION,
    CONSTRAINT samples_pkey PRIMARY KEY ("id")
);

CREATE TABLE public.auth_tokens (
    "token_hash" TEXT COLLATE "C" NOT NULL,
    "account_id" TEXT COLLATE "C" NOT NULL,
    "expires_at" TEXT COLLATE "C" NOT NULL,
    CONSTRAINT auth_tokens_pkey PRIMARY KEY ("token_hash"),
    CONSTRAINT auth_tokens_account_id_fkey FOREIGN KEY ("account_id")
        REFERENCES public.accounts ("id") ON UPDATE NO ACTION ON DELETE NO ACTION NOT DEFERRABLE
);

CREATE TABLE public.login_attempts (
    "username" TEXT COLLATE "C" NOT NULL,
    "attempted_at" TEXT COLLATE "C" NOT NULL
);

CREATE TABLE public.coaching (
    "id" TEXT COLLATE "C" NOT NULL,
    "account_id" TEXT COLLATE "C" NOT NULL,
    "session_id" TEXT COLLATE "C" NOT NULL,
    "text" TEXT COLLATE "C" NOT NULL,
    "lifestyle" TEXT COLLATE "C" NOT NULL,
    "created_at" TEXT COLLATE "C" NOT NULL,
    CONSTRAINT coaching_pkey PRIMARY KEY ("id"),
    CONSTRAINT coaching_account_id_fkey FOREIGN KEY ("account_id")
        REFERENCES public.accounts ("id") ON UPDATE NO ACTION ON DELETE NO ACTION NOT DEFERRABLE,
    CONSTRAINT coaching_session_id_fkey FOREIGN KEY ("session_id")
        REFERENCES public.sessions ("id") ON UPDATE NO ACTION ON DELETE NO ACTION NOT DEFERRABLE
);

CREATE TABLE public.trash_sessions (
    "session_id" TEXT COLLATE "C" NOT NULL,
    "subject" TEXT COLLATE "C" NOT NULL,
    "deleted_at" TEXT COLLATE "C" NOT NULL,
    CONSTRAINT trash_sessions_pkey PRIMARY KEY ("session_id"),
    CONSTRAINT trash_sessions_session_id_fkey FOREIGN KEY ("session_id")
        REFERENCES public.sessions ("id") ON UPDATE NO ACTION ON DELETE NO ACTION NOT DEFERRABLE
);

CREATE TABLE public.trash_coaching (
    "coaching_id" TEXT COLLATE "C" NOT NULL,
    "account_id" TEXT COLLATE "C" NOT NULL,
    "deleted_at" TEXT COLLATE "C" NOT NULL,
    CONSTRAINT trash_coaching_pkey PRIMARY KEY ("coaching_id"),
    CONSTRAINT trash_coaching_coaching_id_fkey FOREIGN KEY ("coaching_id")
        REFERENCES public.coaching ("id") ON UPDATE NO ACTION ON DELETE NO ACTION NOT DEFERRABLE
);

CREATE TABLE public.coaching_context (
    "coaching_id" TEXT COLLATE "C" NOT NULL,
    "payload" TEXT COLLATE "C" NOT NULL,
    CONSTRAINT coaching_context_pkey PRIMARY KEY ("coaching_id"),
    CONSTRAINT coaching_context_coaching_id_fkey FOREIGN KEY ("coaching_id")
        REFERENCES public.coaching ("id") ON UPDATE NO ACTION ON DELETE NO ACTION NOT DEFERRABLE
);

CREATE TABLE public.permanent_deletions (
    "kind" TEXT COLLATE "C" NOT NULL,
    "record_id" TEXT COLLATE "C" NOT NULL,
    "subject" TEXT COLLATE "C" NOT NULL,
    "deleted_at" TEXT COLLATE "C" NOT NULL,
    CONSTRAINT permanent_deletions_pkey PRIMARY KEY ("kind", "record_id", "subject")
);

CREATE TABLE public.session_created (
    "session_id" TEXT COLLATE "C" NOT NULL,
    "created_at" TEXT COLLATE "C" NOT NULL,
    CONSTRAINT session_created_pkey PRIMARY KEY ("session_id"),
    CONSTRAINT session_created_session_id_fkey FOREIGN KEY ("session_id")
        REFERENCES public.sessions ("id") ON UPDATE NO ACTION ON DELETE NO ACTION NOT DEFERRABLE
);

CREATE TABLE public.coaching_requests (
    "id" TEXT COLLATE "C" NOT NULL,
    "account_id" TEXT COLLATE "C",
    "requested_at" TEXT COLLATE "C" NOT NULL,
    CONSTRAINT coaching_requests_pkey PRIMARY KEY ("id")
);

CREATE TABLE public.health_connections (
    "account_id" TEXT COLLATE "C" NOT NULL,
    "token_hash" TEXT COLLATE "C" NOT NULL,
    "provider" TEXT COLLATE "C" NOT NULL,
    "source_id" TEXT COLLATE "C" NOT NULL,
    "source_name" TEXT COLLATE "C" NOT NULL,
    "created_at" TEXT COLLATE "C" NOT NULL,
    "expires_at" TEXT COLLATE "C" NOT NULL,
    "last_synced_at" TEXT COLLATE "C",
    "auto_coach" BIGINT NOT NULL DEFAULT 0,
    "advice_status" TEXT COLLATE "C",
    "last_window_end" TEXT COLLATE "C",
    CONSTRAINT health_connections_pkey PRIMARY KEY ("account_id"),
    CONSTRAINT health_connections_token_hash_key UNIQUE ("token_hash"),
    CONSTRAINT health_connections_account_id_fkey FOREIGN KEY ("account_id")
        REFERENCES public.accounts ("id") ON UPDATE NO ACTION ON DELETE CASCADE NOT DEFERRABLE
);

CREATE TABLE public.health_sync_sessions (
    "account_id" TEXT COLLATE "C" NOT NULL,
    "day" TEXT COLLATE "C" NOT NULL,
    "session_id" TEXT COLLATE "C" NOT NULL,
    CONSTRAINT health_sync_sessions_pkey PRIMARY KEY ("account_id", "day"),
    CONSTRAINT health_sync_sessions_session_id_key UNIQUE ("session_id"),
    CONSTRAINT health_sync_sessions_account_id_fkey FOREIGN KEY ("account_id")
        REFERENCES public.accounts ("id") ON UPDATE NO ACTION ON DELETE CASCADE NOT DEFERRABLE,
    CONSTRAINT health_sync_sessions_session_id_fkey FOREIGN KEY ("session_id")
        REFERENCES public.sessions ("id") ON UPDATE NO ACTION ON DELETE CASCADE NOT DEFERRABLE
);

CREATE TABLE public.health_advice_jobs (
    "account_id" TEXT COLLATE "C" NOT NULL,
    "session_id" TEXT COLLATE "C" NOT NULL,
    CONSTRAINT health_advice_jobs_pkey PRIMARY KEY ("account_id", "session_id"),
    CONSTRAINT health_advice_jobs_account_id_fkey FOREIGN KEY ("account_id")
        REFERENCES public.accounts ("id") ON UPDATE NO ACTION ON DELETE CASCADE NOT DEFERRABLE,
    CONSTRAINT health_advice_jobs_session_id_fkey FOREIGN KEY ("session_id")
        REFERENCES public.sessions ("id") ON UPDATE NO ACTION ON DELETE CASCADE NOT DEFERRABLE
);

CREATE TABLE public.sleep_alarm_settings (
    "account_id" TEXT COLLATE "C" NOT NULL,
    "bedtime" TEXT COLLATE "C" NOT NULL,
    "wake_time" TEXT COLLATE "C" NOT NULL,
    "timezone" TEXT COLLATE "C" NOT NULL,
    "enabled" BIGINT NOT NULL,
    "coaching_id" TEXT COLLATE "C",
    "updated_at" TEXT COLLATE "C" NOT NULL,
    CONSTRAINT sleep_alarm_settings_pkey PRIMARY KEY ("account_id"),
    CONSTRAINT sleep_alarm_settings_account_id_fkey FOREIGN KEY ("account_id")
        REFERENCES public.accounts ("id") ON UPDATE NO ACTION ON DELETE NO ACTION NOT DEFERRABLE
);

CREATE TABLE public.sleep_alarm_fires (
    "account_id" TEXT COLLATE "C" NOT NULL,
    "kind" TEXT COLLATE "C" NOT NULL,
    "local_date" TEXT COLLATE "C" NOT NULL,
    "fired_at" TEXT COLLATE "C" NOT NULL,
    CONSTRAINT sleep_alarm_fires_pkey PRIMARY KEY ("account_id", "kind", "local_date"),
    CONSTRAINT sleep_alarm_fires_account_id_fkey FOREIGN KEY ("account_id")
        REFERENCES public.accounts ("id") ON UPDATE NO ACTION ON DELETE NO ACTION NOT DEFERRABLE
);

CREATE INDEX sessions_subject_start ON public.sessions ("subject", "start");
CREATE INDEX samples_observation ON public.samples ("subject", "metric", "source", "unit", "start", "end");
CREATE INDEX coaching_account_session ON public.coaching ("account_id", "session_id", "created_at");
CREATE INDEX trash_sessions_owner_time ON public.trash_sessions ("subject", "deleted_at");
CREATE INDEX trash_coaching_owner_time ON public.trash_coaching ("account_id", "deleted_at");
CREATE INDEX coaching_requests_time ON public.coaching_requests ("requested_at");

-- Infrastructure metadata only. No INSERT/UPDATE/DELETE targets an application table.
INSERT INTO public.daljam_schema_migrations ("version", "name")
VALUES (1, '0001_initial_schema');

COMMIT;
