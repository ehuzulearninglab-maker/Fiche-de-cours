-- =========================================================================
-- Fiche-de-cour — Migration 005 : suivi de la consommation de tokens LLM
-- =========================================================================
-- Crée une table d'événements de consommation : pour chaque appel LLM
-- réussi, on stocke combien de tokens (prompt + completion) ont été
-- facturés et à quel utilisateur. L'agrégation se fait à la lecture
-- (sum() au moment d'afficher la page admin).
--
-- Idempotente : peut être ré-exécutée sans danger.
-- =========================================================================

create table if not exists public.usage_events (
    id                uuid        primary key default gen_random_uuid(),
    user_id           uuid        references auth.users(id) on delete cascade,
    provider_id       text        not null,
    model             text,
    prompt_tokens     integer     not null default 0,
    completion_tokens integer     not null default 0,
    total_tokens      integer     not null default 0,
    created_at        timestamptz not null default now()
);

create index if not exists usage_events_user_idx
    on public.usage_events(user_id);
create index if not exists usage_events_created_idx
    on public.usage_events(created_at desc);

-- RLS : seul le service_role écrit/lit. Les utilisateurs n'ont aucun accès direct.
alter table public.usage_events enable row level security;

drop policy if exists usage_events_admin_read on public.usage_events;
create policy usage_events_admin_read on public.usage_events
    for select using (public.is_admin(auth.uid()));
