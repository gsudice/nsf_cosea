-- Make a copy of contact list from 2024 schema
select * into allhsgrades24.ga_school_contact_list from "2024".ga_school_contact_list;

-- Select count of schools in ga_school_contact_list
select count(*) from "allhsgrades24".ga_school_contact_list; -- 2298

-- Add UNIQUESCHOOLID to fte2024-1_enroll-demog_sch if not exists
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'allhsgrades24' 
        AND table_name = 'fte2024-1_enroll-demog_sch' 
        AND column_name = 'UNIQUESCHOOLID'
    ) THEN
        ALTER TABLE "allhsgrades24"."fte2024-1_enroll-demog_sch" 
        ADD COLUMN "UNIQUESCHOOLID" TEXT;
    END IF;
END $$;

UPDATE "allhsgrades24"."fte2024-1_enroll-demog_sch";
SET "UNIQUESCHOOLID" = LPAD("SYSTEM_ID"::TEXT, 4, '0') || LPAD("SCHOOL_ID"::TEXT, 4, '0');

-- This section has been added. Note that filtered_schools now contains all schools where the GRADE_RANGE includes high school grades (9-12).

-- count checks
select count(*) from "allhsgrades24"."fte2024-1_enroll-demog_sch"; -- 2232
select count(*) from "allhsgrades24"."fte2024-1_enroll-demog_sch"
    where "GRADE_RANGE" like '%-9%' or "GRADE_RANGE" like '%-10%' or "GRADE_RANGE" like '%-11%' or "GRADE_RANGE" like '%-12%'; -- 514

select * into allhsgrades24.filtered_schools from "allhsgrades24"."fte2024-1_enroll-demog_sch"
    where "GRADE_RANGE" like '%-9%' or "GRADE_RANGE" like '%-10%' or "GRADE_RANGE" like '%-11%' or "GRADE_RANGE" like '%-12%'
    order by "GRADE_RANGE"

-- Count of filtered_schools
select count(*) from "allhsgrades24".filtered_schools; -- Count is 514

-- Drop and recreate alternative_schools
DROP TABLE IF EXISTS "allhsgrades24".alternative_schools;
CREATE TABLE "allhsgrades24".alternative_schools AS
SELECT * 
FROM "allhsgrades24".filtered_schools
WHERE "SCHOOL_NAME" ILIKE ANY (ARRAY[
    '%Academy%', '%STEM%', '%Charter%', '%State Schools%', '%Virtual%', '%Institute%', 
    '%Foundry%', '%Transition%', '%Center%', '%Online%', '%Intervention%', '%S.T.E.M.%', 
    '%Treatment%', '%Youth%', '%Home%', '%Ministries%', '%Chance%', 
    '%Career%', '%Arts%', '%E-Learning%', '%Humanities%', '%ITU%', 'Margaret Harris Comprehensive School' -- removed %Comprehensive% and added Margret. 
])
OR "SYSTEM_NAME" ILIKE ANY (ARRAY[
    '%charter%', '%state%', '%academy%', '%justice%', '%department%' -- added justice and department
]);

-- Remove alternative_schools from filtered_schools
DELETE FROM "allhsgrades24".filtered_schools
    WHERE "UNIQUESCHOOLID" IN (SELECT "UNIQUESCHOOLID" FROM "allhsgrades24".alternative_schools); -- 120 removed

-- Drop and recreate tbl_approvedschools
DROP TABLE IF EXISTS "allhsgrades24".tbl_approvedschools;
CREATE TABLE "allhsgrades24".tbl_approvedschools AS
SELECT fs.*, 
       gsc."School Address",
       gsc."School City", 
       gsc."State",
       gsc."lat",
       gsc."lon"
FROM "allhsgrades24".filtered_schools fs
LEFT JOIN "allhsgrades24".ga_school_contact_list gsc
ON fs."UNIQUESCHOOLID" = gsc."UNIQUESCHOOLID";

-- Add geometry column if not exists and populate it
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'allhsgrades24'
          AND table_name = 'tbl_approvedschools'
          AND column_name = 'schoolgeom'
    ) THEN
        ALTER TABLE "allhsgrades24".tbl_approvedschools ADD COLUMN schoolgeom geometry(Point, 102005);
    END IF;
END $$;

UPDATE "allhsgrades24".tbl_approvedschools 
    SET schoolgeom = ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4269), 102005);

-- Count check
select count(*) from "allhsgrades24".tbl_approvedschools; -- 394 after removing comprehensive schools from the alternative schools criteria

