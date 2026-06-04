package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"sync"
	"time"

	"github.com/beevik/ntp"
	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"

	"telemetry-agent/internal/gpu"
	pb "telemetry-agent/internal/pb"
)

type telemetryServer struct {
	pb.UnimplementedGpuTelemetryServer
	mu         sync.RWMutex
	NtpOffsetMs int64
}

func (s *telemetryServer) GetMetrics(ctx context.Context, req *pb.TelemetryRequest) (*pb.TelemetryResponse, error) {
	currentState := gpu.CollectGpuMetrics()

	ts := time.Now().Unix()
	resp := &pb.TelemetryResponse{
		SystemStatus: currentState.SystemStatus,
		TimestampUtc: ts,
	}

	if currentState.ErrorMessage != nil {
		resp.ErrorMessage = *currentState.ErrorMessage
	}

	s.mu.RLock()
	resp.NtpOffsetMs = s.NtpOffsetMs
	s.mu.RUnlock()

	for _, g := range currentState.Gpus {
		resp.Gpus = append(resp.Gpus, &pb.GpuMetric{
			Uuid:               g.Uuid,
			Name:               g.Name,
			UtilizationPercent: float64(g.UtilizationPercent),
			MemoryUsedMb:       g.MemoryUsedMb,
			MemoryTotalMb:      g.MemoryTotalMb,
			TemperatureC:       float64(g.TemperatureC),
			PowerDrawW:         g.PowerDrawW,
		})
	}

	return resp, nil
}

func pollNTP(s *telemetryServer) {
	for {
		response, err := ntp.Query("time.google.com")
		if err != nil {
			log.Printf("[NTP] query failed: %v (defaulting offset to 0)", err)
			s.mu.Lock()
			s.NtpOffsetMs = 0
			s.mu.Unlock()
		} else {
			offset := response.ClockOffset.Milliseconds()
			s.mu.Lock()
			s.NtpOffsetMs = offset
			s.mu.Unlock()
			log.Printf("[NTP] clock offset: %d ms", offset)
		}
		time.Sleep(60 * time.Second)
	}
}

func main() {
	server := &telemetryServer{}

	go pollNTP(server)

	lis, err := net.Listen("tcp", ":50051")
	if err != nil {
		log.Fatalf("failed to listen: %v", err)
	}

	s := grpc.NewServer()
	pb.RegisterGpuTelemetryServer(s, server)
	reflection.Register(s)

	fmt.Println("telemetry-agent gRPC server listening on :50051")
	if err := s.Serve(lis); err != nil {
		log.Fatalf("failed to serve: %v", err)
	}
}
