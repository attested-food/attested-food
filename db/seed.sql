INSERT INTO sources (type, name, url, accreditation, description) VALUES
    ('lab', 'Equinox Labs', 'https://www.equinoxlab.com', 'NABL TC-6820', 'Food testing lab, Navi Mumbai'),
    ('lab', 'Eurofins', 'https://www.eurofins.in', NULL, 'Global testing lab group'),
    ('lab', 'ALS', 'https://www.alsglobal.com', NULL, 'Global testing lab group'),
    ('website', 'Unbox Health', 'https://www.unboxhealth.in', NULL, 'Lab-tested ratings (A+ to D) for Indian packaged food and supplements'),
    ('website', 'Trustified', 'https://www.trustified.in', NULL, 'Pass/fail batch testing of Indian protein and supplement brands'),
    ('website', 'Labdoor', 'https://labdoor.com', NULL, 'US supplement grading, includes some Indian protein brands'),
    ('website', 'Consumer Voice', 'https://consumer-voice.org', NULL, 'Indian comparative lab tests of food brands, published as PDFs')
ON CONFLICT (name) DO NOTHING;

WITH p AS (
    INSERT INTO products (brand, name, variant, category, net_quantity, image_url)
    VALUES ('Kellogg''s', 'Millet Muesli', 'Choco', 'breakfast_cereal', '400 g', 'https://m.media-amazon.com/images/I/61p7toAa1gL._SL500_.jpg')
    RETURNING id
), r AS (
    INSERT INTO reports (product_id, kind, lab_id, report_number, ulr_number, batch_no, mfg_date, expiry_date, tested_on, issued_on, verification, verified)
    SELECT p.id, 'user', (SELECT id FROM sources WHERE name = 'Equinox Labs'),
           'EQNX:001:NL:26:10:09217', 'TC682026000108177F', 'S6A280526',
           '2026-05-28', '2027-02-22', '2026-11-03', '2026-11-05', 'none', false
    FROM p
    RETURNING id
)
INSERT INTO results (report_id, parameter, "group", unit, value, value_raw, method)
SELECT r.id, v.parameter, 'nutrition', v.unit, v.value, v.value_raw, v.method
FROM r, (VALUES
    ('Added Sugars', 'g/100g', 14.87, '14.87', 'SOP-CHM-139-00'),
    ('Carbohydrate', 'g/100g', 79.89, '79.89', 'SOP-CHM-28-00'),
    ('Dietary Fibre', 'g/100g', 8.01, '8.01', 'AOAC 985.29'),
    ('Energy', 'kcal/100g', 384.84, '384.84', 'SOP-CHM-29-00'),
    ('Protein', 'g/100g', 8.31, '8.31', 'SOP-CHM-137-00'),
    ('Total Fat', 'g/100g', 3.56, '3.56', 'SOP-CHM-100-01'),
    ('Total Sugars', 'g/100g', 21.03, '21.03', 'SOP-CHM-123-00'),
    ('Cholesterol', 'mg/100g', NULL, '<1.0', 'AOAC 994.10'),
    ('Sodium', 'mg/100g', 282.83, '282.83', 'SOP-CHM-27-02'),
    ('Saturated Fat', 'g/100g', 0.66, '0.66', 'AOAC 996.06'),
    ('Unsaturated Fat', 'g/100g', 2.90, '2.90', 'AOAC 996.06'),
    ('Trans Fat', 'g/100g', NULL, '<0.10', 'AOAC 996.06'),
    ('MUFA', 'g/100g', 1.19, '1.19', 'AOAC 996.06'),
    ('PUFA', 'g/100g', 1.17, '1.17', 'AOAC 996.06')
) AS v(parameter, unit, value, value_raw, method);