-- Count checks
-- Total Start: 2322
-- Only keeping -09 -10 -11 -12: 514
-- Alternate schools: 120 (after comprehensive school removal)
-- Remove alternate schools: 394 (tbl_approvedschools)

-- Bring in ncesdata2024 data table from 2024 schema
select * into allhsgrades24.ncesdata2024 from "2024".ncesdata2024

-- Add local code and locale columns to tbl_approvedschools
ALTER TABLE "allhsgrades24".tbl_approvedschools ADD COLUMN IF NOT EXISTS "Locale Code" INT;

-- Join the Locale Code from `ncesdata2024` into `tbl_approvedschools`
UPDATE "allhsgrades24".tbl_approvedschools AS a
SET "Locale Code" = n."Locale Code"
FROM "allhsgrades24".ncesdata2024 AS n
WHERE a."SYSTEM_ID" = n.district_id_clean::INTEGER;

ALTER TABLE "allhsgrades24".tbl_approvedschools ADD COLUMN IF NOT EXISTS "Locale" TEXT;

-- Normalize the `Locale` column based on `Locale Code`
UPDATE "allhsgrades24".tbl_approvedschools
SET "Locale" = 
    CASE 
        WHEN "Locale Code" BETWEEN 11 AND 19 THEN 'City'
        WHEN "Locale Code" BETWEEN 21 AND 29 THEN 'Suburb'
        WHEN "Locale Code" BETWEEN 31 AND 39 THEN 'Town'
        WHEN "Locale Code" BETWEEN 41 AND 49 THEN 'Rural'
        ELSE 'Unknown'
    END;


-- define buffers
DROP TABLE IF EXISTS "allhsgrades24".tbl_bufferlookup;
-- Create the buffer lookup table
CREATE TABLE IF NOT EXISTS "allhsgrades24".tbl_bufferlookup (
    locale_type TEXT PRIMARY KEY,
    buffer_distance FLOAT
);

-- Insert buffer distances for each locale type
INSERT INTO "allhsgrades24".tbl_bufferlookup (locale_type, buffer_distance)
VALUES
    ('City', 2),   -- originally 1 mile, now 2 miles
    ('Suburb', 4.5), -- originally 3 miles, now 4.5 miles
    ('Town', 8),   -- originally 7 miles, now 8 miles
    ('Rural', 20)  -- originally 18 miles, now 20 miles   
ON CONFLICT (locale_type) DO NOTHING;

-- Check the buffer lookup table
select * from "allhsgrades24".tbl_bufferlookup;

-- Add buffer distance column to tbl_approvedschools
ALTER TABLE "allhsgrades24".tbl_approvedschools ADD COLUMN IF NOT EXISTS buffer_distance FLOAT;

-- Assign buffer distances based on locale type
UPDATE "allhsgrades24".tbl_approvedschools AS a
SET buffer_distance = b.buffer_distance
FROM "allhsgrades24".tbl_bufferlookup AS b
WHERE a."Locale" = b.locale_type;

--- check
select * from allhsgrades24.tbl_approvedschools limit 10;

-- Create attendance zones
-- make a copy of tbl_cbg
SELECT * into allhsgrades24.tbl_cbg FROM "2024".tbl_cbg

-- Ensure the centroid column exists in tbl_cbg
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'allhsgrades24' 
        AND table_name = 'tbl_cbg' 
        AND column_name = 'cbgcentroidgeom'
    ) THEN
        ALTER TABLE "allhsgrades24".tbl_cbg ADD COLUMN cbgcentroidgeom geometry(Point, 102005);
    END IF;
END $$;

-- Populate cbgcentroidgeom with centroids of the CBG polygons
UPDATE "allhsgrades24".tbl_cbg 
SET cbgcentroidgeom = ST_Centroid(cbgpolygeom);

-- Create a table to assign CBGs to schools strictly within buffer zones
DROP TABLE IF EXISTS "allhsgrades24".tbl_cbgassignment1;
CREATE TABLE "allhsgrades24".tbl_cbgassignment1 AS
SELECT 
    c."GEOID",
    c.cbgpolygeom,
    c.cbgcentroidgeom,
    s."UNIQUESCHOOLID",
    s.schoolgeom,
    s.buffer_distance,
    ST_Distance(
        ST_Transform(c.cbgcentroidgeom, 102005), 
        ST_Transform(s.schoolgeom, 102005)
    ) AS distance
