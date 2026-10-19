-- Run this ONCE as the MySQL root user (MySQL Workbench or the mysql command line).
-- It creates the empty database and a user for the app.
CREATE DATABASE IF NOT EXISTS concerttix CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'concerttix'@'localhost' IDENTIFIED BY 'concerttix123';
GRANT ALL PRIVILEGES ON concerttix.* TO 'concerttix'@'localhost';
FLUSH PRIVILEGES;
