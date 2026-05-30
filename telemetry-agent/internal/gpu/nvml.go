package gpu

import (
	"fmt"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"
)

// ---------------------------------------------------------------------------
// Constants and types mirroring the C definitions found in nvml.h
// ---------------------------------------------------------------------------

// nvmlReturn represents the NVML error/success code returned by every
// NVML function.  SUCCESS (0) means the call completed without error.
const nvmlSuccess = 0

// nvmlTemperatureThresholds identifies which temperature sensor to read.
// TEMPERATURE_GPU (0) is the on-die GPU temperature.
const nvmlTemperatureGpu = 0

// nvmlMemory_v1 is the legacy C struct nvmlMemory_t (v1).  It is
// returned by the unversioned nvmlDeviceGetMemoryInfo function and
// contains total and free device memory in bytes.
type nvmlMemory_v1 struct {
	Total uint64
	Free  uint64
}

// nvmlUtilizationRates_v2 is the C struct nvmlUtilization_t.  It holds
// the GPU and memory controller utilisation percentages (0-100).
type nvmlUtilizationRates_v2 struct {
	Version uint32
	Gpu     uint32
	Memory  uint32
}

// GpuMetric represents a snapshot of a single GPU's telemetry data.
// Each field corresponds to a value exposed by NVML.
type GpuMetric struct {
	Uuid               string  `json:"uuid"`
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

// ---------------------------------------------------------------------------
// Global NVML function pointers initialised once in init().
// We load nvml.dll at program startup and look up every procedure we
// need so the rest of the code can call them without repeated lookups.
// ---------------------------------------------------------------------------

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
	procInitWithFlags          *windows.Proc
)

// nvmlLoadLibrary loads nvml.dll and resolves all procedure addresses.
// It returns an error if the DLL cannot be found or a symbol is missing.
func nvmlLoadLibrary() error {
	var loadError error

	// On Windows the NVIDIA driver places nvml.dll in
	// %ProgramFiles%\NVIDIA Corporation\NVSMI\ and also adds that
	// directory to the system PATH.  windows.LoadDLL will search
	// the standard system library path.
	nvmlDLL, loadError = windows.LoadDLL("nvml.dll")
	if loadError != nil {
		return fmt.Errorf("failed to load nvml.dll: %w", loadError)
	}

	// Look up every NVML function that this package uses.
	procedureMap := map[string]**windows.Proc{
		"nvmlInit_v2":                   &procInit,
		"nvmlInitWithFlags":             &procInitWithFlags,
		"nvmlShutdown":                  &procShutdown,
		"nvmlDeviceGetCount_v2":         &procDeviceGetCount,
		"nvmlDeviceGetHandleByIndex_v2": &procDeviceGetHandleByIndex,
		"nvmlDeviceGetUUID":             &procDeviceGetUUID,
		"nvmlDeviceGetUtilizationRates": &procDeviceGetUtilRates,
		"nvmlDeviceGetMemoryInfo":       &procDeviceGetMemoryInfo,
		"nvmlDeviceGetTemperature":      &procDeviceGetTemperature,
		"nvmlDeviceGetPowerUsage":       &procDeviceGetPowerUsage,
	}

	for procedureName, procedurePointer := range procedureMap {
		procedure, findError := nvmlDLL.FindProc(procedureName)
		if findError != nil {
			return fmt.Errorf("failed to find %s: %w", procedureName, findError)
		}
		*procedurePointer = procedure
	}

	return nil
}

// ---------------------------------------------------------------------------
// Thin wrappers around the NVML C ABI that handle type conversions
// ---------------------------------------------------------------------------

// nvmlInit calls nvmlInit_v2 (the latest versioned init).
func nvmlInit() error {
	initReturn, _, _ := procInit.Call()
	if initReturn != nvmlSuccess {
		return fmt.Errorf("nvmlInit_v2 returned %d", initReturn)
	}
	return nil
}

// nvmlShutdown tears down the NVML library.
func nvmlShutdown() error {
	shutdownReturn, _, _ := procShutdown.Call()
	if shutdownReturn != nvmlSuccess {
		return fmt.Errorf("nvmlShutdown returned %d", shutdownReturn)
	}
	return nil
}

