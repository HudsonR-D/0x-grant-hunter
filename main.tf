terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = "boring-access"
  region  = "us-central1"
}

# Artifact Registry
resource "google_artifact_registry_repository" "granthunter_repo" {
  location      = "us-central1"
  repository_id = "granthunter-repo"
  description   = "0xGrantHunter container images"
  format        = "DOCKER"
}

# Firestore
resource "google_firestore_database" "granthunter_db" {
  project         = "boring-access"
  name            = "granthunter-db"
  location_id     = "us-central1"
  type            = "FIRESTORE_NATIVE"
}

# Secret Manager
resource "google_secret_manager_secret" "granthunter_secrets" {
  secret_id = "granthunter-secrets"
  replication {
    auto {}
  }
}

# Cloud Run Service
resource "google_cloud_run_v2_service" "granthunter_service" {
  name     = "granthunter-service"
  location = "us-central1"
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image = "us-central1-docker.pkg.dev/boring-access/granthunter-repo/granthunter:latest"
      ports {
        container_port = 8080
      }
    }
  }
}

resource "google_cloud_run_service_iam_member" "public" {
  service  = google_cloud_run_v2_service.granthunter_service.name
  location = google_cloud_run_v2_service.granthunter_service.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

output "cloud_run_url" {
  value = google_cloud_run_v2_service.granthunter_service.uri
}