terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

# Latest Amazon Linux 2023 AMI id, resolved from the public SSM parameter.
data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

# Single-box demo: deploy into the account's default VPC + first default subnet.
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "app" {
  name        = "${var.name}-sg"
  description = "Legacy Refactoring Agent - web + SSH"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP (app: frontend + proxied API)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  # Neo4j browser is OFF by default; if enabled it is still restricted to your IP.
  dynamic "ingress" {
    for_each = var.expose_neo4j_browser ? [1] : []
    content {
      description = "Neo4j browser"
      from_port   = 7474
      to_port     = 7474
      protocol    = "tcp"
      cidr_blocks = [var.allowed_ssh_cidr]
    }
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.name}-sg" }
}

resource "aws_instance" "app" {
  ami                    = data.aws_ssm_parameter.al2023.value
  instance_type          = var.instance_type
  subnet_id              = element(tolist(data.aws_subnets.default.ids), 0)
  vpc_security_group_ids = [aws_security_group.app.id]
  key_name               = var.key_name

  user_data = templatefile("${path.module}/user-data.sh.tftpl", {
    repo_url = var.repo_url
  })

  root_block_device {
    volume_size = var.disk_gb
    volume_type = "gp3"
  }

  tags = { Name = var.name }
}
