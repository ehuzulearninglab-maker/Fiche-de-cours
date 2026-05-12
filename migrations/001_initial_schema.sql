-- =========================================================================
-- Fiche-de-cour — Schéma initial Supabase
-- =========================================================================
-- Ce script est idempotent (CREATE TABLE IF NOT EXISTS). Il peut être
-- ré-exécuté en toute sécurité.
--
-- Tables :
--   profiles                -- métadonnées utilisateur (lié à auth.users)
--   api_keys                -- clés API LLM (admin only)
--   assistants              -- assistants (1 par classe : CI..CM2)
--   assistant_documents     -- PDFs propres à chaque assistant (KB)
--   conversations           -- conversations utilisateur ↔ assistant
--   messages                -- messages (user / assistant) dans une conversation
-- =========================================================================

-- 1) Profils utilisateur ----------------------------------------------------
create table if not exists public.profiles (
    id          uuid        primary key references auth.users(id) on delete cascade,
    email       text        not null,
    full_name   text,
    is_admin    boolean     not null default false,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create index if not exists profiles_is_admin_idx on public.profiles(is_admin) where is_admin;

-- Trigger : crée automatiquement un profil quand un utilisateur s'inscrit
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (id, email, full_name)
    values (
        new.id,
        new.email,
        coalesce(new.raw_user_meta_data->>'full_name', '')
    )
    on conflict (id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- 2) Clés API LLM (admin only) ---------------------------------------------
create table if not exists public.api_keys (
    provider    text        primary key,         -- 'openai', 'gemini', 'groq', ...
    api_key     text        not null,            -- valeur en clair (RLS bloque la lecture)
    updated_at  timestamptz not null default now(),
    updated_by  uuid        references auth.users(id) on delete set null
);

-- 3) Assistants (1 par classe) ---------------------------------------------
create table if not exists public.assistants (
    id              uuid        primary key default gen_random_uuid(),
    name            text        not null,                  -- "Rédacteur CM2"
    description     text        not null default '',
    classe          text,                                  -- 'CI', 'CP', 'CE1', 'CE2', 'CM1', 'CM2' ou null
    avatar_url      text,
    instructions    text        not null default '',       -- system prompt
    provider        text        not null default 'gemini', -- fournisseur LLM
    model           text,                                  -- modèle (peut écraser le défaut)
    is_active       boolean     not null default true,
    is_public       boolean     not null default true,
    allow_uploads   boolean     not null default true,
    created_by      uuid        references auth.users(id) on delete set null,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create index if not exists assistants_classe_idx on public.assistants(classe);
create index if not exists assistants_active_public_idx on public.assistants(is_active, is_public);

-- 4) Documents par assistant (KB) ------------------------------------------
create table if not exists public.assistant_documents (
    id              uuid        primary key default gen_random_uuid(),
    assistant_id    uuid        not null references public.assistants(id) on delete cascade,
    name            text        not null,
    content         text        not null,                  -- texte extrait (UTF-8)
    bytes           integer     not null default 0,
    uploaded_by     uuid        references auth.users(id) on delete set null,
    uploaded_at     timestamptz not null default now()
);

create index if not exists assistant_documents_assistant_idx
    on public.assistant_documents(assistant_id);

-- 5) Conversations ---------------------------------------------------------
create table if not exists public.conversations (
    id              uuid        primary key default gen_random_uuid(),
    user_id         uuid        not null references auth.users(id) on delete cascade,
    assistant_id    uuid        not null references public.assistants(id) on delete cascade,
    title           text        not null default 'Nouvelle conversation',
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create index if not exists conversations_user_idx     on public.conversations(user_id);
create index if not exists conversations_updated_idx  on public.conversations(updated_at desc);

-- 6) Messages --------------------------------------------------------------
create table if not exists public.messages (
    id              uuid        primary key default gen_random_uuid(),
    conversation_id uuid        not null references public.conversations(id) on delete cascade,
    role            text        not null check (role in ('user', 'assistant', 'system')),
    content         text        not null,
    metadata        jsonb       not null default '{}'::jsonb,
    created_at      timestamptz not null default now()
);

