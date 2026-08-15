-- Clydesdale Capital: members + voting + golf poll  (safe to re-run)
-- Mirror of the Supabase project schema (project ref nvhsvcesvkudgttmbpvg).
-- Kept in the repo so the database can be rebuilt from scratch if the project
-- is ever lost. Free-tier projects pause after ~7 days idle.
create table if not exists members (id bigint generated always as identity primary key, name text not null, email text unique not null, code text);
create table if not exists proposals (id bigint generated always as identity primary key, ticker text, title text not null, proposed_by text, summary text, status text default 'open', created_at timestamptz default now());
create table if not exists votes (id bigint generated always as identity primary key, proposal_id bigint references proposals(id) on delete cascade, member_id bigint references members(id) on delete cascade, choice text not null, reason text, created_at timestamptz default now(), unique(proposal_id, member_id));
create table if not exists polls (id bigint generated always as identity primary key, question text not null, kind text default 'multi', status text default 'open');
create table if not exists poll_options (id bigint generated always as identity primary key, poll_id bigint references polls(id) on delete cascade, label text not null, sort int default 0);
create table if not exists poll_votes (id bigint generated always as identity primary key, poll_id bigint references polls(id) on delete cascade, option_id bigint references poll_options(id) on delete cascade, member_id bigint references members(id) on delete cascade, unique(poll_id, option_id, member_id));

alter table votes add column if not exists reason text;
create unique index if not exists proposals_ticker_uidx on proposals(ticker);
create unique index if not exists polls_question_uidx on polls(question);
create unique index if not exists poll_options_uidx on poll_options(poll_id,label);

create or replace view vote_tallies as select proposal_id, choice, count(*)::int votes from votes group by 1,2;
create or replace view vote_reasons as select proposal_id, reason from votes where choice='no' and reason is not null and length(trim(reason))>0;
create or replace view member_directory as select id, name from members;
create or replace view poll_tallies as select pv.poll_id, pv.option_id, po.label, po.sort, count(*)::int votes from poll_votes pv join poll_options po on po.id=pv.option_id group by 1,2,3,4;
create or replace view poll_detail as select pv.poll_id, pv.option_id, po.label, m.name from poll_votes pv join poll_options po on po.id=pv.option_id join members m on m.id=pv.member_id;

-- members.code is the lower-cased last name: update members set code = lower(split_part(name,' ',2));
create or replace function member_login(p_code text) returns table(id bigint, name text) language sql security definer set search_path=public as $$ select id,name from members where lower(code)=lower(trim(p_code)) limit 1 $$;
create or replace function cast_vote(p_member_id bigint, p_proposal_id bigint, p_choice text, p_reason text) returns void language sql security definer set search_path=public as $$ insert into votes(proposal_id,member_id,choice,reason) values(p_proposal_id,p_member_id,p_choice,p_reason) on conflict (proposal_id,member_id) do update set choice=excluded.choice, reason=excluded.reason, created_at=now() $$;
create or replace function cast_poll_vote(p_member_id bigint, p_poll_id bigint, p_option_id bigint, p_on boolean) returns void language plpgsql security definer set search_path=public as $$ begin if p_on then insert into poll_votes(poll_id,option_id,member_id) values(p_poll_id,p_option_id,p_member_id) on conflict do nothing; else delete from poll_votes where poll_id=p_poll_id and option_id=p_option_id and member_id=p_member_id; end if; end $$;

alter table members enable row level security;
alter table proposals enable row level security;
alter table votes enable row level security;
alter table polls enable row level security;
alter table poll_options enable row level security;
alter table poll_votes enable row level security;
drop policy if exists "read proposals" on proposals; create policy "read proposals" on proposals for select to anon using (true);
drop policy if exists "read polls" on polls; create policy "read polls" on polls for select to anon using (true);
drop policy if exists "read options" on poll_options; create policy "read options" on poll_options for select to anon using (true);
grant select on vote_tallies, vote_reasons, member_directory, poll_tallies, poll_detail to anon;
grant execute on function member_login(text), cast_vote(bigint,bigint,text,text), cast_poll_vote(bigint,bigint,bigint,boolean) to anon;
