#!/bin/bash

echo "===== Checking GPU and CUDA Configuration ====="

# Check if nvidia-smi is available
if command -v nvidia-smi &> /dev/null; then
    echo "✅ NVIDIA SMI is available."
    echo "===== GPU Information ====="
    nvidia-smi
else
    echo "❌ NVIDIA SMI is not available. GPU acceleration may not work."
fi

# Check CUDA version
if command -v nvcc &> /dev/null; then
    echo "===== CUDA Version ====="
    nvcc --version
else
    echo "❌ NVCC not found. CUDA toolkit may not be installed properly."
fi

# Check CUDA libraries
echo "===== CUDA Libraries Check ====="
if [ -d "/usr/local/cuda/lib64" ] || [ -d "/usr/local/cuda/lib" ]; then
    echo "✅ CUDA libraries found"
    ls -l /usr/local/cuda/lib64 2>/dev/null || ls -l /usr/local/cuda/lib 2>/dev/null
else
    echo "❌ CUDA libraries directory not found in standard location"
fi

# Check if OpenCV is using CUDA
echo "===== OpenCV CUDA Check ====="
python3.10 -c "import cv2; print('OpenCV version:', cv2.__version__); print('OpenCV CUDA enabled:', cv2.cuda.getCudaEnabledDeviceCount() > 0)"

# Check if FFmpeg is available
echo "===== FFmpeg Check ====="
ffmpeg -version | head -n 1

# Generate a summary
echo ""
echo "===== Environment Summary ====="
echo "Python: $(python3.10 --version)"
echo "CUDA Environment Variables:"
echo "CUDA_VISIBLE_DEVICES: $CUDA_VISIBLE_DEVICES"
echo "NVIDIA_VISIBLE_DEVICES: $NVIDIA_VISIBLE_DEVICES"
echo "PATH: $PATH"
echo "LD_LIBRARY_PATH: $LD_LIBRARY_PATH"

# Check GPU availability using nvidia-smi instead of torch
GPU_AVAILABLE=false
if nvidia-smi &>/dev/null; then
    GPU_AVAILABLE=true
fi

echo ""
echo "System is$([ "$GPU_AVAILABLE" = true ] || echo " NOT") ready for GPU-accelerated video processing."
echo "===== Configuration Check Complete ====="
