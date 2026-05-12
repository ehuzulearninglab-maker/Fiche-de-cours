-- =========================================================================
-- 003 : Seed des 6 assistants par classe (CI à CM2)
-- =========================================================================
-- Crée un assistant pour chacune des 6 classes du primaire béninois.
-- L'assistant CM2 est actif par défaut (les 19 PDFs déjà extraits lui seront
-- attribués via scripts/seed_kb_cm2.py). Les 5 autres restent désactivés
-- jusqu'à ce que l'admin uploade leurs PDFs et les active.
--
-- Idempotent : `on conflict do nothing` sur la classe.
-- =========================================================================

create unique index if not exists assistants_classe_unique
    on public.assistants(classe)
    where classe is not null;

insert into public.assistants
    (name, description, classe, instructions, provider, is_active, is_public)
values
    ('Rédacteur CI',
     'Assistant pédagogique pour le Cours Initial.',
     'CI',
     '',
     'gemini',
     false,
     true),
    ('Rédacteur CP',
     'Assistant pédagogique pour le Cours Préparatoire.',
     'CP',
     '',
     'gemini',
     false,
     true),
    ('Rédacteur CE1',
     'Assistant pédagogique pour le Cours Élémentaire 1.',
     'CE1',
     '',
     'gemini',
     false,
     true),
    ('Rédacteur CE2',
     'Assistant pédagogique pour le Cours Élémentaire 2.',
     'CE2',
     '',
     'gemini',
     false,
     true),
    ('Rédacteur CM1',
     'Assistant pédagogique pour le Cours Moyen 1.',
     'CM1',
     '',
     'gemini',
     false,
     true),
    ('Rédacteur CM2',
     'Assistant pédagogique pour le Cours Moyen 2 — toutes matières.',
     'CM2',
     '',
     'gemini',
     true,
     true)
on conflict (classe) where classe is not null do nothing;
