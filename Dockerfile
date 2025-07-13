FROM nvidia/cuda:11.8.0-runtime-ubuntu20.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV IMAGEMAGICK_BINARY=/usr/bin/convert
ENV PATH /usr/local/cuda/bin:${PATH}
ENV LD_LIBRARY_PATH /usr/local/cuda/lib64:${LD_LIBRARY_PATH}

# Install Python and other dependencies
RUN apt-get update && apt-get install -y \
  software-properties-common \
  && add-apt-repository ppa:deadsnakes/ppa \
  && apt-get update \
  && apt-get install -y \
  python3.10 \
  python3.10-dev \
  python3-pip \
  python3.10-distutils \
  wget \
  build-essential \
  libssl-dev \
  libffi-dev \
  libespeak-dev \
  zlib1g-dev \
  libmupdf-dev \
  libfreetype6-dev \
  ffmpeg \
  espeak \
  imagemagick \
  libpango1.0-dev \
  git \
  postgresql \
  postgresql-contrib \
  libfreetype6 \
  libfontconfig1 \
  fonts-liberation \
  libpq-dev \
  && rm -rf /var/lib/apt/lists/*

# Set Python 3.10 as the default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.10 1

# Install pip for Python 3.10
RUN wget https://bootstrap.pypa.io/get-pip.py && \
    python3.10 get-pip.py && \
    rm get-pip.py

WORKDIR /app

# Install CUDA-specific packages
COPY ./requirements.txt .
RUN pip3 install numpy
RUN pip3 install django-ratelimit
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .
COPY .env /app/.env

# Create ImageMagick policy.xml file directory if it doesn't exist
RUN mkdir -p /etc/ImageMagick-6/
COPY ./policy.xml /etc/ImageMagick-6/policy.xml
RUN if [ -f /etc/ImageMagick-6/policy.xml ]; then \
    sed -i 's/<policy domain="path" rights="none" pattern="@\*"/<!--<policy domain="path" rights="none" pattern="@\*"-->/' /etc/ImageMagick-6/policy.xml || true; \
    fi && \
    if [ -d /etc/ImageMagick-7/ ]; then \
    sed -i 's/<policy domain="path" rights="none" pattern="@\*"/<!--<policy domain="path" rights="none" pattern="@\*"-->/' /etc/ImageMagick-7/policy.xml || true; \
    fi

# Create custom fonts directory
RUN mkdir -p /usr/share/fonts/custom
COPY ./fonts /usr/share/fonts/custom
RUN fc-cache -f -v

# Run any setup scripts
RUN python3.10 manage.py add_fonts || true
RUN ldconfig

# Add GPU check script
COPY ./check_gpu.sh /app/check_gpu.sh
RUN chmod +x /app/check_gpu.sh

# Expose port
EXPOSE 8000

# Run application
CMD ["bash", "-c", "export $(cat /app/.env | xargs) && yes y | python3.10 manage.py makemigrations && python3.10 manage.py migrate --noinput && python3.10 manage.py collectstatic --noinput && python3.10 manage.py runserver 127.0.0.1:8000"]
