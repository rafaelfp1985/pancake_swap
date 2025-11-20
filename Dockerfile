# Dockerfile
# Use a slim Python base image
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Copy the dependency file and install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the application code
COPY pancake_swap_cloud.py .

# Copy other files that are needed
COPY abi.json .
COPY erc_20_abi.json .

# Command to run your script when the container starts
# The '-u' flag is important to unbuffer stdout/stderr in Python
CMD ["python", "-u", "pancake_swap_cloud.py"]