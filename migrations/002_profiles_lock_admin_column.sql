-- =========================================================================
-- 002 : Empêche un utilisateur de se promouvoir lui-même admin via PostgREST
-- =========================================================================
--
-- Contexte : la policy `profiles_update_self` (migration 001) autorisait
-- `update` sur toute la ligne quand `auth.uid() = id`. Sans `WITH CHECK`
-- restreignant les colonnes modifiables, n'importe quel user authentifié
-- pouvait `PATCH /rest/v1/profiles?id=eq.<self> { "is_admin": true }`
-- en s'envoyant directement à PostgREST avec la clé anon (publique) et son
-- JWT — escalade de privilèges.
--
-- Fix : on conserve l'autorisation d'update mais on contraint via WITH CHECK
-- que `is_admin` reste identique à sa valeur courante. Seule la policy
-- `profiles_update_admin` (réservée aux admins) peut modifier ce flag.
-- =========================================================================

drop policy if exists profiles_update_self on public.profiles;

create policy profiles_update_self on public.profiles
    for update
    using (auth.uid() = id)
    with check (
        auth.uid() = id
        and is_admin is not distinct from (
            select p.is_admin from public.profiles p where p.id = auth.uid()
        )
    );
