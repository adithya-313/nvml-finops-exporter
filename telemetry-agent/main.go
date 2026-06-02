package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"

	"telemetry-agent/internal/gpu"
	pb "telemetry-agent/internal/pb"
)

type telemetryServer struct {
	pb.UnimplementedGpuTelemetryServer
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

	return resp, nil
}

func main() {
	lis, err := net.Listen("tcp", ":50051")
	if err != nil {
		log.Fatalf("failed to listen: %v", err)
	}

	s := grpc.NewServer()
	pb.RegisterGpuTelemetryServer(s, &telemetryServer{})
	reflection.Register(s)

	fmt.Println("telemetry-agent gRPC server listening on :50051")
	if err := s.Serve(lis); err != nil {
		log.Fatalf("failed to serve: %v", err)
	}
}