// nvmlDeviceGetCount returns the number of visible NVIDIA GPUs.
func nvmlDeviceGetCount() (int, error) {
	var deviceCount uint32
	countReturn, _, _ := procDeviceGetCount.Call(
		uintptr(unsafe.Pointer(&deviceCount)),
	)
	if countReturn != nvmlSuccess {
		return 0, fmt.Errorf("nvmlDeviceGetCount returned %d", countReturn)
	}
	return int(deviceCount), nil
}

// nvmlDeviceGetHandleByIndex returns an opaque handle for the GPU at
// the given 0-based index.
func nvmlDeviceGetHandleByIndex(deviceIndex int) (uintptr, error) {
	var deviceHandle uintptr
	handleReturn, _, _ := procDeviceGetHandleByIndex.Call(
		uintptr(deviceIndex),
		uintptr(unsafe.Pointer(&deviceHandle)),
	)
	if handleReturn != nvmlSuccess {
		return 0, fmt.Errorf("nvmlDeviceGetHandleByIndex(%d) returned %d", deviceIndex, handleReturn)
	}
	return deviceHandle, nil
}

// nvmlDeviceGetUUID retrieves the globally-unique hardware identifier
// for the GPU referenced by deviceHandle.
func nvmlDeviceGetUUID(deviceHandle uintptr) (string, error) {
	// The NVML API expects a buffer of at least NVML_DEVICE_UUID_BUFFER_SIZE (80).
	const uuidBufferSize = 80
	uuidBuffer := make([]byte, uuidBufferSize)
	uuidReturn, _, _ := procDeviceGetUUID.Call(
		deviceHandle,
		uintptr(unsafe.Pointer(&uuidBuffer[0])),
		uintptr(uuidBufferSize),
	)
	if uuidReturn != nvmlSuccess {
		return "", fmt.Errorf("nvmlDeviceGetUUID returned %d", uuidReturn)
	}

	// Find the null terminator and convert to string.
	uuidLength := 0
	for uuidIndex := 0; uuidIndex < uuidBufferSize; uuidIndex++ {
		if uuidBuffer[uuidIndex] == 0 {
			break
		}
		uuidLength++
	}
	return string(uuidBuffer[:uuidLength]), nil
}

// nvmlDeviceGetUtilizationRates returns the GPU utilisation percentage.
func nvmlDeviceGetUtilizationRates(deviceHandle uintptr) (uint32, error) {
	var utilizationRates nvmlUtilizationRates_v2
	utilizationRates.Version = 2 // nvmlUtilizationRates_v2
	utilReturn, _, _ := procDeviceGetUtilRates.Call(
		deviceHandle,
		uintptr(unsafe.Pointer(&utilizationRates)),
	)
	if utilReturn != nvmlSuccess {
		return 0, fmt.Errorf("nvmlDeviceGetUtilizationRates returned %d", utilReturn)
	}
	return utilizationRates.Gpu, nil
}

// nvmlDeviceGetMemoryInfo returns total and used device memory in bytes.
func nvmlDeviceGetMemoryInfo(deviceHandle uintptr) (totalBytes uint64, usedBytes uint64, returnError error) {
	var memoryInfo nvmlMemory_v1
	memoryReturn, _, _ := procDeviceGetMemoryInfo.Call(
		deviceHandle,
		uintptr(unsafe.Pointer(&memoryInfo)),
	)
	if memoryReturn != nvmlSuccess {
		return 0, 0, fmt.Errorf("nvmlDeviceGetMemoryInfo returned %d", memoryReturn)
	}
	return memoryInfo.Total, memoryInfo.Total - memoryInfo.Free, nil
}

// nvmlDeviceGetTemperature reads the GPU temperature in degrees Celsius.
func nvmlDeviceGetTemperature(deviceHandle uintptr) (uint32, error) {
	var temperatureValue uint32
	temperatureReturn, _, _ := procDeviceGetTemperature.Call(
		deviceHandle,
		uintptr(nvmlTemperatureGpu),
		uintptr(unsafe.Pointer(&temperatureValue)),
	)
	if temperatureReturn != nvmlSuccess {
		return 0, fmt.Errorf("nvmlDeviceGetTemperature returned %d", temperatureReturn)
	}
	return temperatureValue, nil
}

