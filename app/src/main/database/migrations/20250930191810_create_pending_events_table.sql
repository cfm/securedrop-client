-- migrate:up
CREATE TABLE pending_events (
    snowflake_id INTEGER PRIMARY KEY,

    -- only one of source_uuid OR item_uuid is set
    source_uuid INTEGER REFERENCES sources(uuid),
    item_uuid INTEGER REFERENCES items(uuid),

    type INTEGER NOT NULL,

    -- only set for AddReply event
    reply_text text,
    reply_source_uuid text
);

ALTER TABLE sources
ADD COLUMN is_starred text generated always as (json_extract (data, '$.is_starred'));

CREATE VIEW sources_projected AS 
SELECT 
    sources.uuid,
    sources.data,
    sources.version,
    sources.has_attachment,
    sources.show_message_preview,
    sources.message_preview,
    -- project Seen event
    CASE 
        WHEN EXISTS (
            SELECT 1 
            FROM pending_events
            WHERE pending_events.source_uuid = sources.uuid 
            -- type: Seen
            AND pending_events.type = 7
        )
        THEN 1 
        ELSE sources.is_seen
    END AS is_seen,
    -- project Star/Unstar event 
    CASE 
        WHEN EXISTS (
            SELECT 1 
            FROM pending_events 
            WHERE pending_events.source_uuid = sources.uuid 
            -- type: Star 
            AND pending_events.type = 5
        ) THEN 1
        WHEN EXISTS (
            SELECT 1 
            FROM pending_events 
            WHERE pending_events.source_uuid = sources.uuid 
            -- type: Unstar 
            AND pending_events.type = 6
        ) THEN 0 
        ELSE sources.is_starred
    END AS is_starred
FROM sources
-- project DeleteSource event 
WHERE NOT EXISTS (
    SELECT 1 
    FROM pending_events 
    WHERE pending_events.source_uuid = sources.uuid 
    -- type: DeleteSource
    AND pending_events.type = 3
);

CREATE VIEW items_projected AS 
SELECT
    items.uuid,
    items.data,
    items.version,
    items.plaintext,
    items.filename,
    items.kind,
    items.is_read,
    items.last_updated,
    items.source_uuid,
    items.fetch_progress,
    items.fetch_status,
    items.fetch_last_updated_at,
    items.fetch_retry_attempts
FROM items 
-- project DeleteReply event
WHERE NOT EXISTS (
    SELECT 1 
    FROM pending_events 
    WHERE pending_events.item_uuid = items.uuid 
    -- type: DeleteReply 
    AND pending_events.type = 2
)
-- project DeleteSource, DeleteSourceConversation event
AND NOT EXISTS (
    SELECT 1 
    FROM pending_events 
    WHERE pending_events.source_uuid = items.source_uuid 
    -- type: DeleteSource, DeleteSourceConversation
    AND pending_events.type IN (3, 4) 
)
-- project AddReply event 
UNION ALL 
SELECT 
    pending_events.item_uuid AS uuid,
    -- TODO(vicki): will we need to populate metadata?
    NULL as data,
    NULL as version,
    pending_events.reply_text AS plaintext,
    NULL as filename,
    'reply' AS kind,
    NULL as is_read,
    NULL as last_updated,
    pending_events.source_uuid AS source_uuid,
    NULL as fetch_progress,
    NULL as fetch_status,
    NULL as fetch_last_updated_at,
    NULL as fetch_retry_attempts
FROM pending_events 
-- type: AddReply
WHERE pending_events.type = 1;

-- migrate:down
DROP VIEW IF EXISTS items_projected;
DROP VIEW IF EXISTS sources_projected;
ALTER TABLE sources DROP COLUMN is_starred;
DROP TABLE IF EXISTS pending_events;
