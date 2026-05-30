package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"time"

	"telemetry-agent/internal/gpu"
)

// globalState holds the result of the last metrics collection so it
// can be served on every GET /metrics request without re-acquiring
// the NVML library lock every time.
var globalState gpu.SystemStatus

func main() {
	// Immediately attempt to collect GPU metrics.  If NVML is not
	// available the global state will be set to "degraded" with a
	// descriptive error message.
	globalState = gpu.CollectGpuMetrics()

	// Register the single HTTP endpoint of this agent.
	http.HandleFunc("/metrics", metricsHandler)

	// Configure the HTTP server with explicit timeouts so that a
	// stuck connection does not hang indefinitely.
	server := &http.Server{
		Addr:         ":8080",
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 5 * time.Second,
	}

	fmt.Println("telemetry-agent listening on :8080")
	log.Fatal(server.ListenAndServe())
}

// metricsHandler is the HTTP handler for GET /metrics.  It marshals
// the latest globalState to JSON and writes the response.
func metricsHandler(responseWriter http.ResponseWriter, request *http.Request) {
	// Serialize the global state to indented JSON for readability.
	jsonPayload, marshalError := json.MarshalIndent(globalState, "", "  ")
	if marshalError != nil {
		http.Error(responseWriter, "internal server error", http.StatusInternalServerError)
		return
	}

	// Set the Content-Type header so clients know the body is JSON.
	responseWriter.Header().Set("Content-Type", "application/json")
	responseWriter.WriteHeader(http.StatusOK)

	// Write the JSON payload to the response body.
	_, writeError := responseWriter.Write(jsonPayload)
	if writeError != nil {
		fmt.Printf("error writing response: %v\n", writeError)
	}
}
