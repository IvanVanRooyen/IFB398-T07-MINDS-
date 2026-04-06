FROM golang:tip-alpine AS build

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /ollama-exporter .

FROM alpine:latest

RUN apk --no-cache add ca-certificates \
    && addgroup -S exporter \
    && adduser -S exporter -G exporter

USER exporter

COPY --from=build /ollama-exporter /usr/local/bin/ollama-exporter

ENTRYPOINT ["ollama-exporter"]

