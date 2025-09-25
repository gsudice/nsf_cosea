-- Extract numeric portion of district ID
ALTER TABLE "2024".ncesdata2024 ADD COLUMN IF NOT EXISTS district_id_clean TEXT;
UPDATE "2024".ncesdata2024
SET district_id_clean = SPLIT_PART("State District ID", '-', 2);

ALTER TABLE "2024".tbl_approvedschools ADD COLUMN IF NOT EXISTS "Locale Code" INT;

-- Join the Locale Code from `ncesdata2024` into `tbl_approvedschools`
UPDATE "2024".tbl_approvedschools AS a
SET "Locale Code" = n."Locale Code"
FROM "2024".ncesdata2024 AS n
WHERE a."SYSTEM_ID" = n.district_id_clean::INTEGER;
ALTER TABLE "2024".tbl_approvedschools ADD COLUMN IF NOT EXISTS "Locale" TEXT;

-- Normalize the `Locale` column based on `Locale Code`
UPDATE "2024".tbl_approvedschools
SET "Locale" = 
    CASE 
        WHEN "Locale Code" BETWEEN 11 AND 19 THEN 'City'
        WHEN "Locale Code" BETWEEN 21 AND 29 THEN 'Suburb'
        WHEN "Locale Code" BETWEEN 31 AND 39 THEN 'Town'
        WHEN "Locale Code" BETWEEN 41 AND 49 THEN 'Rural'
        ELSE 'Unknown'
    END;
