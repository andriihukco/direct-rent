-- Web cabinets: profiles, tenant profile, owner flats, tenant documents, storage buckets, RLS.
-- Bot tables (001_init.sql) also get RLS: with no policies, anon and authenticated see nothing;
-- the bot connects as the database owner, which bypasses RLS.

create table profiles (
    id          uuid primary key references auth.users(id) on delete cascade,
    role        text not null check (role in ('tenant', 'owner')),
    name        text,
    phone       text,
    created_at  timestamptz not null default now()
);

create table tenant_profiles (
    profile_id    uuid primary key references profiles(id) on delete cascade,
    occupation    text,
    move_in       text,
    term          text,
    people        int not null default 1 check (people between 1 and 10),
    pets          boolean not null default false,
    pet_note      text,
    kids          boolean not null default false,
    foreign_citizen boolean not null default false,
    student       boolean not null default false,
    budget_uah    int check (budget_uah is null or budget_uah > 0),
    about         text,
    verified_dia  boolean not null default false,
    updated_at    timestamptz not null default now()
);

create table owner_flats (
    id                 bigserial primary key,
    owner_id           uuid not null references profiles(id) on delete cascade,
    district           text,
    rooms              int check (rooms is null or rooms between 1 and 3),
    price_uah          int check (price_uah is null or price_uah > 0),
    rules              text[] not null default '{}',
    contract_official  boolean not null default true,
    photo_paths        text[] not null default '{}',
    created_at         timestamptz not null default now()
);
create index owner_flats_owner on owner_flats (owner_id);

create table tenant_docs (
    id           bigserial primary key,
    tenant_id    uuid not null references profiles(id) on delete cascade,
    kind         text not null,
    storage_path text not null unique,
    created_at   timestamptz not null default now()
);
create index tenant_docs_tenant on tenant_docs (tenant_id);

-- Role is chosen once at onboarding; it cannot be changed from the client.
create function prevent_role_change() returns trigger language plpgsql as $$
begin
    if new.role <> old.role then
        raise exception 'role is fixed after onboarding';
    end if;
    return new;
end $$;
create trigger profiles_role_fixed before update on profiles
    for each row execute function prevent_role_change();

-- Row Level Security: every table, no implicit access.
alter table profiles enable row level security;
alter table tenant_profiles enable row level security;
alter table owner_flats enable row level security;
alter table tenant_docs enable row level security;

create policy profiles_own_select on profiles for select to authenticated using (id = auth.uid());
create policy profiles_own_insert on profiles for insert to authenticated with check (id = auth.uid());
create policy profiles_own_update on profiles for update to authenticated
    using (id = auth.uid()) with check (id = auth.uid());

create policy tenant_profiles_own on tenant_profiles for all to authenticated
    using (profile_id = auth.uid()) with check (
        profile_id = auth.uid()
        and exists (select 1 from profiles p where p.id = auth.uid() and p.role = 'tenant'));

create policy owner_flats_own on owner_flats for all to authenticated
    using (owner_id = auth.uid()) with check (
        owner_id = auth.uid()
        and exists (select 1 from profiles p where p.id = auth.uid() and p.role = 'owner'));

create policy tenant_docs_own on tenant_docs for all to authenticated
    using (tenant_id = auth.uid()) with check (
        tenant_id = auth.uid()
        and exists (select 1 from profiles p where p.id = auth.uid() and p.role = 'tenant'));

-- Bot tables: lock them down for the public API. Only listings that passed the filter are readable,
-- and only by tenants. Raw bytes and raw contacts never reach the browser.
alter table users enable row level security;
alter table filters enable row level security;
alter table objects enable row level security;
alter table listings enable row level security;
alter table contacts enable row level security;
alter table listing_contacts enable row level security;
alter table complaints enable row level security;
alter table deliveries enable row level security;
alter table outbox enable row level security;
alter table source_state enable row level security;
alter table schema_migrations enable row level security;

create policy listings_pass_for_tenants on listings for select to authenticated using (
    verdict in ('pass', 'pass_unverified')
    and exists (select 1 from profiles p where p.id = auth.uid() and p.role = 'tenant'));

revoke all on listings from anon, authenticated;
grant select (id, source, source_id, url, object_id, text, channel_title, price_uah, price_raw, rooms,
              district, street, pets, posted_at, ingested_at, verdict, verdict_stage, verdict_reason,
              photo_url)
    on listings to authenticated;

-- Storage: private buckets. Each user writes only under their own folder: <uid>/...
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types) values
    ('listing-photos', 'listing-photos', false, 10485760, array['image/jpeg','image/png','image/webp']),
    ('tenant-docs', 'tenant-docs', false, 10485760, array['image/jpeg','image/png','image/webp','application/pdf'])
on conflict (id) do nothing;

create policy listing_photos_own_read on storage.objects for select to authenticated using (
    bucket_id = 'listing-photos' and (storage.foldername(name))[1] = auth.uid()::text);
create policy listing_photos_own_write on storage.objects for insert to authenticated with check (
    bucket_id = 'listing-photos' and (storage.foldername(name))[1] = auth.uid()::text);
create policy listing_photos_own_delete on storage.objects for delete to authenticated using (
    bucket_id = 'listing-photos' and (storage.foldername(name))[1] = auth.uid()::text);

create policy tenant_docs_own_read on storage.objects for select to authenticated using (
    bucket_id = 'tenant-docs' and (storage.foldername(name))[1] = auth.uid()::text);
create policy tenant_docs_own_write on storage.objects for insert to authenticated with check (
    bucket_id = 'tenant-docs' and (storage.foldername(name))[1] = auth.uid()::text);
create policy tenant_docs_own_delete on storage.objects for delete to authenticated using (
    bucket_id = 'tenant-docs' and (storage.foldername(name))[1] = auth.uid()::text);
