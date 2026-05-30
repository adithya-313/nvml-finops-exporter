//go:build windows

package gpu

import (
	"fmt"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"
)

// NVML constants and structs matching the C headers.
const nvmlTemperatureGpu = 0

type nvmlMemory_v1 struct {
	Total uint64
	Free  uint64
}

type nvmlUtilizationRates_v2 struct {
	Version uint32
	Gpu     uint32
	Memory  uint32
}

// Global NVML function pointers, populated by nvmlLoadLibrary.
var (
	nvmlDLL                    *windows.DLL
	procInit                   *windows.Proc
	procShutdown               *windows.Proc
	procDeviceGetCount         *windows.Proc
	procDeviceGetHandleByIndex *windows.Proc
	procDeviceGetUUID          *windows.Proc
	procDeviceGetUtilRates     *windows.Proc
	procDeviceGetMemoryInfo    *windows.Proc
	procDeviceGetTemperature   *windows.Proc
	procDeviceGetPowerUsage    *windows.Proc
)

func nvmlLoadLibrary() error {
	var loadError error
	nvmlDLL, loadError = windows.LoadDLL("nvml.dll")
	if loadError != nil {
		return fmt.Errorf("failed to load nvml.dll: %w", loadError)
	}

	procedureMap := map[string]**windows.Proc{
		"nvmlInit_v2":                   &procInit,
		"nvmlShutdown":                  &procShutdown,
		"nvmlDeviceGetCount_v2":         &procDeviceGetCount,
		"nvmlDeviceGetHandleByIndex_v2": &procDeviceGetHandleByIndex,
		"nvmlDeviceGetUUID":             &procDeviceGetUUID,
		"nvmlDeviceGetUtilizationRates": &procDeviceGetUtilRates,
		"nvmlDeviceGetMemoryInfo":       &procDeviceGetMemoryInfo,
		"nvmlDeviceGetTemperature":      &procDeviceGetTemperature,
		"nvmlDeviceGetPowerUsage":       &procDeviceGetPowerUsage,
	}

	for name, ptr := range procedureMap {
		proc, err := nvmlDLL.FindProc(name)
		if err != nil {
			return fmt.Errorf("failed to find %s: %w", name, err)
		}
		*ptr = proc
	}
	return nil
}

func CollectGpuMetrics() SystemStatus {
	loadError := nvmlLoadLibrary()
	if loadError != nil {
		return buildDegradedStatus(fmt.Sprintf("nvmlLoadLibrary failed: %v", loadError))
	}

	initReturn, _, _ := procInit.Call()
	if initReturn != 0 {
		return buildDegradedStatus(fmt.Sprintf("nvmlInit_v2 returned %d", initReturn))
	}

	defer func() {
		shutdownReturn, _, _ := procShutdown.Call()
		if shutdownReturn != 0 {
			fmt.Printf("warning: nvmlShutdown returned %d\n", shutdownReturn)
		}
	}()

	var deviceCount uint32
	countReturn, _, _ := procDeviceGetCount.Call(uintptr(unsafe.Pointer(&deviceCount)))
	if countReturn != 0 {
		return buildDegradedStatus(fmt.Sprintf("nvmlDeviceGetCount returned %d", countReturn))
	}

	gpuMetrics := make([]GpuMetric, 0, deviceCount)

	for deviceIndex := 0; deviceIndex < int(deviceCount); deviceIndex++ {
		var deviceHandle uintptr
		handleReturn, _, _ := procDeviceGetHandleByIndex.Call(
			uintptr(deviceIndex), uintptr(unsafe.Pointer(&deviceHandle)),
		)
		if handleReturn != 0 {
			fmt.Printf("warning: DeviceGetHandleByIndex(%d) returned %d\n", deviceIndex, handleReturn)
			continue
		}

		metric := GpuMetric{}

		// UUID
		const uuidBufSize = 80
		uuidBuf := make([]byte, uuidBufSize)
		uuidReturn, _, _ := procDeviceGetUUID.Call(
			deviceHandle, uintptr(unsafe.Pointer(&uuidBuf[0])), uintptr(uuidBufSize),
		)
		if uuidReturn == 0 {
			uuidLen := 0
			for i := 0; i < uuidBufSize; i++ {
				if uuidBuf[i] == 0 {
					break
				}
				uuidLen++
			}
			metric.Uuid = string(uuidBuf[:uuidLen])
		} else {
			metric.Uuid = fmt.Sprintf("unknown-%d", deviceIndex)
		}

		// Utilization
		var utilRates nvmlUtilizationRates_v2
		utilRates.Version = 2
		utilReturn, _, _ := procDeviceGetUtilRates.Call(
			deviceHandle, uintptr(unsafe.Pointer(&utilRates)),
		)
		if utilReturn == 0 {
			metric.UtilizationPercent = uint(utilRates.Gpu)
		}

		// Memory
		var memInfo nvmlMemory_v1
		memReturn, _, _ := procDeviceGetMemoryInfo.Call(
			deviceHandle, uintptr(unsafe.Pointer(&memInfo)),
		)
		if memReturn == 0 {
			metric.MemoryUsedMb = memInfo.Total/(1024*1024) - memInfo.Free/(1024*1024)
			metric.MemoryTotalMb = memInfo.Total / (1024 * 1024)
		}

		// Temperature
		var tempValue uint32
		tempReturn, _, _ := procDeviceGetTemperature.Call(
			deviceHandle, uintptr(nvmlTemperatureGpu), uintptr(unsafe.Pointer(&tempValue)),
		)
		if tempReturn == 0 {
			metric.TemperatureC = uint(tempValue)
		}

		// Power
		var powerValue uint32
		powerReturn, _, _ := procDeviceGetPowerUsage.Call(
			deviceHandle, uintptr(unsafe.Pointer(&powerValue)),
		)
		if powerReturn == 0 {
			metric.PowerDrawW = float64(powerValue) / 1000.0
		}

		gpuMetrics = append(gpuMetrics, metric)
	}

	return SystemStatus{
		SystemStatus: "healthy",
		ErrorMessage: nil,
		Gpus:         gpuMetrics,
		Timestamp:    time.Now().UTC().Format(time.RFC3339),
	}
}
