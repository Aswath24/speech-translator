FROM python:3.10-slim

# Install system packages
RUN apt-get update && apt-get install -y ffmpeg git && apt-get clean

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install Python packages
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Expose the port (not strictly required by Render, but good practice)
ENV PORT=5000
EXPOSE $PORT

# Start the app using shell form for environment expansion
CMD gunicorn main:app --bind 0.0.0.0:${PORT:-5000}
