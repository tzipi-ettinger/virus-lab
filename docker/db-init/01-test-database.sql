-- pytest wipes and rebuilds this database on every run (tests/conftest.py), so the
-- tests never touch the development data in virus_lab.
CREATE DATABASE virus_lab_test;
