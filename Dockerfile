# Use an official Python runtime as a base image
FROM python:3.11-slim

# Set environment variables for unbuffered Python output and no bytecode generation
ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1

# Set the working directory inside the container
WORKDIR /app
    
# # Install system dependencies required for psycopg2 (PostgreSQL adapter for Python)
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# install dependencies
RUN pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install -r requirements.txt

# Copy the entire Django project into the container
COPY . .

# Expose the port your Django app will run on (default is 8000)
EXPOSE 8000

# Command to run the Django development server
# Consider using Gunicorn/Nginx for production
CMD ["gunicorn", "be.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
