# Environment Setup Guide

## Quick Start

After cloning the repository with T3 enhancements, follow these steps:

### 1. Create Your Local Environment File

```powershell
# Copy the example file to create your local .env
Copy-Item env.example .env
```

### 2. Update Values for Your Environment

Open `.env` in your editor and update these values:

```bash
# Update database connection
DATABASE_URL=postgresql+asyncpg://YOUR_USER:YOUR_PASSWORD@YOUR_HOST:5432/YOUR_DATABASE

# If using Redis for durable audit logging, uncomment and update:
# REDIS_URL=redis://YOUR_REDIS_HOST:6379/0

# Adjust feature flags as needed
FEATURES_T3_AUDIT=true
FEATURES_T3_COSTS=true
FEATURES_T3_GDPR=true

# Tune batch sizes if needed (defaults are production-ready)
AUDIT_BATCH_SIZE=50
AUDIT_FLUSH_INTERVAL_MS=1000
```

### 3. Environment-Specific Configurations

#### Local Development
```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ledgerlift_dev
AUDIT_DURABLE_MODE=memory
```

#### Staging
```bash
DATABASE_URL=postgresql+asyncpg://user:pass@staging-db.example.com:5432/ledgerlift_staging
AUDIT_DURABLE_MODE=redis
REDIS_URL=redis://staging-redis.example.com:6379/0
```

#### Production
```bash
DATABASE_URL=postgresql+asyncpg://user:pass@prod-db.example.com:5432/ledgerlift_prod
AUDIT_DURABLE_MODE=redis
REDIS_URL=redis://prod-redis.example.com:6379/0
AUDIT_BATCH_SIZE=100
MAX_JOB_COST_CENTS=50000
```

## Security Best Practices

### ✅ DO:
- Keep `.env` in your `.gitignore`
- Use `env.example` to document required variables
- Use different credentials for each environment
- Store production secrets in a secure vault (AWS Secrets Manager, Azure Key Vault, etc.)

### ❌ DON'T:
- Never commit `.env` to Git
- Never share `.env` files via email or chat
- Never hardcode secrets in Python/TypeScript files
- Never use production credentials in development

## Verification

After setting up your `.env` file, verify it's working:

```powershell
# Test configuration loading
cd apps/api
python -c "from app.config_t3 import settings; print(f'Audit enabled: {settings.features_t3_audit}')"
```

Expected output:
```
Audit enabled: True
```

## Troubleshooting

### Error: "DATABASE_URL is not set"
- Ensure you've copied `env.example` to `.env`
- Verify `.env` is in the project root directory
- Check that variable names match exactly (no typos)

### Error: "Cannot connect to database"
- Verify your database is running
- Check connection string format
- Test connection manually: `psql postgresql://user:pass@host:5432/dbname`

### Error: "Cannot connect to Redis"
- If using `AUDIT_DURABLE_MODE=redis`, ensure Redis is running
- Or switch to `AUDIT_DURABLE_MODE=memory` for development

## Next Steps

After environment setup:
1. Install dependencies: `pip install -r requirements.txt`
2. Run migrations: `alembic upgrade head`
3. Start the API: `uvicorn app.main:app --reload`
4. Run tests: `pytest tests/`

See `T3_README.md` for complete integration instructions.
