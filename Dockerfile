# Base image: lightweight Python 3.11
FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /code

# Install system dependencies needed for psycopg2 (Postgres driver) to compile/run
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first (Docker layer caching trick — see explanation below)
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of the application code
COPY ./app ./app

# Expose the port uvicorn will run on
EXPOSE 8000

# Command to run when the container starts
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
