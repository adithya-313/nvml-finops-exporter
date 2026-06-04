import torch
import time
import sys

def main():
    print("🔥 IGNITING NATIVE CUDA STRESS TEST 🔥")
    
    if not torch.cuda.is_available():
        print("❌ ERROR: CUDA not found. Ensure NVIDIA drivers and PyTorch are installed.")
        sys.exit(1)

    device = torch.device('cuda')
    print(f"✅ Hardware Hooked: {torch.cuda.get_device_name(device)}")
    print("⏳ Flooding VRAM and CUDA Cores with Matrix Multiplications...")
    print("🛑 Press Ctrl+C to terminate the workload and return to IDLE state.")

    try:
        # Create massive 15000x15000 matrices to spike VRAM and Power immediately
        dimension = 15000
        matrix_a = torch.randn(dimension, dimension, device=device)
        matrix_b = torch.randn(dimension, dimension, device=device)
        
        # Infinite loop forcing 100% CUDA core utilization
        while True:
            _ = torch.matmul(matrix_a, matrix_b)
            
    except KeyboardInterrupt:
        print("\n🛑 Load generator terminated. GPU returning to idle state.")
        sys.exit(0)

if __name__ == "__main__":
    main()
