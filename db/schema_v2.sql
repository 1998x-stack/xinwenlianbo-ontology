-- Phase 2 migration: adds NewsEvent + junction tables

-- 1. NewsEvent: core event object
CREATE TABLE IF NOT EXISTS news_event (
    event_id          TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    type              TEXT NOT NULL CHECK (type IN ('political','economic','military','diplomatic','social','technological','environmental')),
    importance        TEXT NOT NULL DEFAULT 'routine' CHECK (importance IN ('routine','notable','major','critical')),
    status            TEXT NOT NULL DEFAULT 'emerging' CHECK (status IN ('emerging','developing','peak','declining','resolved','archived')),
    first_date        TEXT NOT NULL,
    last_date         TEXT NOT NULL,
    news_count        INTEGER NOT NULL DEFAULT 0,
    summary           TEXT,
    heat_score        REAL,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_event_type ON news_event(type);
CREATE INDEX IF NOT EXISTS idx_event_status ON news_event(status);
CREATE INDEX IF NOT EXISTS idx_event_heat ON news_event(heat_score);
CREATE INDEX IF NOT EXISTS idx_event_first_date ON news_event(first_date);
CREATE INDEX IF NOT EXISTS idx_event_last_date ON news_event(last_date);

-- 2. Junction: NewsItem coversEvent NewsEvent (many:many)
CREATE TABLE IF NOT EXISTS news_event_link (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    news_id           TEXT NOT NULL,
    event_id          TEXT NOT NULL,
    FOREIGN KEY (news_id) REFERENCES news_item(news_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (event_id) REFERENCES news_event(event_id) ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE (news_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_nel_news ON news_event_link(news_id);
CREATE INDEX IF NOT EXISTS idx_nel_event ON news_event_link(event_id);

-- 3. Junction: NewsEvent involves Person (many:many)
CREATE TABLE IF NOT EXISTS event_person (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id          TEXT NOT NULL,
    person_id         TEXT NOT NULL,
    role              TEXT NOT NULL DEFAULT 'mentioned' CHECK (role IN ('primary_actor','mentioned','affected')),
    FOREIGN KEY (event_id) REFERENCES news_event(event_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (person_id) REFERENCES person(person_id) ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE (event_id, person_id)
);

CREATE INDEX IF NOT EXISTS idx_ep_event ON event_person(event_id);
CREATE INDEX IF NOT EXISTS idx_ep_person ON event_person(person_id);

-- 4. Junction: NewsEvent involves Organization (many:many)
CREATE TABLE IF NOT EXISTS event_organization (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id          TEXT NOT NULL,
    org_id            TEXT NOT NULL,
    role              TEXT NOT NULL DEFAULT 'mentioned' CHECK (role IN ('primary_actor','mentioned','affected')),
    FOREIGN KEY (event_id) REFERENCES news_event(event_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (org_id) REFERENCES organization(org_id) ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE (event_id, org_id)
);

CREATE INDEX IF NOT EXISTS idx_eo_event ON event_organization(event_id);
CREATE INDEX IF NOT EXISTS idx_eo_org ON event_organization(org_id);

-- 5. Junction: NewsEvent relatedTo NewsEvent (many:many)
CREATE TABLE IF NOT EXISTS event_relation (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_event_id     TEXT NOT NULL,
    target_event_id     TEXT NOT NULL,
    similarity_score    REAL NOT NULL DEFAULT 0,
    relation_type       TEXT NOT NULL DEFAULT 'thematic' CHECK (relation_type IN ('causal','thematic','sequential')),
    time_interval_days  INTEGER,
    FOREIGN KEY (source_event_id) REFERENCES news_event(event_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (target_event_id) REFERENCES news_event(event_id) ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE (source_event_id, target_event_id)
);

CREATE INDEX IF NOT EXISTS idx_er_source ON event_relation(source_event_id);
CREATE INDEX IF NOT EXISTS idx_er_target ON event_relation(target_event_id);
