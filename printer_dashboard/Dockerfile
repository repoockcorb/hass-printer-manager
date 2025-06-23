FROM alpine:3.18

# Install required packages
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-flask \
    py3-requests \
    nginx \
    curl \
    jq \
    bash

# Install Python packages that aren't available in Alpine repos
COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt && \
    pip3 list | grep -E "(flask|gunicorn|eventlet)" && \
    which gunicorn || echo "Gunicorn not found in PATH"

# Create app directory
RUN mkdir -p /app

# Copy application files
COPY app/ /app/
COPY nginx.conf /etc/nginx/nginx.conf
COPY run.sh /
RUN chmod a+x /run.sh

# Create nginx directories
RUN mkdir -p /var/log/nginx /var/lib/nginx/tmp /etc/nginx/conf.d

# Expose port
EXPOSE 5000

# Run the service
CMD ["/run.sh"] 