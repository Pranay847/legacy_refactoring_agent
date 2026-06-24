variable "region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "name" {
  description = "Name tag / prefix for created resources."
  type        = string
  default     = "legacy-refactoring-agent"
}

variable "instance_type" {
  description = "EC2 instance type. t3.large (8 GB) recommended; t3.medium (4 GB) minimum."
  type        = string
  default     = "t3.large"
}

variable "key_name" {
  description = "Name of an EXISTING EC2 key pair to enable SSH access."
  type        = string
}

variable "allowed_ssh_cidr" {
  description = "CIDR allowed to SSH (and reach the Neo4j browser if exposed). Use YOUR_IP/32."
  type        = string
}

variable "expose_neo4j_browser" {
  description = "Open port 7474 (Neo4j browser) to allowed_ssh_cidr only."
  type        = bool
  default     = false
}

variable "disk_gb" {
  description = "Root EBS volume size in GB."
  type        = number
  default     = 30
}

variable "repo_url" {
  description = "Git repository cloned onto the instance by user-data."
  type        = string
  default     = "https://github.com/Pranay847/legacy_refactoring_agent.git"
}
