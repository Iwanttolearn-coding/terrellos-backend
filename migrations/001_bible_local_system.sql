-- PastorAIConnect Local Bible System
-- Safe for public-domain/local Bible versions

create extension if not exists pg_trgm;

-- 1. Bible versions
create table if not exists bible_versions (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique, -- en-kjv, en-asv, geneva-1599, etc.
  name text not null,
  abbreviation text not null,
  language text default 'en',
  era text,
  scope text not null default 'full_bible', -- full_bible, old_testament, torah
  copyright_status text default 'public_domain',
  source text,
  is_enabled boolean default true,
  is_safe_for_generation boolean default true,
  notes text,
  imported_at timestamptz,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- 2. Bible books
create table if not exists bible_books (
  id uuid primary key default gen_random_uuid(),
  testament text not null, -- old, new, apocrypha
  book_order int not null,
  slug text not null unique, -- genesis, john, psalms
  name text not null,
  common_abbreviation text,
  alternate_names text[] default '{}',
  created_at timestamptz default now()
);

-- 3. Version-specific book support
create table if not exists bible_version_books (
  id uuid primary key default gen_random_uuid(),
  version_id uuid not null references bible_versions(id) on delete cascade,
  book_id uuid not null references bible_books(id) on delete cascade,
  source_book_slug text not null,
  is_supported boolean default true,
  notes text,
  unique(version_id, book_id)
);

-- 4. Bible chapters
create table if not exists bible_chapters (
  id uuid primary key default gen_random_uuid(),
  version_id uuid not null references bible_versions(id) on delete cascade,
  book_id uuid not null references bible_books(id) on delete cascade,
  chapter_number int not null,
  verse_count int default 0,
  imported_at timestamptz default now(),
  unique(version_id, book_id, chapter_number)
);

-- 5. Bible verses
create table if not exists bible_verses (
  id uuid primary key default gen_random_uuid(),
  version_id uuid not null references bible_versions(id) on delete cascade,
  book_id uuid not null references bible_books(id) on delete cascade,
  chapter_number int not null,
  verse_number int not null,
  reference text not null, -- John 3:16
  text text not null,
  clean_text text,
  search_vector tsvector,
  imported_at timestamptz default now(),
  unique(version_id, book_id, chapter_number, verse_number)
);

-- 6. Saved Bible studies / teachings
create table if not exists saved_bible_studies (
  id uuid primary key default gen_random_uuid(),
  user_id uuid,
  title text not null,
  version_slug text,
  book_slug text,
  chapter_number int,
  verse_number int,
  reference text,
  scripture_text text,
  teaching text,
  summary text,
  historical_context text,
  key_words jsonb default '[]',
  practical_application text,
  prayer text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- 7. Bible import logs
create table if not exists bible_import_logs (
  id uuid primary key default gen_random_uuid(),
  version_slug text not null,
  status text not null, -- started, completed, failed
  books_imported int default 0,
  chapters_imported int default 0,
  verses_imported int default 0,
  error_message text,
  started_at timestamptz default now(),
  completed_at timestamptz
);

-- 8. Bible generation audit
create table if not exists bible_generation_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid,
  version_slug text,
  reference text,
  tool_name text, -- sermon_builder, bible_reader, devotional, bible_game
  prompt text,
  output_preview text,
  created_at timestamptz default now()
);

-- Indexes
create index if not exists idx_bible_versions_slug on bible_versions(slug);
create index if not exists idx_bible_books_slug on bible_books(slug);
create index if not exists idx_bible_verses_reference on bible_verses(reference);
create index if not exists idx_bible_verses_lookup on bible_verses(version_id, book_id, chapter_number, verse_number);
create index if not exists idx_bible_verses_text_trgm on bible_verses using gin (text gin_trgm_ops);
create index if not exists idx_bible_verses_search_vector on bible_verses using gin(search_vector);

-- Auto-update search vector
create or replace function update_bible_verse_search_vector()
returns trigger as $$
begin
  new.clean_text := regexp_replace(coalesce(new.text, ''), '\s+', ' ', 'g');
  new.search_vector := to_tsvector('english', coalesce(new.clean_text, ''));
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_update_bible_verse_search_vector on bible_verses;

create trigger trg_update_bible_verse_search_vector
before insert or update on bible_verses
for each row
execute function update_bible_verse_search_vector();

-- Seed verified safe Bible versions
insert into bible_versions (
  slug, name, abbreviation, language, era, scope, copyright_status, is_enabled, is_safe_for_generation, notes
)
values
('kjv', 'King James Version', 'KJV', 'en', '1769', 'full_bible', 'public_domain', true, true, 'Verified safe full Bible'),
('asv', 'American Standard Version', 'ASV', 'en', '1901', 'full_bible', 'public_domain', true, true, 'Verified safe full Bible'),
('geneva', 'Geneva Bible', 'GENEVA', 'en', '1599', 'full_bible', 'public_domain', true, true, 'Verified safe full Bible'),
('cambridge-kjv', 'Cambridge Paragraph Bible', 'CPB', 'en', '19th century', 'full_bible', 'public_domain', true, true, 'KJV with modern punctuation'),
('douay-rheims', 'Douay-Rheims American Edition', 'DRA', 'en', '1899', 'full_bible', 'public_domain', true, true, 'Catholic tradition'),
('revised-version', 'Revised Version', 'RV', 'en', '1885', 'full_bible', 'public_domain', true, true, 'Verified safe full Bible'),
('old-jps', 'Old JPS TaNaKH', 'JPS', 'en', '1917', 'old_testament', 'public_domain', true, true, 'Old Testament only'),
('targum-onkelos', 'Targum Onkelos Etheridge', 'ONKELOS', 'en', 'ancient / 19th century translation', 'torah', 'public_domain', true, true, 'Torah only')
on conflict (slug) do update set
  name = excluded.name,
  abbreviation = excluded.abbreviation,
  era = excluded.era,
  scope = excluded.scope,
  copyright_status = excluded.copyright_status,
  is_enabled = excluded.is_enabled,
  is_safe_for_generation = excluded.is_safe_for_generation,
  notes = excluded.notes,
  updated_at = now();