FROM "allhsgrades24".tbl_cbg c
JOIN "allhsgrades24".tbl_approvedschools s
ON ST_DWithin(
    ST_Transform(s.schoolgeom, 102005), 
    ST_Transform(c.cbgcentroidgeom, 102005), 
    s.buffer_distance * 1609.34 -- Convert miles to meters
); -- 31954 CBGs assigned to schools within buffer zones

-- Creating a table to visualize the buffer zones around schools
DROP TABLE IF EXISTS "allhsgrades24".buffervisual;
select "UNIQUESCHOOLID", schoolgeom, st_buffer(schoolgeom, buffer_distance * 1609.34) into allhsgrades24.buffervisual from "allhsgrades24".tbl_cbgassignment1 ;

-- Assign each CBG to the closest school within the buffer distance
DROP TABLE IF EXISTS "allhsgrades24".tbl_cbgassignment;
CREATE TABLE "allhsgrades24".tbl_cbgassignment AS
SELECT DISTINCT ON (a."GEOID")
    a."GEOID",
    a.cbgpolygeom,
    a.cbgcentroidgeom,
    a."UNIQUESCHOOLID",
    a.schoolgeom,
    a.buffer_distance,
    a.distance
FROM "allhsgrades24".tbl_cbgassignment1 a
ORDER BY a."GEOID", a.distance; -- 7237 assigned CBGs

-- Identify unassigned CBGs
DROP TABLE IF EXISTS "allhsgrades24".tbl_cbg_notassigned;
CREATE TABLE "allhsgrades24".tbl_cbg_notassigned AS
SELECT * 
FROM "allhsgrades24".tbl_cbg 
WHERE "GEOID" NOT IN (SELECT "GEOID" FROM "allhsgrades24".tbl_cbgassignment); 

-- Ensure no unassigned CBGs remain
SELECT COUNT(*) AS unassigned_cbg_count FROM "allhsgrades24".tbl_cbg_notassigned; -- 209 unassigned BGs

-- Assign unassigned CBGs to the closest school
DROP TABLE IF EXISTS "allhsgrades24".tbl_cbg_notassigned_final;
CREATE TABLE "allhsgrades24".tbl_cbg_notassigned_final AS
SELECT DISTINCT ON (c."GEOID") 
    c."GEOID",
    c.cbgpolygeom,
    c.cbgcentroidgeom,
    s."UNIQUESCHOOLID",
    s.schoolgeom,
    s.buffer_distance,
    ST_Distance(
        ST_Transform(c.cbgcentroidgeom, 102005),
        ST_Transform(s.schoolgeom, 102005)
    ) AS distance
FROM "allhsgrades24".tbl_cbg_notassigned c
CROSS JOIN "allhsgrades24".tbl_approvedschools s
ORDER BY c."GEOID", distance;

-- Merge assigned CBGs and newly assigned CBGs into final table
DROP TABLE IF EXISTS "allhsgrades24".tbl_cbg_finalassignment;
CREATE TABLE "allhsgrades24".tbl_cbg_finalassignment AS
SELECT * FROM "allhsgrades24".tbl_cbgassignment
UNION ALL
SELECT * FROM "allhsgrades24".tbl_cbg_notassigned_final;

-- Check if total assigned CBGs match the total CBGs
SELECT 
    (SELECT COUNT(*) FROM "allhsgrades24".tbl_cbg_finalassignment) AS assigned_cbg_count,
    (SELECT COUNT(*) FROM "allhsgrades24".tbl_cbg) AS total_cbg_count;

-- Verify that each school has at least one assigned block group
SELECT 
    "UNIQUESCHOOLID", COUNT(*) AS assigned_cbg_count 
FROM "allhsgrades24".tbl_cbg_finalassignment
GROUP BY "UNIQUESCHOOLID"
ORDER BY assigned_cbg_count ASC;

-- Run Python code to compute the gadoe2024_389 table

-- Calculate Gap Score
alter table census.gadoe2024_389 add "ri_gap" float;
-- OLD: update census.gadoe2024_389 set "ri_gap" = (GREATEST("RI_Asian", "RI_Black", "RI_Hispanic", "RI_White")-LEAST("RI_Asian", "RI_Black", "RI_Hispanic", "RI_White"))/2;
UPDATE census.gadoe2024_389
SET "ri_gap" = CASE
    WHEN "CS_Enrollment" = 0 THEN NULL
    ELSE (GREATEST("RI_Asian", "RI_Black", "RI_Hispanic", "RI_White") - LEAST("RI_Asian", "RI_Black", "RI_Hispanic", "RI_White")) / 2
END;

-- Check Gap Score
select "ri_gap", count(*) from census.gadoe2024_389 group by "ri_gap" order by "ri_gap";

