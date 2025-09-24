-- Ensure the centroid column exists in tbl_cbg
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = '2024' 
        AND table_name = 'tbl_cbg' 
        AND column_name = 'cbgcentroidgeom'
    ) THEN
        ALTER TABLE "2024".tbl_cbg ADD COLUMN cbgcentroidgeom geometry(Point, 102005);
    END IF;
END $$;

-- Populate cbgcentroidgeom with centroids of the CBG polygons
UPDATE "2024".tbl_cbg 
SET cbgcentroidgeom = ST_Centroid(cbgpolygeom);

-- Create a table to assign CBGs to schools strictly within buffer zones
CREATE TABLE "2024".tbl_cbgassignment1 AS
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
FROM "2024".tbl_cbg c
JOIN "2024".tbl_approvedschools s
ON ST_DWithin(
    ST_Transform(s.schoolgeom, 102005), 
    ST_Transform(c.cbgcentroidgeom, 102005), 
    s.buffer_distance * 1609.34 -- Convert miles to meters
);

-- Assign each CBG to the closest school within the buffer distance
CREATE TABLE "2024".tbl_cbgassignment AS
SELECT DISTINCT ON (a."GEOID")
    a."GEOID",
    a.cbgpolygeom,
    a.cbgcentroidgeom,
    a."UNIQUESCHOOLID",
    a.schoolgeom,
    a.buffer_distance,
    a.distance
FROM "2024".tbl_cbgassignment1 a
ORDER BY a."GEOID", a.distance;

-- Identify unassigned CBGs
CREATE TABLE "2024".tbl_cbg_notassigned AS
SELECT * 
FROM "2024".tbl_cbg 
WHERE "GEOID" NOT IN (SELECT "GEOID" FROM "2024".tbl_cbgassignment);

-- Ensure no unassigned CBGs remain
SELECT COUNT(*) AS unassigned_cbg_count FROM "2024".tbl_cbg_notassigned;

-- Assign unassigned CBGs to the closest school
CREATE TABLE "2024".tbl_cbg_notassigned_final AS
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
FROM "2024".tbl_cbg_notassigned c
CROSS JOIN "2024".tbl_approvedschools s
ORDER BY c."GEOID", distance;

-- Merge assigned CBGs and newly assigned CBGs into final table
CREATE TABLE "2024".tbl_cbg_finalassignment AS
SELECT * FROM "2024".tbl_cbgassignment
UNION ALL
SELECT * FROM "2024".tbl_cbg_notassigned_final;

-- Check if total assigned CBGs match the total CBGs
SELECT 
    (SELECT COUNT(*) FROM "2024".tbl_cbg_finalassignment) AS assigned_cbg_count,
    (SELECT COUNT(*) FROM "2024".tbl_cbg) AS total_cbg_count;

-- Verify that each school has at least one assigned block group
SELECT 
    "UNIQUESCHOOLID", COUNT(*) AS assigned_cbg_count 
FROM "2024".tbl_cbg_finalassignment
GROUP BY "UNIQUESCHOOLID"
ORDER BY assigned_cbg_count ASC;
