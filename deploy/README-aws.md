# Deploying to AWS

This project is **fully containerized** (`Dockerfile`, `frontend/Dockerfile`,
`docker-compose.prod.yml`). The whole stack — frontend, backend API, arq worker,
Neo4j (with the GDS plugin) and Redis — runs from one compose file.

> **The one AWS catch:** there is no managed Neo4j-with-GDS on AWS. Amazon
> Neptune is *not* compatible (no Cypher `gds.*`). So Neo4j must run on EC2
> (self-hosted, as below) or on **Neo4j Aura** (Neo4j's managed service, hosted
> on AWS — pick a tier that includes Graph Data Science).

---

## Option A — Single EC2 box (recommended, simplest end-to-end)

Runs everything, including Neo4j+GDS, with one command. Best for a demo / MVP.

### 1. Launch the instance
- **AMI:** Amazon Linux 2023
- **Type:** `t3.large` (8 GB RAM) recommended — Neo4j + GDS + parallel
  generation are memory-hungry. `t3.medium` (4 GB) is the practical minimum.
- **Storage:** 30 GB gp3 or more.
- **User data:** paste the contents of [`deploy/ec2-userdata.sh`](./ec2-userdata.sh)
  (installs Docker + compose and clones the repo automatically).
- **Security group (inbound):**
  | Port | Source | Why |
  |------|--------|-----|
  | 22   | your IP | SSH |
  | 80   | 0.0.0.0/0 | the app (frontend + proxied API) |
  | 7474 | your IP *(optional)* | Neo4j browser — keep it off the public internet |

  Do **not** expose 7687 or 8000 publicly; they talk over the internal Docker network.

### 2. Configure and start (over SSH)
```bash
cd ~/legacy_refactoring_agent
cp .env.example .env
nano .env
#   NEO4J_PASSWORD=<a strong password>
#   ANTHROPIC_API_KEY=sk-ant-...
#   ENVIRONMENT=production
#   FRONTEND_URL=http://<your-ec2-public-ip>     # for CORS
#   (Clerk / Stripe / Supabase / Redis are optional — leave blank to disable)

docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f backend   # watch it boot
```

### 3. Verify
Open `http://<public-ip>/`. The frontend serves the SPA and proxies `/api/*`
to the backend, so no CORS setup is needed for same-host access.

### 4. (Recommended) Add HTTPS + a domain
Put the box behind an **Application Load Balancer** with an **ACM** certificate,
or run **Caddy/Traefik** on the instance for automatic Let's Encrypt TLS, then
point a Route 53 record at it and set `FRONTEND_URL=https://yourdomain`.

---

## Option B — Managed services (more moving parts, scales better)

| Component | AWS service | Notes |
|-----------|-------------|-------|
| Frontend  | **S3 + CloudFront** | `npm run build` → upload `frontend/dist`. Set `VITE_API_BASE_URL=https://api.yourdomain/api`. |
| Backend + worker | **Elastic Beanstalk** | EB's Python platform reads the repo's `Procfile` natively (`web:` + `worker:`). No Dockerfile needed for this path. |
| Redis     | **ElastiCache for Redis** | Set `REDIS_URL` to the cluster endpoint; same VPC as the backend. |
| Neo4j+GDS | **EC2** or **Neo4j Aura** | Set `NEO4J_URI/USER/PASSWORD`. |

Because the backend and worker **share a filesystem** for generated artifacts
(`import/`, `services/`), if you split them onto separate EB instances you must
put that shared state on **EFS** (mounted at `/app/import` and `/app/services`).
The single-box Option A sidesteps this entirely with a shared Docker volume.

For containerized managed compute instead of EB, push the backend image to
**ECR** and run it on **ECS Fargate** (web + worker as two services), with the
same EFS requirement for shared artifacts.

---

## Infrastructure as code & CI

- **Terraform (Option A, automated):** [`deploy/terraform/`](./terraform/) provisions
  the EC2 box + security group and bootstraps Docker. `terraform apply` then follow
  the `next_steps` output. See [terraform/README.md](./terraform/README.md).
- **GitHub Actions → ECR:** [`.github/workflows/build-and-push-ecr.yml`](../.github/workflows/build-and-push-ecr.yml)
  builds and pushes the backend + frontend images to ECR on every push to `main`
  (OIDC auth — no stored keys). Required GitHub config is documented at the top of
  the workflow. Use these images for the ECS Fargate path.

## Secrets checklist (set as env vars / EB properties — never commit `.env`)
- `NEO4J_PASSWORD`, `NEO4J_URI`, `NEO4J_USER`
- `ANTHROPIC_API_KEY`  *(required for service generation)*
- `ENVIRONMENT=production`, `DEBUG=false`, `FRONTEND_URL`
- Optional: `REDIS_URL`, `SUPABASE_*`, `CLERK_*`, `STRIPE_*`
  (each feature stays off until its keys are present — see `backend/config.py`)
