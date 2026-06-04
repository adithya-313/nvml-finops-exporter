# Stage 1: Build
FROM golang:alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o telemetry-agent .

# Stage 2: Run
FROM alpine:latest
WORKDIR /root/
COPY --from=builder /app/telemetry-agent .
CMD ["./telemetry-agent"]
