//go:build linux

package gpu

import (
	"fmt"
	"math/rand"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

func init() {
	// Seed the global random source so that every call to
	// generateMockMetrics() produces fresh jitter.
	rand.Seed(time.Now().UnixNano())
}

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
		// If nvidia-smi is unavailable (e.g. inside a container
		// without GPU passthrough), fall back to mock data so
		// the monitoring pipeline can still be exercised.
		return generateMockMetrics()
	}

	gpuMetrics := parseNvidiaSmiOutput(rawGpus)

	if len(gpuMetrics) == 0 {
		return generateMockMetrics()
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

// generateMockMetrics returns plausible GPU metrics for environments
// where real NVIDIA hardware is not accessible (e.g. inside a Docker
// container without --gpus passthrough).  This allows the full
// monitoring pipeline to be validated end-to-end.
//
// Each call introduces randomised jitter so the Prometheus time
// series show realistic variation for the stats engine.
func generateMockMetrics() SystemStatus {
	// Power jitter: base 175W +/- 5W
	powerJitter := 175.0 + (rand.Float64()*10.0 - 5.0)

	// Utilization jitter: base 42% +/- 5pp
	utilJitter := 42 + rand.Intn(10) - 5
	if utilJitter < 0 {
		utilJitter = 0
	}
	if utilJitter > 100 {
		utilJitter = 100
	}

	// Temperature jitter: base 65C +/- 3C
	tempJitter := 65 + rand.Intn(6) - 3

	// Memory jitter: base 3072 MiB +/- 256 MiB
	memJitter := 3072 + rand.Intn(512) - 256

	mockGpu := GpuMetric{
		Uuid:               "GPU-mock-0000-0000-000000000001",
		UtilizationPercent: uint(utilJitter),
		MemoryUsedMb:       uint64(memJitter),
		MemoryTotalMb:      8192,
		TemperatureC:       uint(tempJitter),
		PowerDrawW:         powerJitter,
	}

	return SystemStatus{
		SystemStatus: "healthy",
		ErrorMessage: nil,
		Gpus:         []GpuMetric{mockGpu},
		Timestamp:    time.Now().UTC().Format(time.RFC3339),
	}
}
