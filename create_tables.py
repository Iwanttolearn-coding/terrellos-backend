#!/usr/bin/env python3
"""
create_tables.py — One-time table creation for terrellos-backend
Creates all Pastor AI + HEE + logging tables in Supabase via direct postgres
"""
import os, sys
import psycopg2

db_url = os.environ.get("DATABASE_URL", "")
if not db_url:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

print(f"Connecting to Supabase postgres...")
conn = psycopg2.connect(db_url, connect_timeout=15)
conn.autocommit = True
cur = conn.cursor()
print("Connected OK")

TABLES = {
    "pastor_sermons": """
        CREATE TABLE IF NOT EXISTS pastor_sermons (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id TEXT NOT NULL,
            title TEXT,
            scripture TEXT,
            topic TEXT,
            tone TEXT DEFAULT 'balanced',
            denomination TEXT DEFAULT 'non-denominational',
            sermon_length TEXT DEFAULT 'medium',
            content TEXT NOT NULL,
            word_count INTEGER DEFAULT 0,
            output_type TEXT DEFAULT 'text',
            tags TEXT[] DEFAULT ARRAY[]::TEXT[],
            notes TEXT,
            generation_ms INTEGER,
            model TEXT DEFAULT 'gpt-4o',
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """,
    "idx_pastor_sermons_user": "CREATE INDEX IF NOT EXISTS idx_pastor_sermons_user ON pastor_sermons(user_id)",

    "pastor_bible_studies": """
        CREATE TABLE IF NOT EXISTS pastor_bible_studies (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id TEXT NOT NULL,
            title TEXT,
            book TEXT,
            passage TEXT,
            audience TEXT DEFAULT 'adults',
            version TEXT DEFAULT 'NIV',
            topic TEXT,
            content TEXT NOT NULL,
            word_count INTEGER DEFAULT 0,
            tags TEXT[] DEFAULT ARRAY[]::TEXT[],
            notes TEXT,
            generation_ms INTEGER,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """,
    "idx_pastor_bible_user": "CREATE INDEX IF NOT EXISTS idx_pastor_bible_user ON pastor_bible_studies(user_id)",

    "pastor_transcripts": """
        CREATE TABLE IF NOT EXISTS pastor_transcripts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id TEXT NOT NULL,
            session_id TEXT,
            transcript TEXT NOT NULL,
            audio_url TEXT,
            duration_sec FLOAT DEFAULT 0,
            source TEXT DEFAULT 'voice',
            language TEXT DEFAULT 'en',
            confidence FLOAT,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """,
    "idx_pastor_transcripts_user": "CREATE INDEX IF NOT EXISTS idx_pastor_transcripts_user ON pastor_transcripts(user_id)",

    "pastor_sessions": """
        CREATE TABLE IF NOT EXISTS pastor_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id TEXT NOT NULL,
            session_type TEXT DEFAULT 'general',
            started_at TIMESTAMPTZ DEFAULT now(),
            ended_at TIMESTAMPTZ,
            duration_sec FLOAT DEFAULT 0,
            actions_taken JSONB DEFAULT '[]'::JSONB,
            notes TEXT
        )
    """,

    "pastor_voice_recordings": """
        CREATE TABLE IF NOT EXISTS pastor_voice_recordings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id TEXT NOT NULL,
            transcript_id UUID,
            audio_url TEXT,
            storage_path TEXT,
            duration_sec FLOAT DEFAULT 0,
            file_size_bytes INTEGER DEFAULT 0,
            purpose TEXT DEFAULT 'transcription',
            processed BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """,
    "idx_pastor_voice_user": "CREATE INDEX IF NOT EXISTS idx_pastor_voice_user ON pastor_voice_recordings(user_id)",

    "pastor_generations": """
        CREATE TABLE IF NOT EXISTS pastor_generations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id TEXT NOT NULL,
            tool_type TEXT NOT NULL,
            title TEXT,
            content TEXT NOT NULL,
            input_data JSONB DEFAULT '{}'::JSONB,
            word_count INTEGER DEFAULT 0,
            generation_ms INTEGER,
            model TEXT DEFAULT 'gpt-4o',
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """,
    "idx_pastor_gen_user": "CREATE INDEX IF NOT EXISTS idx_pastor_gen_user ON pastor_generations(user_id)",
    "idx_pastor_gen_type": "CREATE INDEX IF NOT EXISTS idx_pastor_gen_type ON pastor_generations(tool_type)",

    "system_logs": """
        CREATE TABLE IF NOT EXISTS system_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            app TEXT NOT NULL,
            level TEXT DEFAULT 'info',
            event TEXT NOT NULL,
            detail TEXT,
            user_id TEXT,
            duration_ms INTEGER,
            status_code INTEGER,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """,
    "idx_system_logs_app": "CREATE INDEX IF NOT EXISTS idx_system_logs_app ON system_logs(app, created_at DESC)",

    "generation_logs": """
        CREATE TABLE IF NOT EXISTS generation_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            app TEXT NOT NULL,
            user_id TEXT,
            tool_type TEXT NOT NULL,
            prompt_summary TEXT,
            status TEXT DEFAULT 'success',
            error_message TEXT,
            duration_ms INTEGER,
            model TEXT DEFAULT 'gpt-4o',
            tokens_used INTEGER,
            saved_id TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """,
    "idx_gen_logs_app": "CREATE INDEX IF NOT EXISTS idx_gen_logs_app ON generation_logs(app, status, created_at DESC)",

    "voice_logs": """
        CREATE TABLE IF NOT EXISTS voice_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            app TEXT NOT NULL,
            user_id TEXT,
            action TEXT NOT NULL,
            provider TEXT,
            duration_sec FLOAT,
            status TEXT DEFAULT 'success',
            error_message TEXT,
            file_size_bytes INTEGER,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """,

    "clone_logs": """
        CREATE TABLE IF NOT EXISTS clone_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            app TEXT NOT NULL,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            elevenlabs_voice_id TEXT,
            recordings_count INTEGER,
            total_seconds FLOAT,
            status TEXT DEFAULT 'success',
            error_message TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """,

    "payment_logs": """
        CREATE TABLE IF NOT EXISTS payment_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            app TEXT NOT NULL,
            user_id TEXT,
            provider TEXT DEFAULT 'paypal',
            event_type TEXT NOT NULL,
            amount FLOAT,
            currency TEXT DEFAULT 'USD',
            order_id TEXT,
            status TEXT DEFAULT 'success',
            error_message TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """,

    "hee_recordings": """
        CREATE TABLE IF NOT EXISTS hee_recordings (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            profile_id TEXT,
            question_index INTEGER,
            question_text TEXT,
            category TEXT DEFAULT 'general',
            audio_url TEXT,
            transcript TEXT,
            duration_sec FLOAT DEFAULT 0,
            file_size_bytes INTEGER DEFAULT 0,
            storage_path TEXT,
            upload_success BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """,
    "idx_hee_rec_user": "CREATE INDEX IF NOT EXISTS idx_hee_rec_user ON hee_recordings(user_id)",

    "hee_voice_clones": """
        CREATE TABLE IF NOT EXISTS hee_voice_clones (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
            user_id TEXT UNIQUE NOT NULL,
            profile_id TEXT,
            status TEXT DEFAULT 'not_started',
            elevenlabs_voice_id TEXT,
            voice_name TEXT,
            recording_count INTEGER DEFAULT 0,
            total_seconds FLOAT DEFAULT 0,
            last_error TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """,
    "idx_hee_vc_user": "CREATE INDEX IF NOT EXISTS idx_hee_vc_user ON hee_voice_clones(user_id)",
}

results = {}
for name, sql in TABLES.items():
    try:
        cur.execute(sql)
        results[name] = "OK"
        print(f"  ✅ {name}")
    except Exception as e:
        results[name] = f"FAIL: {e}"
        print(f"  ❌ {name}: {e}")

cur.close()
conn.close()

ok = sum(1 for v in results.values() if v == "OK")
fail = sum(1 for v in results.values() if "FAIL" in v)
print(f"\nDONE: {ok} OK, {fail} FAILED")
