package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"time"

	"telemetry-agent/internal/gpu"
)

func main() {
	// Register the HTTP endpoints.
	http.HandleFunc("/api/v1/status", jsonStatusHandler)
	http.HandleFunc("/metrics", prometheusMetricsHandler)

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

// getCurrentMetrics collects a fresh snapshot of GPU telemetry.
// Each call produces a new set of randomised values so that entropy
// is visible across sequential requests.
func getCurrentMetrics() gpu.SystemStatus {
	return gpu.CollectGpuMetrics()
}

// jsonStatusHandler is the HTTP handler for GET /api/v1/status.  It
// returns a fresh JSON status payload with every request.
func jsonStatusHandler(responseWriter http.ResponseWriter, request *http.Request) {
	currentState := getCurrentMetrics()

	jsonPayload, marshalError := json.MarshalIndent(currentState, "", "  ")
	if marshalError != nil {
		http.Error(responseWriter, "internal server error", http.StatusInternalServerError)
		return
	}

	responseWriter.Header().Set("Content-Type", "application/json")
	responseWriter.WriteHeader(http.StatusOK)

	_, writeError := responseWriter.Write(jsonPayload)
	if writeError != nil {
		fmt.Printf("error writing response: %v\n", writeError)
	}
}

// prometheusMetricsHandler is the HTTP handler for GET /metrics.  It
// collects fresh GPU telemetry and writes it in Prometheus exposition
// format so that a Prometheus server can scrape it directly.
func prometheusMetricsHandler(responseWriter http.ResponseWriter, request *http.Request) {
	currentState := getCurrentMetrics()

	responseWriter.Header().Set("Content-Type", "text/plain; version=0.0.4")
	responseWriter.WriteHeader(http.StatusOK)

	systemHealth := 0
	if currentState.SystemStatus == "healthy" {
		systemHealth = 1
	}

	textOutput := fmt.Sprintf("# HELP gpu_system_health System health (1=healthy, 0=degraded)\n")
	textOutput += fmt.Sprintf("# TYPE gpu_system_health gauge\n")
	textOutput += fmt.Sprintf("gpu_system_health %d\n", systemHealth)

	for _, gpuMetric := range currentState.Gpus {
		uuidLabel := gpuMetric.Uuid

		textOutput += fmt.Sprintf("\n# HELP gpu_utilization_percent GPU Engine Utilization\n")
		textOutput += fmt.Sprintf("# TYPE gpu_utilization_percent gauge\n")
		textOutput += fmt.Sprintf("gpu_utilization_percent{uuid=\"%s\"} %d\n", uuidLabel, gpuMetric.UtilizationPercent)

		textOutput += fmt.Sprintf("# HELP gpu_memory_used_mb GPU Memory Used\n")
		textOutput += fmt.Sprintf("# TYPE gpu_memory_used_mb gauge\n")
		textOutput += fmt.Sprintf("gpu_memory_used_mb{uuid=\"%s\"} %d\n", uuidLabel, gpuMetric.MemoryUsedMb)

		textOutput += fmt.Sprintf("# HELP gpu_memory_total_mb GPU Memory Total\n")
		textOutput += fmt.Sprintf("# TYPE gpu_memory_total_mb gauge\n")
		textOutput += fmt.Sprintf("gpu_memory_total_mb{uuid=\"%s\"} %d\n", uuidLabel, gpuMetric.MemoryTotalMb)

		textOutput += fmt.Sprintf("# HELP gpu_temperature_c GPU Temperature\n")
		textOutput += fmt.Sprintf("# TYPE gpu_temperature_c gauge\n")
		textOutput += fmt.Sprintf("gpu_temperature_c{uuid=\"%s\"} %d\n", uuidLabel, gpuMetric.TemperatureC)

		textOutput += fmt.Sprintf("# HELP gpu_power_draw_w GPU Power Draw\n")
		textOutput += fmt.Sprintf("# TYPE gpu_power_draw_w gauge\n")
		textOutput += fmt.Sprintf("gpu_power_draw_w{uuid=\"%s\"} %g\n", uuidLabel, gpuMetric.PowerDrawW)
	}

	_, writeError := fmt.Fprint(responseWriter, textOutput)
	if writeError != nil {
		fmt.Printf("error writing response: %v\n", writeError)
	}
}
