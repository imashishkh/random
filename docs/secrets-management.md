# Secrets Management Guide

This guide explains how to securely manage environment variables and secrets across different deployment environments for the FX-Swarm application.

## Table of Contents
- [Environment Files](#environment-files)
- [Development Environment](#development-environment)
- [Staging Environment](#staging-environment)
- [Production Environment](#production-environment)
- [Docker Secrets](#docker-secrets)
- [Secret Rotation](#secret-rotation)
- [Security Best Practices](#security-best-practices)

## Environment Files

The project uses different environment files for different deployment scenarios:

- `.env.development` - Settings for local development
- `.env.staging` - Settings for testing environments
- `.env.production` - Settings for production environments (with Docker secrets)
- `.env-example` - Template with documentation for all required variables

To set up your environment:

1. Choose the appropriate environment file for your deployment
2. Copy it to `.env` in the project root directory
3. Update any sensitive values with secure credentials

Example:
```bash
cp .env.development .env
# Edit .env with your specific settings
```

**IMPORTANT: Never commit `.env` files to version control**

## Development Environment

In development, secrets are stored directly in the `.env.development` file for simplicity:

```bash
# Example development workflow
cp .env.development .env
docker-compose up -d
```

- Environment variables are loaded from the `.env` file automatically
- The included `docker-compose.override.yml` adds development-specific settings
- Sensitive values should still use strong passwords, even in development

## Staging Environment

Staging uses a similar approach to development but with more secure credentials:

```bash
# Example staging workflow
cp .env.staging .env
docker-compose up -d
```

- Staging credentials should be different from development
- If possible, use a separate development machine/server for staging
- Staging should mirror production configuration as closely as possible

## Production Environment

Production uses Docker secrets for sensitive information:

```bash
# Example production workflow
cp .env.production .env
# Ensure all secrets files are populated with secure values
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

- Sensitive values are stored in Docker secrets instead of environment variables
- Environment variables are used for non-sensitive configuration
- Docker secrets are mounted into containers as files rather than environment variables

## Docker Secrets

Docker secrets are files mounted into containers at runtime. For FX-Swarm, they are stored in the `docker/secrets/` directory:

- `postgres_password.txt` - PostgreSQL admin password
- `redis_password.txt` - Redis password
- `airflow_fernet_key.txt` - Airflow Fernet key for database encryption
- `airflow_password.txt` - Airflow database password
- `grafana_admin_password.txt` - Grafana admin password
- `grafana_db_password.txt` - Grafana database password

To create or update a secret:

```bash
echo "your_secure_password" > docker/secrets/postgres_password.txt
```

**IMPORTANT: Keep these files secure and never commit them to version control**

### Generating Secure Passwords

Use a secure method to generate strong passwords:

```bash
# Generate a random 32-character password
openssl rand -base64 24

# Generate an Airflow Fernet key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Secret Rotation

Regularly rotating credentials is a security best practice:

1. Create new secret files with updated credentials
2. Update relevant `.env` file(s) if needed
3. Restart the services with the new secrets:
   ```bash
   docker-compose -f docker-compose.yml -f docker-compose.prod.yml down
   docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
   ```

For database passwords, remember to update the database users as well:

```bash
# Example: Updating PostgreSQL password
docker exec -it fx-swarm-postgres psql -U postgres
postgres=# ALTER USER postgres WITH PASSWORD 'new_secure_password';
postgres=# ALTER USER airflow WITH PASSWORD 'new_airflow_password';
postgres=# ALTER USER grafana_reader WITH PASSWORD 'new_grafana_password';
```

## Security Best Practices

1. **Never commit secrets to version control**
   - Ensure `.env*` is in your `.gitignore`
   - Ensure `docker/secrets/` is in your `.gitignore`

2. **Use strong, unique passwords for each service**
   - At least 16 characters
   - Mix of letters, numbers, and special characters
   - Different for each service and environment

3. **Limit access to environment files and secret files**
   - Restrict file permissions (`chmod 600 .env`)
   - Limit who has access to production servers

4. **Rotate secrets regularly**
   - Every 90 days for normal operation
   - Immediately if a breach is suspected
   - When team members with access leave the project

5. **Use principle of least privilege**
   - Database users should only have the permissions they need
   - Create read-only users when possible (like Grafana's database user)

6. **Monitor for unauthorized access**
   - Check logs regularly for suspicious activity
   - Set up alerts for failed login attempts

7. **Keep software updated**
   - Regularly update all services to the latest secure versions
   - Apply security patches promptly 