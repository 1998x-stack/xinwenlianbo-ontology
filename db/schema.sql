PRAGMA foreign_keys = ON;

-- news_item: individual news segment within a daily broadcast
CREATE TABLE IF NOT EXISTS news_item (
    news_id           TEXT PRIMARY KEY,
    title             TEXT NOT NULL,
    full_text         TEXT,
    broadcast_date    TEXT NOT NULL,
    order_in_broadcast INTEGER,
    summary           TEXT,
    keywords          TEXT,
    tags              TEXT,
    url               TEXT,
    word_count        INTEGER,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_news_broadcast_date ON news_item(broadcast_date);
CREATE INDEX idx_news_title ON news_item(title);

-- person: individual mentioned in news
CREATE TABLE IF NOT EXISTS person (
    person_id         TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    name_chinese      TEXT NOT NULL,
    title             TEXT,
    organization_id   TEXT,
    article_count     INTEGER,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (organization_id) REFERENCES organization(org_id)
        ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE INDEX idx_person_name ON person(name_chinese);

-- organization: institutional entity
CREATE TABLE IF NOT EXISTS organization (
    org_id            TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    type              TEXT CHECK (type IN ('government','military','enterprise','international','media','academic')),
    article_count     INTEGER,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_org_name ON organization(name);

-- topic: policy/research topic
CREATE TABLE IF NOT EXISTS topic (
    topic_id          TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    category          TEXT,
    article_count     INTEGER,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_topic_name ON topic(name);
CREATE INDEX idx_topic_category ON topic(category);

-- junction: news_item mentions person
CREATE TABLE IF NOT EXISTS news_person (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    news_id           TEXT NOT NULL,
    person_id         TEXT NOT NULL,
    FOREIGN KEY (news_id) REFERENCES news_item(news_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (person_id) REFERENCES person(person_id) ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE (news_id, person_id)
);

CREATE INDEX idx_np_news ON news_person(news_id);
CREATE INDEX idx_np_person ON news_person(person_id);

-- junction: news_item mentions organization
CREATE TABLE IF NOT EXISTS news_organization (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    news_id           TEXT NOT NULL,
    org_id            TEXT NOT NULL,
    FOREIGN KEY (news_id) REFERENCES news_item(news_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (org_id) REFERENCES organization(org_id) ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE (news_id, org_id)
);

CREATE INDEX idx_no_news ON news_organization(news_id);
CREATE INDEX idx_no_org ON news_organization(org_id);

-- junction: news_item about topic
CREATE TABLE IF NOT EXISTS news_topic (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    news_id           TEXT NOT NULL,
    topic_id          TEXT NOT NULL,
    relevance_score   REAL CHECK (relevance_score >= 0 AND relevance_score <= 1),
    is_primary        INTEGER,
    FOREIGN KEY (news_id) REFERENCES news_item(news_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (topic_id) REFERENCES topic(topic_id) ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE (news_id, topic_id)
);

CREATE INDEX idx_nt_news ON news_topic(news_id);
CREATE INDEX idx_nt_topic ON news_topic(topic_id);
