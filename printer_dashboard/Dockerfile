FROM alpine:3.18

# Install required packages
RUN apk add --no-cache \
    python3 \
    py3-pip \
    nginx \
    curl \
    jq \
    bash \
    gcc \
    musl-dev \
    python3-dev

# Create app directory
RUN mkdir -p /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt /app/

# Install Python requirements
RUN pip3 install --no-cache-dir -r /app/requirements.txt

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