-- Question #1
-- Assuming that the data stored in `skill_name` 
-- in the `user_skill` table might be repeated 
-- for different users, what changes would you make 
-- to the database to normalize the `skill_name` 
-- and reduce repeated storage? 
-- Show the structure of the new table(s).

-- Two New Tables...
-- skill (new table)
-- ├── skill_id (PK)
-- └── skill_name (UNIQUE)

-- user_skill (modified)
-- ├── user_skill_id (PK)
-- ├── user_id (FK → user)
-- ├── skill_id (FK → skill)  ← replaces skill_name
-- ├── skill_level
-- ├── skill_usage
-- ├── skill_last_used
-- ├── user_skill_endorsed
-- ├── user_skill_last_modified
-- └── user_skill_date_created

-- Here is the DDL for the modified tables:

CREATE TABLE skill (
    skill_id INT(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
    skill_name VARCHAR(255) NOT NULL UNIQUE,
    date_created DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE user_skill (
    user_skill_id INT(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id INT(11) NOT NULL,
    skill_id INT(11) NOT NULL,
    skill_level VARCHAR(255),
    skill_usage VARCHAR(255),
    skill_last_used VARCHAR(255),
    user_skill_endorsed TINYINT(1) DEFAULT 0,
    user_skill_last_modified TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    user_skill_date_created DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign keys
    CONSTRAINT fk_user_skill_user FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_skill_skill FOREIGN KEY (skill_id) REFERENCES skill(skill_id) ON DELETE CASCADE,
    
    -- Composite unique constraint to prevent duplicate skill entries per user
    UNIQUE KEY uk_user_skill (user_id, skill_id),
    
    -- Indexes for common queries
    INDEX idx_user_id (user_id),
    INDEX idx_skill_id (skill_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Question #2
-- Recreate the query that returned 
-- the 10 rows of data supplied. 
-- Speculate on tables that would 
-- be needed that are not shown here.

SELECT 
    u.user_firstname,
    u.user_lastname,
    s.skill_name
FROM users u
JOIN user_skills us ON us.user_id = u.user_id
JOIN skills s ON s.skill_id = us.skill_id
WHERE u.user_firstname = 'Kim'
  AND u.user_lastname = 'Simpson'
ORDER BY us.id  

-- Speculated Tables:

CREATE TABLE users (
    user_id       INT PRIMARY KEY AUTO_INCREMENT,
    user_firstname VARCHAR(100),
    user_lastname  VARCHAR(100),
    email          VARCHAR(255),
    created_at     DATETIME
);

CREATE TABLE skills (
    skill_id   INT PRIMARY KEY AUTO_INCREMENT,
    skill_name VARCHAR(100) NOT NULL
);

-- Bridge table. 
CREATE TABLE user_skills (
    id         INT PRIMARY KEY AUTO_INCREMENT,
    user_id    INT NOT NULL,
    skill_id   INT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (skill_id) REFERENCES skills(skill_id)
);

-- Question #3
-- Given the following query, 
-- list possible ways it could be optimized? 
-- List all assumptions:

-- Original Query  
SELECT c.* 
FROM companies AS c 
JOIN users AS u USING(companyid) 
JOIN jobs AS j USING(userid) 
JOIN useraccounts AS ua USING(userid) 
WHERE j.jobid = 123;


-- 1. CONVERT TO USE ON INSTEAD OF USING
-- =============================================================================
SELECT c.* 
FROM companies AS c 
JOIN users AS u ON c.companyid = u.companyid 
JOIN jobs AS j ON u.userid = j.userid 
JOIN useraccounts AS ua ON u.userid = ua.userid 
WHERE j.jobid = 123;


-- 2. REORDER JOINS - START FROM JOBS TABLE FIRST
-- =============================================================================
SELECT c.* 
FROM jobs AS j 
INNER JOIN users AS u ON j.userid = u.userid 
INNER JOIN companies AS c ON u.companyid = c.companyid 
JOIN useraccounts AS ua ON u.userid = ua.userid 
WHERE j.jobid = 123;


-- 3. CREATE INDEXES (EXCLUDING useraccounts)
-- =============================================================================
-- Most critical: filter column
CREATE INDEX idx_jobs_jobid ON jobs(jobid);

-- Join columns
CREATE INDEX idx_jobs_userid ON jobs(userid);
CREATE INDEX idx_users_userid ON users(userid);
CREATE INDEX idx_users_companyid ON users(companyid);

-- Composite indexes for better performance
CREATE INDEX idx_jobs_jobid_userid ON jobs(jobid, userid);
CREATE INDEX idx_users_userid_companyid ON users(userid, companyid);


-- 4. ADD DISTINCT TO PREVENT DUPLICATES
-- =============================================================================
SELECT DISTINCT c.* 
FROM jobs AS j 
INNER JOIN users AS u ON j.userid = u.userid 
INNER JOIN companies AS c ON u.companyid = c.companyid 
JOIN useraccounts AS ua ON u.userid = ua.userid 
WHERE j.jobid = 123;

-- 5. SELECT SPECIFIC COLULMS
-- =============================================================================
SELECT DISTINCT c.name, c.city, c.domain -- etc 
FROM jobs AS j 
INNER JOIN users AS u ON j.userid = u.userid 
INNER JOIN companies AS c ON u.companyid = c.companyid 
JOIN useraccounts AS ua ON u.userid = ua.userid 
WHERE j.jobid = 123;

-- 6. DROP USERACCOUNTS FROM QUERY IF NOT USED
-- =============================================================================
SELECT DISTINCT c.name, c.city, c.domain -- etc 
FROM jobs AS j 
INNER JOIN users AS u ON j.userid = u.userid 
INNER JOIN companies AS c ON u.companyid = c.companyid 
WHERE j.jobid = 123;

-- ============================================================================
-- BONUS: ALL OPTIMIZATIONS COMBINED (RECOMMENDED)
-- ============================================================================
-- This combines all four changes above plus removes unused useraccounts table
SELECT DISTINCT c.name, c.city, c.domain 
FROM jobs AS j 
INNER JOIN users AS u ON j.userid = u.userid 
INNER JOIN companies AS c ON u.companyid = c.companyid 
WHERE j.jobid = 123;

-- Supporting indexes:
CREATE INDEX idx_jobs_jobid ON jobs(jobid);
CREATE INDEX idx_jobs_jobid_userid ON jobs(jobid, userid);
CREATE INDEX idx_users_userid_companyid ON users(userid, companyid);

-- Key Assumptions:

-- Foreign key relationships exist and are properly defined
-- Each jobid maps to exactly one company (no cross-joins)
-- The useraccounts table is truly unused in the output
-- Normalized schema with reasonable cardinality

