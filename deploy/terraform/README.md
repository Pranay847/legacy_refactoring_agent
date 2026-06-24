# Terraform — single EC2 deploy

Provisions one EC2 instance (Amazon Linux 2023) in your default VPC, with a
security group and a bootstrap that installs Docker + Compose and clones the
repo. You finish the deploy over SSH (the instance never sees your secrets).

## Prerequisites
- Terraform >= 1.5 and AWS credentials configured (`aws configure` or env vars).
- An **existing EC2 key pair** in the target region (for SSH).
- Your public IP (for `allowed_ssh_cidr`).

## Use
```bash
cd deploy/terraform
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars: key_name, allowed_ssh_cidr, region

terraform init
terraform plan
terraform apply        # prints public_ip, app_url, and next_steps

# Then follow the `next_steps` output: SSH in, fill .env, docker compose up.
```

## What it creates
- 1× `aws_instance` (default `t3.large`, 30 GB gp3)
- 1× `aws_security_group` — inbound 80 (all), 22 (your IP), 7474 (optional, your IP)

## Notes
- **Cost**: a `t3.large` runs ~\$60/mo on-demand if left on. `terraform destroy`
  tears everything down.
- This is the single-box path (Neo4j + GDS run on the instance). For managed
  services (EB / ECS / ElastiCache / Aura) see [../README-aws.md](../README-aws.md).
- Variables: see [variables.tf](variables.tf).
