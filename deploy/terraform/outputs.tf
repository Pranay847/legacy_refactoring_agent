output "public_ip" {
  description = "Public IP of the instance."
  value       = aws_instance.app.public_ip
}

output "app_url" {
  description = "URL the app is served on once you finish the SSH steps."
  value       = "http://${aws_instance.app.public_ip}/"
}

output "ssh_command" {
  description = "SSH into the instance."
  value       = "ssh ec2-user@${aws_instance.app.public_ip}"
}

output "next_steps" {
  description = "Finish the deploy after `terraform apply`."
  value       = <<-EOT
    1. ssh ec2-user@${aws_instance.app.public_ip}
    2. cd ~/legacy_refactoring_agent && cp .env.example .env && nano .env
         NEO4J_PASSWORD=<strong password>
         ANTHROPIC_API_KEY=sk-ant-...
         ENVIRONMENT=production
         FRONTEND_URL=http://${aws_instance.app.public_ip}
    3. docker compose -f docker-compose.prod.yml up -d --build
    4. open http://${aws_instance.app.public_ip}/
  EOT
}
