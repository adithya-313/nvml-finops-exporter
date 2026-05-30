# Stage 1: Build
FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
# Disable CGO for static binary, build for Linux
RUN CGO_ENABLED=0 GOOS=linux go build -o telemetry-agent .

# Stage 2: Run
FROM alpine:latest
WORKDIR /root/
COPY --from=builder /app/telemetry-agent .
EXPOSE 8080
CMD ["./telemetry-agent"]
