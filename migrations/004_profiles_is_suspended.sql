-- =========================================================================
-- Fiche-de-cour — Migration 004 : suspension d'utilisateurs
-- =========================================================================
-- Ajoute une colonne `is_suspended` à `profiles` permettant à un admin de
-- bloquer l'accès à l'application sans détruire le compte. La suppression
-- définitive utilise `auth.admin.delete_user` qui cascade automatiquement
-- vers `profiles` (FK ON DELETE CASCADE déjà en place dans la migration 001).
--
-- Ce script est idempotent : il peut être ré-exécuté en toute sécurité.
-- =========================================================================

alter table public.profiles
    add column if not exists is_suspended boolean not null default false;

create index if not exists profiles_is_suspended_idx
    on public.profiles(is_suspended) where is_suspended;

-- RLS : seul un admin peut modifier `is_suspended` (la policy
-- `profiles_update_admin` existante l'autorise déjà). On verrouille en plus
-- la policy `profiles_update_self` pour empêcher un user de se "désuspendre"
-- lui-même.
drop policy if exists profiles_update_self on public.profiles;
create policy profiles_update_self on public.profiles
    for update
    using (auth.uid() = id)
    with check (
        auth.uid() = id
        and is_admin is not distinct from (
            select p.is_admin from public.profiles p where p.id = auth.uid()
        )
        and is_suspended is not distinct from (
            select p.is_suspended from public.profiles p where p.id = auth.uid()
        )
    );
