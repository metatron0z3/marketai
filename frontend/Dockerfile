# Stage 1: Builder
FROM node:20-alpine as builder

WORKDIR /app

# Copy package.json and package-lock.json
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy the rest of the application code
COPY . .

# Build the Angular application for production

RUN npm run build -- --configuration production

# Stage 2: Production
FROM nginx:stable-alpine as production

# Copy the built Angular application from the builder stage
COPY --from=builder /app/dist/marketai-app/browser /usr/share/nginx/html

# Copy the custom Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose the Nginx port
EXPOSE 80