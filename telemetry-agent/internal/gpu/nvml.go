package gpu

import (
	"time"
)

// GpuMetric represents a snapshot of a single GPU's telemetry data.
type GpuMetric struct {
	Uuid               string  `json:"uuid"`
	Name               string  `json:"name"`
	UtilizationPercent uint    `json:"utilization_percent"`
	MemoryUsedMb       uint64  `json:"memory_used_mb"`
	MemoryTotalMb      uint64  `json:"memory_total_mb"`
	TemperatureC       uint    `json:"temperature_c"`
	PowerDrawW         float64 `json:"power_draw_w"`
}

// SystemStatus holds the overall health of the telemetry agent
// plus the list of per-GPU metrics.
type SystemStatus struct {
	SystemStatus string      `json:"system_status"`
	ErrorMessage *string     `json:"error_message"`
	Gpus         []GpuMetric `json:"gpus"`
	Timestamp    string      `json:"timestamp"`
}

// buildDegradedStatus constructs a SystemStatus with "degraded" status,
// the provided error text, and an empty GPU list.
func buildDegradedStatus(errorMessage string) SystemStatus {
	currentTime := time.Now().UTC().Format(time.RFC3339)
	messageCopy := errorMessage

	return SystemStatus{
		SystemStatus: "degraded",
		ErrorMessage: &messageCopy,
		Gpus:         []GpuMetric{},
		Timestamp:    currentTime,
	}
}
