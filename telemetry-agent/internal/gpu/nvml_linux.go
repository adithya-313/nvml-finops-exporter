//go:build linux

package gpu

import (
	"fmt"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

// nvidiaSmiGpuRaw holds one row of nvidia-smi CSV output.
type nvidiaSmiGpuRaw struct {
	Index          string
	Uuid           string
	UtilizationGpu string
	MemoryUsed     string
	MemoryTotal    string
	TemperatureGpu string
	PowerDraw      string
}

func CollectGpuMetrics() SystemStatus {
	rawGpus, queryError := queryNvidiaSmi()
	if queryError != nil {
		return buildDegradedStatus(fmt.Sprintf("nvidia-smi query failed: %v", queryError))
	}

	gpuMetrics := parseNvidiaSmiOutput(rawGpus)

	if len(gpuMetrics) == 0 {
		msg := "nvidia-smi returned zero GPUs"
		return SystemStatus{
			SystemStatus: "degraded",
			ErrorMessage: &msg,
			Gpus:         gpuMetrics,
			Timestamp:    time.Now().UTC().Format(time.RFC3339),
		}
	}

	return SystemStatus{
		SystemStatus: "healthy",
		ErrorMessage: nil,
		Gpus:         gpuMetrics,
		Timestamp:    time.Now().UTC().Format(time.RFC3339),
	}
}

func queryNvidiaSmi() ([]nvidiaSmiGpuRaw, error) {
	cmd := exec.Command("nvidia-smi",
		"--query-gpu=index,uuid,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
		"--format=csv,noheader,nounits",
	)
	outputBytes, runError := cmd.Output()
	if runError != nil {
		return nil, fmt.Errorf("nvidia-smi execution failed: %w", runError)
	}

	outputLines := strings.Split(strings.TrimSpace(string(outputBytes)), "\n")
	rawGpus := make([]nvidiaSmiGpuRaw, 0, len(outputLines))

	for _, line := range outputLines {
		fields := strings.Split(line, ", ")
		if len(fields) < 7 {
			continue
		}
		rawGpus = append(rawGpus, nvidiaSmiGpuRaw{
			Index:          strings.TrimSpace(fields[0]),
			Uuid:           strings.TrimSpace(fields[1]),
			UtilizationGpu: strings.TrimSpace(fields[2]),
			MemoryUsed:     strings.TrimSpace(fields[3]),
			MemoryTotal:    strings.TrimSpace(fields[4]),
			TemperatureGpu: strings.TrimSpace(fields[5]),
			PowerDraw:      strings.TrimSpace(fields[6]),
		})
	}

	return rawGpus, nil
}

func parseNvidiaSmiOutput(rawGpus []nvidiaSmiGpuRaw) []GpuMetric {
	gpuMetrics := make([]GpuMetric, 0, len(rawGpus))

	for _, raw := range rawGpus {
		metric := GpuMetric{Uuid: raw.Uuid}

		if utilValue, parseError := strconv.ParseUint(raw.UtilizationGpu, 10, 32); parseError == nil {
			metric.UtilizationPercent = uint(utilValue)
		}

		memUsedStr := strings.TrimSuffix(raw.MemoryUsed, " MiB")
		if memValue, parseError := strconv.ParseUint(memUsedStr, 10, 64); parseError == nil {
			metric.MemoryUsedMb = memValue
		}

		memTotalStr := strings.TrimSuffix(raw.MemoryTotal, " MiB")
		if memValue, parseError := strconv.ParseUint(memTotalStr, 10, 64); parseError == nil {
			metric.MemoryTotalMb = memValue
		}

		if tempValue, parseError := strconv.ParseUint(raw.TemperatureGpu, 10, 32); parseError == nil {
			metric.TemperatureC = uint(tempValue)
		}

		powerStr := strings.TrimSuffix(raw.PowerDraw, " W")
		if powerValue, parseError := strconv.ParseFloat(powerStr, 64); parseError == nil {
			metric.PowerDrawW = powerValue
		}

		gpuMetrics = append(gpuMetrics, metric)
	}

	return gpuMetrics
}
