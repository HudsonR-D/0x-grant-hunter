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

# =============================================================================
# Core Infrastructure (Artifact Registry, Firestore for ADK session state,
# Secret Manager for Gemini + MongoDB Atlas URI + agent deps)
# =============================================================================

resource "google_artifact_registry_repository" "granthunter_repo" {
  location      = "us-central1"
  repository_id = "granthunter-repo"
  description   = "0xGrantHunter container images"
  format        = "DOCKER"
}

# Firestore (used for ADK resumable agent session state / multi-agent workflows)
resource "google_firestore_database" "granthunter_db" {
  project         = "boring-access"
  name            = "granthunter-db"
  location_id     = "us-central1"
  type            = "FIRESTORE_NATIVE"
}

resource "google_secret_manager_secret" "granthunter_secrets" {
  secret_id = "granthunter-secrets"
  replication {
    auto {}
  }
}

resource "google_service_account" "granthunter_sa" {
  account_id   = "granthunter-run"
  display_name = "0xGrantHunter Cloud Run"
  description  = "Service account for the GrantHunter Cloud Run service (multi-agent orchestrator)"
}

resource "google_secret_manager_secret_iam_member" "granthunter_secret_accessor" {
  secret_id = google_secret_manager_secret.granthunter_secrets.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.granthunter_sa.email}"
}

# =============================================================================
# Cloud Run Service (multi-agent orchestrator)
# Includes secret volume mount + env vars for ReviewerAgent / WriterAgent
# =============================================================================

resource "google_cloud_run_v2_service" "granthunter_service" {
  name     = "granthunter-service"
  location = "us-central1"
  ingress  = "INGRESS_TRAFFIC_ALL" # LB will be the public face; tighten later with IAM if needed

  template {
    service_account = google_service_account.granthunter_sa.email

    containers {
      image = "us-central1-docker.pkg.dev/boring-access/granthunter-repo/granthunter-service:latest"
      ports {
        container_port = 8080
      }

      # The app reads the full JSON secret (GEMINI_API_KEY, MONGODB_ATLAS_URI,
      # plus any REVIEWER_AGENT_* / WRITER_AGENT_* keys you add to the secret)
      volume_mounts {
        name       = "granthunter-secrets"
        mount_path = "/secrets"
      }

      # Agent dependencies / multi-agent configuration (populate via Secret Manager JSON or override here)
      env {
        name  = "REVIEWER_AGENT_ENABLED"
        value = "true"
      }
      env {
        name  = "WRITER_AGENT_ENABLED"
        value = "true"
      }
      env {
        name  = "REVIEWER_AGENT_MODEL"
        value = "gemini-2.0-flash"
      }
      env {
        name  = "WRITER_AGENT_MODEL"
        value = "gemini-2.0-flash"
      }
      # Add more keys as needed (e.g. REVIEWER_AGENT_API_KEY) by extending the secret JSON payload
    }

    volumes {
      name = "granthunter-secrets"
      secret {
        secret = google_secret_manager_secret.granthunter_secrets.secret_id
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

# =============================================================================
# Global External HTTPS Load Balancer + Serverless NEG (for granthunter.hudsonrnd.com)
# Provides Google-managed SSL, clean routing, and enterprise-grade frontend.
# =============================================================================

# Reserved global IP (A record target for your DNS)
resource "google_compute_global_address" "granthunter_lb_ip" {
  name = "granthunter-lb-ip"
}

# Google-managed SSL certificate for the custom subdomain
resource "google_compute_managed_ssl_certificate" "granthunter_cert" {
  name = "granthunter-cert"
  managed {
    domains = ["granthunter.hudsonrnd.com"]
  }
}

# Serverless NEG pointing at the Cloud Run service
resource "google_compute_region_network_endpoint_group" "granthunter_neg" {
  name                  = "granthunter-neg"
  region                = "us-central1"
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.granthunter_service.name
  }
}

# Backend service for the NEG
resource "google_compute_backend_service" "granthunter_backend" {
  name                  = "granthunter-backend"
  protocol              = "HTTP"
  port_name             = "http"
  timeout_sec           = 30
  enable_cdn            = false

  backend {
    group = google_compute_region_network_endpoint_group.granthunter_neg.id
  }
}

# URL map (routes all traffic to the backend)
resource "google_compute_url_map" "granthunter_url_map" {
  name            = "granthunter-url-map"
  default_service = google_compute_backend_service.granthunter_backend.id
}

# Target HTTPS proxy (uses the managed cert)
resource "google_compute_target_https_proxy" "granthunter_https_proxy" {
  name             = "granthunter-https-proxy"
  url_map          = google_compute_url_map.granthunter_url_map.id
  ssl_certificates = [google_compute_managed_ssl_certificate.granthunter_cert.id]
}

# Global forwarding rule (the public entry point on port 443)
resource "google_compute_global_forwarding_rule" "granthunter_https" {
  name       = "granthunter-https"
  target     = google_compute_target_https_proxy.granthunter_https_proxy.id
  port_range = "443"
  ip_address = google_compute_global_address.granthunter_lb_ip.address
}

# (Optional but recommended) HTTP -> HTTPS redirect
resource "google_compute_url_map" "granthunter_http_redirect" {
  name = "granthunter-http-redirect"
  default_url_redirect {
    https_redirect = true
    strip_query    = false
  }
}

resource "google_compute_target_http_proxy" "granthunter_http_proxy" {
  name    = "granthunter-http-proxy"
  url_map = google_compute_url_map.granthunter_http_redirect.id
}

resource "google_compute_global_forwarding_rule" "granthunter_http" {
  name       = "granthunter-http"
  target     = google_compute_target_http_proxy.granthunter_http_proxy.id
  port_range = "80"
  ip_address = google_compute_global_address.granthunter_lb_ip.address
}

# =============================================================================
# Outputs (critical for DNS cutover)
# =============================================================================

output "cloud_run_url" {
  value       = google_cloud_run_v2_service.granthunter_service.uri
  description = "Internal Cloud Run URL (use the load balancer for public traffic)"
}

output "load_balancer_ip" {
  value       = google_compute_global_address.granthunter_lb_ip.address
  description = "Public IP for the Global LB. Create an A record in your DNS for granthunter.hudsonrnd.com pointing to this IP."
}

output "service_account_email" {
  value = google_service_account.granthunter_sa.email
}

output "ssl_certificate_name" {
  value = google_compute_managed_ssl_certificate.granthunter_cert.name
}

output "lb_https_forwarding_rule" {
  value = google_compute_global_forwarding_rule.granthunter_https.name
}