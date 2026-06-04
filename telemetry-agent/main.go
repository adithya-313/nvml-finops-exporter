package main

import (
	"log"
	"sync"
	"time"

	"github.com/beevik/ntp"
	"github.com/nats-io/nats.go"
	"google.golang.org/protobuf/proto"

	"telemetry-agent/internal/gpu"
	pb "telemetry-agent/internal/pb"
)

type telemetryAgent struct {
	mu          sync.RWMutex
	ntpOffsetMs int64
}

func (a *telemetryAgent) pollNTP() {
	for {
		response, err := ntp.Query("time.google.com")
		if err != nil {
			log.Printf("[NTP] query failed: %v (defaulting offset to 0)", err)
			a.mu.Lock()
			a.ntpOffsetMs = 0
			a.mu.Unlock()
		} else {
			offset := response.ClockOffset.Milliseconds()
			a.mu.Lock()
			a.ntpOffsetMs = offset
			a.mu.Unlock()
			log.Printf("[NTP] clock offset: %d ms", offset)
		}
		time.Sleep(60 * time.Second)
	}
}

func main() {
	agent := &telemetryAgent{}
	go agent.pollNTP()

	nc, err := nats.Connect("nats://nats:4222")
	if err != nil {
		log.Fatalf("failed to connect to NATS: %v", err)
	}
	defer nc.Close()
	log.Println("connected to NATS at nats://nats:4222")

	ticker := time.NewTicker(1 * time.Second)
	defer ticker.Stop()

	for range ticker.C {
		currentState := gpu.CollectGpuMetrics()
		ts := time.Now().Unix()

		resp := &pb.TelemetryResponse{
			SystemStatus: currentState.SystemStatus,
			TimestampUtc: ts,
		}
		if currentState.ErrorMessage != nil {
			resp.ErrorMessage = *currentState.ErrorMessage
		}

		agent.mu.RLock()
		resp.NtpOffsetMs = agent.ntpOffsetMs
		agent.mu.RUnlock()

		for _, g := range currentState.Gpus {
			resp.Gpus = append(resp.Gpus, &pb.GpuMetric{
				Uuid:               g.Uuid,
				UtilizationPercent: float64(g.UtilizationPercent),
				MemoryUsedMb:       g.MemoryUsedMb,
				MemoryTotalMb:      g.MemoryTotalMb,
				TemperatureC:       float64(g.TemperatureC),
				PowerDrawW:         g.PowerDrawW,
			})
		}

		data, err := proto.Marshal(resp)
		if err != nil {
			log.Printf("failed to marshal protobuf: %v", err)
			continue
		}

		if err := nc.Publish("telemetry.gpu.metrics", data); err != nil {
			log.Printf("failed to publish: %v", err)
		}
	}
}
