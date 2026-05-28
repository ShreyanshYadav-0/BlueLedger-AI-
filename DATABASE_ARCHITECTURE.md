# DATABASE ARCHITECTURE

# AI Framework for Enterprise Financial Planning, Control & Risk Prediction

----------------------------------------------------------------

                    SQLITE DATABASE
                        database.db

----------------------------------------------------------------

1. USERS TABLE
----------------------------------------------------------------

Purpose:
- Store login credentials
- Manage role-based access

Fields:
- id
- username
- password
- role

Roles:
- Manager
- Accountant

----------------------------------------------------------------

2. EXPENSES TABLE
----------------------------------------------------------------

Purpose:
- Store enterprise financial transactions
- AI risk monitoring

Fields:
- id
- amount
- category
- risk_status
- created_at

Features:
- Historical transaction storage
- AI anomaly detection
- Financial monitoring

----------------------------------------------------------------

3. BUDGET TABLE
----------------------------------------------------------------

Purpose:
- Store enterprise budgeting information

Fields:
- id
- budget_amount

Features:
- Budget tracking
- Overspending monitoring
- Financial forecasting

----------------------------------------------------------------

4. LOGS TABLE
----------------------------------------------------------------

Purpose:
- Store enterprise activity logs

Fields:
- id
- activity
- timestamp

Features:
- Audit trail
- User monitoring
- Enterprise tracking

----------------------------------------------------------------

5. DEPARTMENTS TABLE
----------------------------------------------------------------

Purpose:
- Store enterprise department information

Fields:
- id
- department_name
- manager
- allocated_budget

Features:
- Department budgeting
- Manager assignment
- Enterprise financial structure

----------------------------------------------------------------

DATABASE FEATURES
----------------------------------------------------------------

- Historical Financial Data
- AI-ready Transaction Storage
- Enterprise Monitoring
- Role-Based Security
- Backup Support
- Audit Logging
- Scalable Architecture

----------------------------------------------------------------
                registered_users
-----------------------------------------------------------------

REGISTERED_USERS TABLE

Fields:
- id
- username
- password
- email
- role

Purpose:
- Store signup users
- Secure enterprise authentication
- Email verification support