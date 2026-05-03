from django.contrib.postgres.search import SearchVectorField
from django.db import migrations


class Migration(migrations.Migration):
    atomic = False  # required for CREATE INDEX CONCURRENTLY

    dependencies = [
        ('core', '0012_document_search_tsv'),
    ]

    operations = [
        # 1. Add the column (initially NULL for all existing rows)
        migrations.AddField(
            model_name='document',
            name='search_tsv',
            field=SearchVectorField(blank=True, null=True),
        ),

        # 2. Create the PL/pgSQL trigger function
        migrations.RunSQL(
            sql="""
                CREATE OR REPLACE FUNCTION core_document_tsv_update()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    NEW.search_tsv :=
                        setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
                        setweight(to_tsvector('english', coalesce(NEW.extracted_text, '')), 'B');
                    RETURN NEW;
                END;
                $$;

                DROP TRIGGER IF EXISTS core_document_tsv_trigger ON core_document;

                CREATE TRIGGER core_document_tsv_trigger
                BEFORE INSERT OR UPDATE ON core_document
                FOR EACH ROW EXECUTE FUNCTION core_document_tsv_update();
            """,
            reverse_sql="""
                DROP TRIGGER IF EXISTS core_document_tsv_trigger ON core_document;
                DROP FUNCTION IF EXISTS core_document_tsv_update();
            """,
        ),

        # 3. Create GIN index on the new column for fast full-text lookups
        migrations.RunSQL(
            sql="""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS core_document_search_tsv_gin
                ON core_document USING GIN(search_tsv);
            """,
            reverse_sql="DROP INDEX IF EXISTS core_document_search_tsv_gin;",
        ),

        # 4. Backfill existing rows so the column is not NULL after migration
        migrations.RunSQL(
            sql="""
                UPDATE core_document
                SET search_tsv =
                    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
                    setweight(to_tsvector('english', coalesce(extracted_text, '')), 'B');
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
