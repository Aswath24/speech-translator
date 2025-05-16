FROM python:3.10-slim

# Install ffmpeg and other system dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg git && \
    apt-get clean

# Set working directory
WORKDIR /app

# Copy files
COPY . /app

# Install Python dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Expose port
ENV PORT=5000
EXPOSE $PORT

# Start the Flask app with gunicorn
CMD ["gunicorn", "main:app", "--bind", "0.0.0.0:$PORT"]
