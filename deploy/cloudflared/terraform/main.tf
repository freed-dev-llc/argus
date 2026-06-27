# Cloudflare Access — service-token auth for the NetBox prometheus-sd endpoint.
#
# NetBox is gated behind Cloudflare Zero Trust (Azure AD / Entra) for interactive
# users. A Prometheus scraper cannot log in interactively, so it reads the NetBox
# prometheus-sd HTTP service-discovery endpoint using a Cloudflare Access *service
# token* (the CF-Access-Client-Id / CF-Access-Client-Secret request headers).
#
# This file is a self-contained ADDITION. It does NOT touch any existing,
# dashboard-managed hostname-wide NetBox Access app. It manages:
#   - a service token for the Prometheus scraper,
#   - a path-scoped Access application covering only /api/plugins/prometheus-sd/,
#   - a Service Auth (non_identity) policy allowing that one service token.
#
# Because the path-scoped app is more specific than the hostname-wide app, requests
# to the SD path match HERE (service-token auth) while the rest of NetBox stays
# SSO-only. The NetBox read-only API token (consumed scraper-side) is a separate
# layer and is not managed here.
#
# This is a PUBLIC repo: no real account ID or hostname is committed. Supply them
# via a gitignored terraform.tfvars (see terraform.tfvars.example) or TF_VAR_* env.
#
# Prerequisites:
#   - CLOUDFLARE_API_TOKEN env var, scoped to the account with:
#       Account > Access: Apps and Policies  (Edit)
#       Account > Access: Service Tokens      (Edit)
#
# Usage:
#   cd deploy/cloudflared/terraform
#   cp terraform.tfvars.example terraform.tfvars   # fill in real values (gitignored)
#   terraform init && terraform apply
#   # Then publish the credentials into the scraper's secret files (kept out of git):
#   terraform output -raw netbox_sd_service_token_client_id      # -> secrets/cf_access_client_id
#   terraform output -raw netbox_sd_service_token_client_secret  # -> secrets/cf_access_client_secret

terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID. Required; set via terraform.tfvars or TF_VAR_cloudflare_account_id (never committed)."
  type        = string

  validation {
    condition     = length(var.cloudflare_account_id) > 0
    error_message = "cloudflare_account_id must be set (terraform.tfvars or TF_VAR_cloudflare_account_id)."
  }
}

variable "netbox_hostname" {
  description = "Internal NetBox hostname fronted by Cloudflare Access. Override in terraform.tfvars."
  type        = string
  default     = "netbox.example.com"
}

variable "sd_path" {
  description = "Path prefix of the prometheus-sd endpoint to scope the service-token app to."
  type        = string
  default     = "/api/plugins/prometheus-sd/"
}

variable "service_token_name" {
  description = "Display name for the Cloudflare Access service token."
  type        = string
  default     = "prometheus-netbox-sd"
}

# Service token used by the Prometheus scraper (non-human identity).
# Default validity is 1 year; rotate before expiry and re-publish the scraper secrets.
resource "cloudflare_zero_trust_access_service_token" "prometheus_sd" {
  account_id = var.cloudflare_account_id
  name       = var.service_token_name
}

# Path-scoped Access application: covers ONLY the prometheus-sd endpoint, leaving
# the hostname-wide NetBox app (dashboard-managed, SSO) untouched.
resource "cloudflare_zero_trust_access_application" "netbox_prometheus_sd" {
  account_id                = var.cloudflare_account_id
  name                      = "NetBox — prometheus-sd (service token)"
  domain                    = "${var.netbox_hostname}${var.sd_path}"
  type                      = "self_hosted"
  session_duration          = "24h" # not meaningful for non-identity; kept for parity
  auto_redirect_to_identity = false # never bounce the scraper to an IdP login
  allowed_idps              = []
}

# Service Auth policy: allow exactly this service token, with no interactive identity.
# decision = "non_identity" is the Terraform equivalent of the dashboard "Service Auth" action.
resource "cloudflare_zero_trust_access_policy" "netbox_prometheus_sd_service_token" {
  account_id     = var.cloudflare_account_id
  application_id = cloudflare_zero_trust_access_application.netbox_prometheus_sd.id
  name           = "Prometheus service token"
  precedence     = 1
  decision       = "non_identity"

  include {
    service_token = [cloudflare_zero_trust_access_service_token.prometheus_sd.id]
  }
}

output "netbox_sd_service_token_client_id" {
  description = "CF-Access-Client-Id -> scraper secret cf_access_client_id"
  value       = cloudflare_zero_trust_access_service_token.prometheus_sd.client_id
}

output "netbox_sd_service_token_client_secret" {
  description = "CF-Access-Client-Secret -> scraper secret cf_access_client_secret (shown once)"
  value       = cloudflare_zero_trust_access_service_token.prometheus_sd.client_secret
  sensitive   = true
}
