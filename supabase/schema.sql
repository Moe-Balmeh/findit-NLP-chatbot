-- run this once in supabase: SQL Editor -> New query -> paste -> Run

create table if not exists found_items (
  id uuid primary key default gen_random_uuid(),
  ref_code text unique not null,
  item text not null,
  brand text,
  color text,
  description text,
  location text,
  location_detail text,
  zone text,
  room text,
  floor int,
  date date,
  time text,
  status text not null default 'pending_surrender'
    check (status in ('pending_surrender', 'in_custody', 'claimed', 'disposed')),
  created_at timestamptz not null default now(),
  claimed_at timestamptz
);

create table if not exists lost_reports (
  id uuid primary key default gen_random_uuid(),
  ref_code text unique not null,
  item text not null,
  brand text,
  color text,
  description text,
  location text,
  location_detail text,
  zone text,
  room text,
  floor int,
  date date,
  time text,
  status text not null default 'open'
    check (status in ('open', 'matched', 'returned', 'closed')),
  created_at timestamptz not null default now(),
  resolved_at timestamptz
);

create table if not exists matches (
  id uuid primary key default gen_random_uuid(),
  lost_id uuid not null references lost_reports(id) on delete cascade,
  found_id uuid not null references found_items(id) on delete cascade,
  score int not null,
  status text not null default 'suggested'
    check (status in ('suggested', 'confirmed', 'rejected')),
  created_at timestamptz not null default now(),
  unique (lost_id, found_id)
);

create table if not exists chat_logs (
  id bigint generated always as identity primary key,
  session_id text,
  message text,
  intent text,
  confidence real,
  created_at timestamptz not null default now()
);

-- emails allowed into the admin dashboard
create table if not exists admins (
  email text primary key
);

create index if not exists found_items_open_idx on found_items (item, status);
create index if not exists lost_reports_open_idx on lost_reports (item, status);
create index if not exists chat_logs_created_idx on chat_logs (created_at);

-- lock everything down. the flask api uses the service role key (server only),
-- so the public anon key can't read or write any of this directly
alter table found_items enable row level security;
alter table lost_reports enable row level security;
alter table matches enable row level security;
alter table chat_logs enable row level security;
alter table admins enable row level security;
