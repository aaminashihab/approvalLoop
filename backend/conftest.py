import os

# Automatically configure test environment for pytest runs
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("MODEL_ARMOR_ENABLED", "false")
