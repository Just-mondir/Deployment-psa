# Use official Playwright image with Python support
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Avoids buffering logs so they appear instantly in Railway
ENV PYTHONUNBUFFERED=1

# Set workdir
WORKDIR /app

# Copy requirements first
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Expose port for Railway
EXPOSE 8080

# Run Flask
CMD ["python", "app.py"]
