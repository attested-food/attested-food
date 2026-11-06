CREATE TABLE IF NOT EXISTS products (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    brand         text NOT NULL,
    name          text NOT NULL,
    variant       text,
    category      text NOT NULL,
    manufacturer  text,
    fssai_license text,
    barcode       text,
    net_quantity  text,
    image_url     text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sources (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    type          text NOT NULL CHECK (type IN ('lab', 'website')),
    name          text NOT NULL UNIQUE,
    url           text,
    accreditation text,
    description   text
);

CREATE TABLE IF NOT EXISTS reports (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id         uuid NOT NULL REFERENCES products(id),
    kind               text NOT NULL CHECK (kind IN ('user', 'fallback')),
    lab_id             uuid REFERENCES sources(id),
    publisher_id       uuid REFERENCES sources(id),
    source_url         text UNIQUE,
    report_number      text,
    ulr_number         text,
    batch_no           text,
    mfg_date           date,
    expiry_date        date,
    tested_on          date,
    issued_on          date,
    verdict            text CHECK (verdict IN ('pass', 'fail', 'grade')),
    grade              text,
    pdf_url            text,
    pdf_sha256         text,
    verification       text NOT NULL DEFAULT 'none' CHECK (verification IN ('zk_email', 'zk_tls', 'signature', 'none')),
    verified           boolean NOT NULL DEFAULT false,
    chain_tx           text,
    fetched_at         timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS results (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id   uuid NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    parameter   text NOT NULL,
    "group"     text NOT NULL CHECK ("group" IN ('nutrition', 'heavy_metal', 'toxin', 'pesticide', 'spiking', 'other')),
    unit        text,
    value       numeric,
    value_raw   text NOT NULL,
    label_claim numeric,
    "limit"     numeric,
    detection_limit numeric,
    method      text,
    status      text CHECK (status IN ('pass', 'fail'))
);

CREATE INDEX IF NOT EXISTS reports_product_idx ON reports(product_id);
CREATE INDEX IF NOT EXISTS results_report_idx ON results(report_id);
CREATE INDEX IF NOT EXISTS products_search_idx ON products USING gin (to_tsvector('simple', brand || ' ' || name || ' ' || coalesce(variant, '')));

CREATE TABLE IF NOT EXISTS test_requests (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    brand         text NOT NULL,
    name          text NOT NULL,
    variant       text,
    category      text NOT NULL,
    net_quantity  text,
    manufacturer  text,
    fssai_license text,
    barcode       text,
    buy_url       text,
    asin          text UNIQUE,
    image_url     text,
    image         bytea,
    image_type    text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    CHECK ((image_url IS NULL) <> (image IS NULL))
);

-- Pack label data (per 100 g) and ingredient list, used for label-vs-lab notes.
ALTER TABLE products ADD COLUMN IF NOT EXISTS ingredients text;
ALTER TABLE products ADD COLUMN IF NOT EXISTS ingredients_source text;
ALTER TABLE products ADD COLUMN IF NOT EXISTS label_nutrition jsonb;
ALTER TABLE products ADD COLUMN IF NOT EXISTS off_code text;
