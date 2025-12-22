group "all" {
  targets = [
    "rag-converter",
    "asr-service",
    "llm-service",
    "multimodal-service",
    "pipeline-service",
    "meta-service",
    "slicer-service",
    "ui-service",
    "vector-service",
    "video-service",
    "deps-redis",
    "deps-minio",
    "deps-mysql",
    "deps-es",
  ]
}

group "modules" {
  targets = [
    "asr-service",
    "llm-service",
    "multimodal-service",
    "pipeline-service",
    "meta-service",
    "slicer-service",
    "ui-service",
    "vector-service",
    "video-service",
  ]
}

target "app-base" {
  context    = "."
  dockerfile = "docker/Dockerfile.app"
  cache-from = ["type=gha"]
  cache-to   = ["type=gha,mode=max"]
}

target "rag-converter" {
  inherits = ["app-base"]
  target   = "bundle"
  tags     = ["rag-converter/core:latest"]
  output   = ["type=docker,dest=./docker/images/rag-converter.tar"]
}

target "asr-service" {
  inherits = ["app-base"]
  target   = "asr-service"
  tags     = ["rag-converter/asr:latest"]
  output   = ["type=docker,dest=./docker/images/asr-service.tar"]
}

target "llm-service" {
  inherits = ["app-base"]
  target   = "llm-service"
  tags     = ["rag-converter/llm:latest"]
  output   = ["type=docker,dest=./docker/images/llm-service.tar"]
}

target "multimodal-service" {
  inherits = ["app-base"]
  target   = "multimodal-service"
  tags     = ["rag-converter/multimodal:latest"]
  output   = ["type=docker,dest=./docker/images/multimodal-service.tar"]
}

target "pipeline-service" {
  inherits = ["app-base"]
  target   = "pipeline-service"
  tags     = ["rag-converter/pipeline:latest"]
  output   = ["type=docker,dest=./docker/images/pipeline-service.tar"]
}

target "meta-service" {
  inherits = ["app-base"]
  target   = "meta-service"
  tags     = ["rag-converter/meta:latest"]
  output   = ["type=docker,dest=./docker/images/meta-service.tar"]
}

target "slicer-service" {
  inherits = ["app-base"]
  target   = "slicer-service"
  tags     = ["rag-converter/slicer:latest"]
  output   = ["type=docker,dest=./docker/images/slicer-service.tar"]
}

target "ui-service" {
  inherits = ["app-base"]
  target   = "ui-service"
  tags     = ["rag-converter/ui:latest"]
  output   = ["type=docker,dest=./docker/images/ui-service.tar"]
}

target "vector-service" {
  inherits = ["app-base"]
  target   = "vector-service"
  tags     = ["rag-converter/vector:latest"]
  output   = ["type=docker,dest=./docker/images/vector-service.tar"]
}

target "video-service" {
  inherits = ["app-base"]
  target   = "video-service"
  tags     = ["rag-converter/video:latest"]
  output   = ["type=docker,dest=./docker/images/video-service.tar"]
}

target "deps-base" {
  context    = "."
  dockerfile = "docker/Dockerfile.deps"
}

target "deps-redis" {
  inherits = ["deps-base"]
  target   = "redis"
  tags     = ["rag-converter/redis:7"]
  output   = ["type=docker,dest=./docker/images/deps-redis.tar"]
}

target "deps-minio" {
  inherits = ["deps-base"]
  target   = "minio"
  tags     = ["rag-converter/minio:latest"]
  output   = ["type=docker,dest=./docker/images/deps-minio.tar"]
}

target "deps-mysql" {
  inherits = ["deps-base"]
  target   = "mysql"
  tags     = ["rag-converter/mysql:8.0"]
  output   = ["type=docker,dest=./docker/images/deps-mysql.tar"]
}

target "deps-es" {
  inherits = ["deps-base"]
  target   = "es"
  tags     = ["rag-converter/es:8.14.0"]
  output   = ["type=docker,dest=./docker/images/deps-es.tar"]
}
