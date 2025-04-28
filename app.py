import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from flask import Flask, render_template, jsonify
import os
import redis
import psycopg2

# Initialize Sentry
sentry_sdk.init(
    dsn="https://084ce62db49e2d7079dffaad70678df7@o4509192845131776.ingest.us.sentry.io/4509192903393280",
    integrations=[FlaskIntegration()],
    # Add data like request headers and IP for users,
    # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
    send_default_pii=True,
    traces_sample_rate=1.0,  # Capture 100% of transactions for monitoring
)

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this in production

@app.route('/')
def home():
    return "Hello World! Sentry test app is running."

# Test route for Sentry error tracking
@app.route('/debug-sentry')
def trigger_error():
    division_by_zero = 1 / 0
    return division_by_zero

@app.errorhandler(404)
def page_not_found(e):
    return "Page not found", 404

@app.errorhandler(500)
def server_error(e):
    return "Server error", 500

@app.route('/health', methods=['GET'])
def health_check():
    health_status = {
        "status": "healthy",
        "checks": {
            "postgres": {"status": "healthy"},
            "redis": {"status": "healthy"},
            "application": {"status": "healthy"}
        }
    }
    
    # Check PostgreSQL
    try:
        conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        cursor.close()
        conn.close()
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["postgres"] = {
            "status": "unhealthy",
            "error": str(e)
        }
    
    # Check Redis
    try:
        r = redis.from_url(os.environ.get('REDIS_URL'))
        r.ping()
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["redis"] = {
            "status": "unhealthy",
            "error": str(e)
        }
    
    status_code = 200 if health_status["status"] == "healthy" else 503
    return jsonify(health_status), status_code

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001) 