-- Create the buffer lookup table
CREATE TABLE IF NOT EXISTS "2024".tbl_bufferlookup (
    locale_type TEXT PRIMARY KEY,
    buffer_distance FLOAT
);

-- Insert buffer distances for each locale type
INSERT INTO "2024".tbl_bufferlookup (locale_type, buffer_distance)
VALUES
    ('City', 1),      
    ('Suburb', 3),     
    ('Town', 7),       
    ('Rural', 18)      
ON CONFLICT (locale_type) DO NOTHING;

-- Add buffer distance column to tbl_approvedschools
ALTER TABLE "2024".tbl_approvedschools ADD COLUMN IF NOT EXISTS buffer_distance FLOAT;

-- Assign buffer distances based on locale type
UPDATE "2024".tbl_approvedschools AS a
SET buffer_distance = b.buffer_distance
FROM "2024".tbl_bufferlookup AS b
WHERE a."Locale" = b.locale_type;
