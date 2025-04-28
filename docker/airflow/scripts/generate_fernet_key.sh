#!/bin/bash
# Script to generate a Fernet key for Airflow encryption

set -e

echo "Generating a Fernet key for Airflow..."
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
echo "Add this key to your .env file as AIRFLOW_FERNET_KEY" 