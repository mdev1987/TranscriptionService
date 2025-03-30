# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Install system dependencies, including ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose any ports if needed (not necessary for the bot)
CMD ["python", "bot.py"]
