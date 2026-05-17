# Dockerfile for Go Streaming Service

# --- Build Stage ---
FROM golang:1.19-alpine AS builder

# Set the Current Working Directory inside the container
WORKDIR /app

# Copy go mod file

COPY go.mod ./

# Copy the source code

COPY . .

# Generate go.sum and download dependencies

RUN go mod tidy

RUN go mod download

# Build the Go app

# -ldflags="-w -s" reduces the size of the executable by stripping debugging info

RUN CGO_ENABLED=0 GOOS=linux go build -a -ldflags="-w -s" -o marketai-streaming .

# --- Deploy Stage ---
FROM alpine:latest

WORKDIR /root/

# Copy the Pre-built binary file from the previous stage
COPY --from=builder /app/marketai-streaming .

# Expose port 8082 to the outside world
EXPOSE 8082

# Command to run the executable
CMD ["./marketai-streaming"]
