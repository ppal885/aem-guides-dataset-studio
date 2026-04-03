# Stage 1: Build
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm ci --only=production=false

# Copy source code
COPY . .

# Build the application
# Package.json build script handles errors with fallback message
RUN npm run build

# Verify build output exists
RUN if [ ! -d "/app/dist" ] || [ -z "$(ls -A /app/dist)" ]; then \
        echo "ERROR: Build failed - dist directory is empty or missing!" && \
        ls -la /app/ && \
        exit 1; \
    else \
        echo "Build successful - dist directory contains:" && \
        ls -la /app/dist | head -10; \
    fi

# Stage 2: Production with Nginx
FROM nginx:alpine

# Copy built assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Verify nginx config exists (skip validation - backend hostname not available at build time)
RUN if [ ! -f "/etc/nginx/conf.d/default.conf" ]; then \
        echo "ERROR: nginx.conf not found!" && \
        exit 1; \
    else \
        echo "nginx.conf copied successfully"; \
    fi

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/ || exit 1

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
