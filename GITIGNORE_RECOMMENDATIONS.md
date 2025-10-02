# Recommended .gitignore Additions for T3 Enhancements

# Add these lines to your project's .gitignore file to protect sensitive data
# and keep your repository clean

# ============================================================
# Environment Variables (CRITICAL - Prevents exposing secrets)
# ============================================================
.env
.env.local
.env.*.local

# Keep env.example (safe to commit - renamed from .env.example to avoid hidden file issues)
!env.example
!.env.example

# ============================================================
# Python Cache and Build Files
# ============================================================
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# ============================================================
# Virtual Environments
# ============================================================
venv/
env/
ENV/
.venv

# ============================================================
# Node.js / Netlify Functions
# ============================================================
node_modules/
netlify/functions/node_modules/
.netlify/

# ============================================================
# Database
# ============================================================
*.db
*.sqlite
*.sqlite3

# ============================================================
# IDEs and Editors
# ============================================================
.vscode/
.idea/
*.swp
*.swo
*~
.DS_Store

# ============================================================
# Test Coverage
# ============================================================
.coverage
htmlcov/
.pytest_cache/

# ============================================================
# Logs
# ============================================================
*.log
logs/

# ============================================================
# Helper Scripts (Optional - Not needed in repo)
# ============================================================
create-t3-files.ps1
VERIFY_FILES.ps1

# ============================================================
# Alembic (Keep migrations, ignore runtime files)
# ============================================================
# migrations/ - KEEP THIS, migrations should be committed
*.pyc

# ============================================================
# Redis Dump Files
# ============================================================
dump.rdb

# ============================================================
# MinIO / S3 Local Storage
# ============================================================
.minio/
storage/