create index if not exists messages_conversation_idx on public.messages(conversation_id, created_at);

-- =========================================================================
-- Row Level Security (RLS)
-- =========================================================================
alter table public.profiles            enable row level security;
alter table public.api_keys            enable row level security;
alter table public.assistants          enable row level security;
alter table public.assistant_documents enable row level security;
alter table public.conversations       enable row level security;
alter table public.messages            enable row level security;

-- Helper : user courant est admin ?
create or replace function public.is_admin(uid uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select coalesce(
        (select is_admin from public.profiles where id = uid),
        false
    );
$$;

-- profiles : chaque user lit/met à jour son profil. Admin lit tous les profils.
drop policy if exists profiles_select_self    on public.profiles;
drop policy if exists profiles_select_admin   on public.profiles;
drop policy if exists profiles_update_self    on public.profiles;
drop policy if exists profiles_update_admin   on public.profiles;

create policy profiles_select_self  on public.profiles
    for select using (auth.uid() = id);

create policy profiles_select_admin on public.profiles
    for select using (public.is_admin(auth.uid()));

create policy profiles_update_self  on public.profiles
    for update using (auth.uid() = id);

create policy profiles_update_admin on public.profiles
    for update using (public.is_admin(auth.uid()));

-- api_keys : admin only. (Le backend Flask passe par service_role pour bypass RLS si besoin.)
drop policy if exists api_keys_admin_all on public.api_keys;
create policy api_keys_admin_all on public.api_keys
    for all using (public.is_admin(auth.uid())) with check (public.is_admin(auth.uid()));

-- assistants : tout user authentifié peut lister les actifs/publics ; admin gère tout.
drop policy if exists assistants_select_public on public.assistants;
drop policy if exists assistants_admin_all     on public.assistants;

create policy assistants_select_public on public.assistants
    for select using (
        is_active and is_public
        or public.is_admin(auth.uid())
    );

create policy assistants_admin_all on public.assistants
    for all using (public.is_admin(auth.uid())) with check (public.is_admin(auth.uid()));

-- assistant_documents : admin only (les users n'ont pas besoin de voir le contenu brut).
drop policy if exists assistant_documents_admin_all on public.assistant_documents;
create policy assistant_documents_admin_all on public.assistant_documents
    for all using (public.is_admin(auth.uid())) with check (public.is_admin(auth.uid()));

-- conversations : chaque user voit ses conversations, admin voit tout.
drop policy if exists conversations_owner    on public.conversations;
drop policy if exists conversations_admin    on public.conversations;

create policy conversations_owner on public.conversations
    for all using (user_id = auth.uid()) with check (user_id = auth.uid());

create policy conversations_admin on public.conversations
    for select using (public.is_admin(auth.uid()));

-- messages : accessibles via leur conversation parente.
drop policy if exists messages_owner on public.messages;
drop policy if exists messages_admin on public.messages;

create policy messages_owner on public.messages
    for all using (
        exists (
            select 1 from public.conversations c
            where c.id = messages.conversation_id and c.user_id = auth.uid()
        )
    ) with check (
        exists (
            select 1 from public.conversations c
            where c.id = messages.conversation_id and c.user_id = auth.uid()
        )
    );

create policy messages_admin on public.messages
    for select using (public.is_admin(auth.uid()));

-- =========================================================================
-- Trigger : updated_at automatique
-- =========================================================================
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists set_updated_at_profiles   on public.profiles;
create trigger set_updated_at_profiles   before update on public.profiles
    for each row execute function public.set_updated_at();

drop trigger if exists set_updated_at_assistants on public.assistants;
create trigger set_updated_at_assistants before update on public.assistants
    for each row execute function public.set_updated_at();

drop trigger if exists set_updated_at_conversations on public.conversations;
create trigger set_updated_at_conversations before update on public.conversations
    for each row execute function public.set_updated_at();

drop trigger if exists set_updated_at_api_keys on public.api_keys;
create trigger set_updated_at_api_keys   before update on public.api_keys
    for each row execute function public.set_updated_at();
