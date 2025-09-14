import os
import sqlite3


def do_migration(conf):
    db_path = os.path.join(conf.data_dir, "lbrynet.sqlite")
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    cursor.executescript("""
        -- Correct announce flag on head blobs
        update blob set should_announce=0
        where should_announce=1 and 
        blob.blob_hash in (select stream_blob.blob_hash from stream_blob where position=0);

        -- Performance indexes for hot paths
        create index if not exists support_claim_id_idx on support(claim_id);
        create index if not exists claim_claim_id_idx on claim(claim_id);
        create index if not exists content_claim_bt_infohash_idx on content_claim(bt_infohash);
        create index if not exists blob_next_announce_status_idx on blob(next_announce_time, status);
        create index if not exists blob_should_announce_idx on blob(should_announce);
        create index if not exists blob_single_announce_idx on blob(single_announce);
    """)

    connection.commit()
    connection.close()
