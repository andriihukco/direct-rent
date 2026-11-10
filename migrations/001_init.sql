CREATE TABLE users (
    tg_id       bigint PRIMARY KEY,
    username    text,
    paused      boolean NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE filters (
    id             bigserial PRIMARY KEY,
    user_id        bigint NOT NULL UNIQUE REFERENCES users(tg_id) ON DELETE CASCADE,
    districts      text[] NOT NULL DEFAULT '{}',
    price_min      int,
    price_max      int,
    rooms          int[] NOT NULL DEFAULT '{}',
    pets_required  boolean NOT NULL DEFAULT false,
    updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE objects (
    id             bigserial PRIMARY KEY,
    first_seen_at  timestamptz NOT NULL DEFAULT now(),
    photo_hash     bigint
);

CREATE TABLE listings (
    id              bigserial PRIMARY KEY,
    source          text NOT NULL,
    source_id       text NOT NULL,
    url             text NOT NULL,
    object_id       bigint REFERENCES objects(id) ON DELETE CASCADE,
    text            text NOT NULL,
    channel_title   text NOT NULL DEFAULT '',
    price_uah       int,
    price_raw       text,
    rooms           int,
    district        text,
    street          text,
    pets            text NOT NULL CHECK (pets IN ('yes', 'no', 'unknown')),
    posted_at       timestamptz NOT NULL,
    ingested_at     timestamptz NOT NULL DEFAULT now(),
    verdict         text NOT NULL CHECK (verdict IN ('pass', 'pass_unverified', 'reject')),
    verdict_stage   text NOT NULL CHECK (verdict_stage IN ('reputation', 'rules', 'llm')),
    verdict_reason  text NOT NULL,
    llm_confidence  real,
    photo_url       text,
    photo_bytes     bytea,
    tg_file_id      text,
    photo_hash      bigint,
    raw_contacts    jsonb NOT NULL DEFAULT '[]',
    UNIQUE (source, source_id)
);
CREATE INDEX listings_ingested_at ON listings (ingested_at);
CREATE INDEX listings_object_id ON listings (object_id);

CREATE TABLE contacts (
    id           bigserial PRIMARY KEY,
    kind         text NOT NULL CHECK (kind IN ('phone', 'tg_user_id', 'tg_username', 'olx_user_id')),
    value        text NOT NULL,
    blacklisted  boolean NOT NULL DEFAULT false,
    UNIQUE (kind, value)
);

CREATE TABLE listing_contacts (
    listing_id  bigint NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    contact_id  bigint NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    PRIMARY KEY (listing_id, contact_id)
);
CREATE INDEX listing_contacts_contact ON listing_contacts (contact_id);

CREATE TABLE complaints (
    user_id     bigint NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    object_id   bigint NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, object_id)
);

CREATE TABLE deliveries (
    user_id       bigint NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    object_id     bigint NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    delivered_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, object_id)
);

CREATE TABLE outbox (
    id           bigserial PRIMARY KEY,
    user_id      bigint NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    listing_id   bigint NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    status       text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sending', 'sent', 'failed')),
    attempts     int NOT NULL DEFAULT 0,
    next_try_at  timestamptz NOT NULL DEFAULT now(),
    claimed_at   timestamptz,
    sent_at      timestamptz,
    last_error   text,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX outbox_status_next ON outbox (status, next_try_at);

CREATE TABLE source_state (
    source  text NOT NULL,
    key     text NOT NULL,
    value   text NOT NULL,
    PRIMARY KEY (source, key)
);
