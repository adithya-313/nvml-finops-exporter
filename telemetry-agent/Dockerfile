# Stage 1: Build the Go binary for linux/amd64
FROM golang:alpine AS builder

WORKDIR /build

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /build/telemetry-agent .

# Stage 2: Minimal runtime image
FROM alpine:latest

RUN apk add --no-cache ca-certificates

COPY --from=builder /build/telemetry-agent /usr/local/bin/telemetry-agent

EXPOSE 8080

ENTRYPOINT ["telemetry-agent"]
