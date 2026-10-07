-- Set Up Auto-Classification on a Database
-- Attaches a classification profile to a database for automatic monitoring

-- Parameters:
--   <database>: Database to monitor
--   <profile_database>: Database where profile is stored
--   <profile_schema>: Schema where profile is stored
--   <profile_name>: Name of the classification profile

-- Enable auto-classification
ALTER DATABASE <database> 
    SET CLASSIFICATION_PROFILE = '<profile_database>.<profile_schema>.<profile_name>';

-- Verify the setting
SHOW PARAMETERS LIKE 'CLASSIFICATION_PROFILE' IN DATABASE <database>;

-- To disable auto-classification:
-- ALTER DATABASE <database> UNSET CLASSIFICATION_PROFILE;

-- Note: Auto-classification runs in the background.
-- Results typically appear within a few hours for new tables.