// nvmlDeviceGetPowerUsage returns the current power draw in milliwatts.
func nvmlDeviceGetPowerUsage(deviceHandle uintptr) (uint32, error) {
	var powerValue uint32
	powerReturn, _, _ := procDeviceGetPowerUsage.Call(
		deviceHandle,
		uintptr(unsafe.Pointer(&powerValue)),
	)
	if powerReturn != nvmlSuccess {
		return 0, fmt.Errorf("nvmlDeviceGetPowerUsage returned %d", powerReturn)
	}
	return powerValue, nil
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

// CollectGpuMetrics attempts to initialise NVML, enumerate every GPU,
// extract telemetry, and return a SystemStatus.  If NVML cannot be
// initialised the returned status is "degraded" and the error is
// captured; the function never panics.
func CollectGpuMetrics() SystemStatus {
	// Load nvml.dll and resolve all function pointers.
	loadError := nvmlLoadLibrary()
	if loadError != nil {
		return buildDegradedStatus(fmt.Sprintf("nvmlLoadLibrary() failed: %v", loadError))
	}

	// Attempt to initialise the NVML library.
	initError := nvmlInit()
	if initError != nil {
		return buildDegradedStatus(fmt.Sprintf("nvml.Init() failed: %v", initError))
	}

	// Ensure NVML is shut down before the function returns so we
	// don't leak library resources.
	defer func() {
		shutdownError := nvmlShutdown()
		if shutdownError != nil {
			fmt.Printf("warning: nvml.Shutdown() failed: %v\n", shutdownError)
		}
	}()

	// Query the number of visible NVIDIA GPUs.
	deviceCount, countError := nvmlDeviceGetCount()
	if countError != nil {
		return buildDegradedStatus(fmt.Sprintf("nvml.DeviceGetCount() failed: %v", countError))
	}

	// Allocate a slice large enough to hold every GPU metric.
	gpuMetrics := make([]GpuMetric, 0, deviceCount)

	// Iterate over each GPU and attempt to collect telemetry.
	for deviceIndex := 0; deviceIndex < deviceCount; deviceIndex++ {
		deviceHandle, handleError := nvmlDeviceGetHandleByIndex(deviceIndex)
		if handleError != nil {
			fmt.Printf("warning: DeviceGetHandleByIndex(%d) failed, skipping: %v\n", deviceIndex, handleError)
			continue
		}

		metric := GpuMetric{}

		// UUID – a globally unique identifier for the GPU.
		uuidValue, uuidError := nvmlDeviceGetUUID(deviceHandle)
		if uuidError == nil {
			metric.Uuid = uuidValue
		} else {
			metric.Uuid = fmt.Sprintf("unknown-%d", deviceIndex)
		}

		// Utilization rates (percent).  We only extract the
		// "GPU" (compute) utilisation, not memory bandwidth.
		utilizationValue, utilError := nvmlDeviceGetUtilizationRates(deviceHandle)
		if utilError == nil {
			metric.UtilizationPercent = uint(utilizationValue)
		}

		// Memory usage (NVML returns bytes; we convert to MiB).
		totalMemoryBytes, usedMemoryBytes, memoryError := nvmlDeviceGetMemoryInfo(deviceHandle)
		if memoryError == nil {
			metric.MemoryUsedMb = usedMemoryBytes / (1024 * 1024)
			metric.MemoryTotalMb = totalMemoryBytes / (1024 * 1024)
		}

		// GPU temperature in degrees Celsius.
		temperatureValue, temperatureError := nvmlDeviceGetTemperature(deviceHandle)
		if temperatureError == nil {
			metric.TemperatureC = uint(temperatureValue)
		}

		// Power draw in milliwatts; we convert to watts.
		powerMilliWatts, powerError := nvmlDeviceGetPowerUsage(deviceHandle)
		if powerError == nil {
			metric.PowerDrawW = float64(powerMilliWatts) / 1000.0
		}

		gpuMetrics = append(gpuMetrics, metric)
	}

	// Build the final status with an ISO-8601 timestamp.
	currentTime := time.Now().UTC().Format(time.RFC3339)

	return SystemStatus{
		SystemStatus: "healthy",
		ErrorMessage: nil,
		Gpus:         gpuMetrics,
		Timestamp:    currentTime,
	}
}

// buildDegradedStatus is a helper that constructs a SystemStatus with
// "degraded" status, the provided error text, and an empty GPU list.
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
