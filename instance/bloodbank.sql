-- STEP 1: Create Database
CREATE DATABASE IF NOT EXISTS blood_donation_db;
USE blood_donation_db;

-- --- CRITICAL: DROP TABLES TO ALLOW RE-CREATION WITH NEW SCHEMA ---
DROP TABLE IF EXISTS AdminLogin;
DROP TABLE IF EXISTS BloodStock;
DROP TABLE IF EXISTS Donation;
DROP TABLE IF EXISTS BloodRequest;
DROP TABLE IF EXISTS Recipient;
DROP TABLE IF EXISTS Donor;
-- ------------------------------------------------------------------

-- STEP 2: Create Tables (Modified to include Password, Weight, Diseases, Hospital, Reason)

-- Donor Table (Added Password, Weight, ChronicDiseases for eligibility and login)
CREATE TABLE Donor (
    DonorID INT AUTO_INCREMENT PRIMARY KEY,
    Name VARCHAR(100) NOT NULL,
    Age INT CHECK (Age >= 18 AND Age <= 65),
    Gender ENUM('Male', 'Female', 'Other'),
    BloodGroup ENUM('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-') NOT NULL,
    ContactNumber VARCHAR(15),
    Email VARCHAR(100) UNIQUE NOT NULL, -- Added UNIQUE/NOT NULL
    Password VARCHAR(255) NOT NULL, -- CRITICAL: Added Password for login
    Address TEXT,
    Weight DECIMAL(5, 2) DEFAULT 70.0, -- Added Weight for eligibility check (Default 70kg)
    ChronicDiseases VARCHAR(255) DEFAULT 'None', -- Added for eligibility check
    LastDonationDate DATE
);

-- Recipient Table (Added Password for login)
CREATE TABLE Recipient (
    RecipientID INT AUTO_INCREMENT PRIMARY KEY,
    Name VARCHAR(100) NOT NULL,
    Age INT,
    Gender ENUM('Male', 'Female', 'Other'),
    BloodGroup ENUM('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-') NOT NULL,
    ContactNumber VARCHAR(15),
    Email VARCHAR(100) UNIQUE NOT NULL, -- Added UNIQUE/NOT NULL
    Password VARCHAR(255) NOT NULL, -- CRITICAL: Added Password for login
    Address TEXT,
    RequestDate DATE NOT NULL DEFAULT (CURDATE())
);


-- BloodRequest Table (Added Hospital and Reason for recipient form data)
CREATE TABLE BloodRequest (
    RequestID INT AUTO_INCREMENT PRIMARY KEY,
    RecipientID INT,
    BloodGroup ENUM('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'),
    RequiredUnits INT NOT NULL,
    Hospital VARCHAR(255) NOT NULL, -- CRITICAL: Added Hospital
    Reason TEXT, -- CRITICAL: Added Reason
    RequestStatus ENUM('Pending', 'Approved', 'Rejected', 'Completed') DEFAULT 'Pending',
    MatchedDonorID INT DEFAULT NULL,
    FOREIGN KEY (RecipientID) REFERENCES Recipient(RecipientID) ON DELETE CASCADE,
    FOREIGN KEY (MatchedDonorID) REFERENCES Donor(DonorID) ON DELETE SET NULL
);

-- Donation Table (No changes needed)
CREATE TABLE Donation (
    DonationID INT AUTO_INCREMENT PRIMARY KEY,
    DonorID INT,
    DonationDate DATE NOT NULL DEFAULT (CURDATE()),
    UnitsDonated INT NOT NULL,
    DonationCenter VARCHAR(100),
    FOREIGN KEY (DonorID) REFERENCES Donor(DonorID) ON DELETE CASCADE
);

-- BloodStock Table (No changes needed)
CREATE TABLE BloodStock (
    BloodGroup ENUM('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-') PRIMARY KEY,
    AvailableUnits INT DEFAULT 0
);

-- AdminLogin Table (No changes needed)
CREATE TABLE AdminLogin (
    AdminID INT AUTO_INCREMENT PRIMARY KEY,
    Username VARCHAR(50) UNIQUE NOT NULL,
    Password VARCHAR(255) NOT NULL  -- Note: Should be hashed in real apps
);


-- STEP 3: Insert Initial Blood Stock Records
INSERT INTO BloodStock (BloodGroup, AvailableUnits) VALUES
('A+', 0), ('A-', 0), ('B+', 0), ('B-', 0),
('AB+', 0), ('AB-', 0), ('O+', 0), ('O-', 0);

-- STEP 4: Insert Sample Donors (Added Password, Weight, and ChronicDiseases)
INSERT INTO Donor (Name, Age, Gender, BloodGroup, ContactNumber, Email, Password, Address, Weight, ChronicDiseases, LastDonationDate) VALUES
('Ravi Kumar', 30, 'Male', 'O+', '9876543210', 'ravi@example.com', 'ravipass', 'Pune, MH', 75.5, 'None', '2025-03-20'),
('Neha Sharma', 25, 'Female', 'A+', '9876512345', 'neha@example.com', 'nehapass', 'Mumbai, MH', 62.0, 'None', '2025-05-15'),
('Amit Joshi', 35, 'Male', 'B-', '9876523456', 'amit@example.com', 'amitpass', 'Nagpur, MH', 48.0, 'None', '2025-01-05'); -- Amit is ineligible due to low weight (48kg)

-- STEP 5: Insert Sample Recipients (Added Password)
INSERT INTO Recipient (Name, Age, Gender, BloodGroup, ContactNumber, Email, Password, Address)
VALUES 
('Anita Deshmukh', 28, 'Female', 'O+', '9000012345', 'anita@example.com', 'anitapass', 'Nashik, MH'),
('Rahul Mehra', 45, 'Male', 'B-', '9000023456', 'rahul@example.com', 'rahulpass', 'Kolhapur, MH');

-- STEP 6: Insert Blood Requests (Added Hospital and Reason)
INSERT INTO BloodRequest (RecipientID, BloodGroup, RequiredUnits, Hospital, Reason, RequestStatus, MatchedDonorID) VALUES
(1, 'O+', 500, 'Ruby Hall Clinic', 'Emergency Transfusion for Trauma', 'Approved', 1),
(2, 'B-', 300, 'City General Hospital', 'Scheduled Surgery', 'Pending', NULL);

-- STEP 7: Insert Donations (No changes needed)
INSERT INTO Donation (DonorID, DonationDate, UnitsDonated, DonationCenter)
VALUES 
(1, '2025-07-01', 500, 'Ruby Hall Pune'),
(2, '2025-06-10', 450, 'KEM Mumbai');

-- STEP 8: Update BloodStock with Donations (No changes needed)
-- Note: These updates must run *after* the initial inserts if the database is reset.
UPDATE BloodStock SET AvailableUnits = AvailableUnits + 500 WHERE BloodGroup = 'O+';
UPDATE BloodStock SET AvailableUnits = AvailableUnits + 450 WHERE BloodGroup = 'A+';

-- STEP 9: Insert Admin Users (No changes needed)
INSERT INTO AdminLogin (Username, Password) VALUES
('admin1', 'admin@123'), -- For demo; use hashed passwords in production
('admin2', 'securepass');

-- Final Check
SELECT * FROM BloodStock;

-- Add the RequestDate column to the BloodRequest table
ALTER TABLE BloodRequest
ADD COLUMN RequestDate DATE NOT NULL DEFAULT (CURDATE()) AFTER Reason;