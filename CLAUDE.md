# Agentic Dev — Claude Instructions

You are helping a **non-developer** build and deploy applications on AWS using CodePipeline. Follow this file strictly when writing or modifying code in an Agentic Dev project.

---

## Step 0 — Platform context (read first)

The **platform / DevOps team** provisions all AWS infrastructure before the user pushes code:

- CodePipeline, CodeBuild, ECR, ECS, S3, CloudFront, ALB, domains
- AWS Secrets Manager secret per backend service → injected as `APP_SECRETS` in ECS
- Pipeline environment variables (`BUCKET`, `DISTRIBUTION_ID`, `IMAGE_REPO_NAME`, etc.)

The user **does not** set up pipelines, AWS accounts, or secrets. They only write code and push to GitHub.

**UAT live URLs (reference):**

| App | URL |
|-----|-----|
| Frontend | `https://app-uat-agentic-dev.spyne.ai` |
| Backend API | `https://api-uat-agentic-dev.spyne.ai` |
| Health check | `https://api-uat-agentic-dev.spyne.ai/agentic-dev/api/v1/health` |

**Sample GitHub repos:**

- Frontend: `spyne-ai-agentic-dev/agentic-dev-sample-frontend`
- Backend: `spyne-ai-agentic-dev/agentic-dev-sample-backend`

If the user asks you to "deploy" or "set up AWS", tell them to contact the platform team to register their repo. Your job is the **application code only**.

---

## Step 1 — Identify the app type

| Type | When to use | AWS target |
|------|-------------|------------|
| **Static frontend** | HTML, CSS, JavaScript only. No server-side runtime. No `npm run build` step. | S3 + CloudFront |
| **Dynamic backend** | Node.js API, server, or any code that runs in a container. | ECS Fargate + ECR |

If unsure: **no Dockerfile needed → static frontend**. **API or server → dynamic backend**.

---

## Step 2 — Required repo files (do not skip)

### Static frontend (minimum)

```
my-frontend/
├── index.html          # Required — entry page
├── app.js              # Required — application logic
├── styles.css          # Required — styles
├── config.json         # Required — runtime API config (no secrets)
├── 404.html            # Required — error page
├── code-build.yaml     # Required — pipeline build stage
└── code-deploy.yaml    # Required — pipeline deploy stage
```

### Dynamic backend (minimum)

```
my-backend/
├── index.js            # Required — application entry (reads APP_SECRETS)
├── package.json        # Required — must have "start" script
├── Dockerfile          # Required — container image definition
├── code-build.yaml     # Required — Docker build + ECR push
└── code-deploy.yaml    # Required — ECS deploy artifact handoff
```

---

## Step 3 — Rules you MUST follow

### Secrets & configuration

| Do | Don't |
|----|-------|
| Read backend config from `APP_SECRETS` (JSON injected by ECS from Secrets Manager) | Hardcode URLs, ports, or origins in `index.js` |
| Use `config.json` for frontend API URLs (non-secret, public config) | Put passwords or API keys in `config.json` or source code |
| Fail fast at startup if required config is missing | Add fallback hardcoded production values in code |
| Keep `Dockerfile` free of `ENV` for runtime values | Set `ENV NODE_ENV`, `ENV PORT`, etc. in Dockerfile |

**Why two different approaches?**

- **Frontend** is static files on S3 — anyone can read them. Use `config.json` for public settings only (API URL, feature flags). This is standard industry practice.
- **Backend** runs in ECS — the platform injects a Secrets Manager JSON blob as `APP_SECRETS` at container startup. Use this for ports, CORS origin, and any sensitive values.

### Backend — APP_SECRETS contract

ECS injects one environment variable: `APP_SECRETS` (JSON string from AWS Secrets Manager). Terraform creates one secret per backend service (e.g. `spyne-agentic-dev-api`).

Expected keys (managed by platform team, not by you in code):

```json
{
  "NAME": "<service-name>",
  "PORT": "3000",
  "ALLOWED_ORIGIN": "https://<frontend-domain>",
  "NODE_ENV": "development"
}
```

UAT example:

```json
{
  "NAME": "spyne-agentic-dev-api",
  "PORT": "3000",
  "ALLOWED_ORIGIN": "https://app-uat-agentic-dev.spyne.ai",
  "NODE_ENV": "development"
}
```

Your backend code MUST parse `APP_SECRETS` like this:

```javascript
function loadConfig() {
  if (process.env.APP_SECRETS) {
    const secrets = JSON.parse(process.env.APP_SECRETS);
    return {
      name: secrets.NAME,
      port: Number(secrets.PORT),
      allowedOrigin: secrets.ALLOWED_ORIGIN,
      nodeEnv: secrets.NODE_ENV,
    };
  }
  // Local dev only — individual env vars
  return {
    name: process.env.NAME,
    port: Number(process.env.PORT),
    allowedOrigin: process.env.ALLOWED_ORIGIN,
    nodeEnv: process.env.NODE_ENV,
  };
}
```

### Frontend — config.json contract

```json
{
  "apiBaseUrl": "https://api-uat-agentic-dev.spyne.ai",
  "apiEndpoint": "/agentic-dev/api/v1/health"
}
```

- Load via `fetch("./config.json")` at runtime — never hardcode API URLs in `app.js`.
- Use the **exact** API hostname provided by the platform team.
- Replace `<env>` with the actual environment (UAT uses `uat`: `api-uat-agentic-dev.spyne.ai`).

### CORS (backend)

Set `Access-Control-Allow-Origin` from `config.allowedOrigin` (from `APP_SECRETS.ALLOWED_ORIGIN`).

Handle `OPTIONS` preflight requests so browser `fetch` from the static frontend succeeds.

### Health check (backend)

Expose this exact path for load balancer / ECS health checks:

```
GET /agentic-dev/api/v1/health
```

Response:

```json
{
  "status": "healthy",
  "service": "<NAME from secrets>",
  "timestamp": "<ISO-8601>"
}
```

The ALB routes all paths matching `/agentic-dev/api/v1/*` to your container.

### Pipeline files — do not change unless asked

- **`code-build.yaml`** and **`code-deploy.yaml`** are platform-managed templates.
- Copy from `templates/` in this repo — do not invent new pipeline logic.
- Do **not** add Parameter Store or Secrets Manager calls in buildspecs.
- Do **not** add `npm run build` to static frontends.
- Do **not** add S3 sync commands to backend deploy specs.

---

## Step 4 — Copy the correct templates

Use the templates in `agentic-dev-docs/templates/`:

- Static → `templates/static-frontend/`
- Dynamic → `templates/dynamic-backend/`

Only customize the **`build`** phase file list in frontend `code-build.yaml` if you add new static assets (e.g. `images/`).

---

## Step 5 — Dockerfile rules (backend only)

```dockerfile
FROM node:22-alpine

WORKDIR /app

COPY package.json ./
COPY index.js ./

EXPOSE 3000

USER node

CMD ["npm", "start"]
```

- No `ENV` for runtime config.
- No `npm install` if there are zero dependencies (sample app pattern).
- Add `COPY` lines only for files the app actually needs.
- Listen on `0.0.0.0` and port from `APP_SECRETS.PORT`.

---

## Step 6 — Before telling the user to push

Verify:

- [ ] Correct app type templates are in the repo root
- [ ] All required files exist (see Step 2)
- [ ] No secrets hardcoded in source
- [ ] Backend health endpoint path is `/agentic-dev/api/v1/health`
- [ ] Frontend `config.json` has correct `apiBaseUrl` (ask user for platform-provided URL if unknown)
- [ ] `code-deploy.yaml` is included in frontend build artifacts (via `**/*` or explicit list)
- [ ] Backend `Dockerfile` has no runtime `ENV` lines
- [ ] User knows their repo must be registered by platform team before first deploy

---

## Step 7 — What the user does (not you)

The platform team provisions (via Terraform):

- CodePipeline (`spyne-agentic-dev-app` / `spyne-agentic-dev-api` naming pattern)
- ECR repo, ECS Fargate service, ALB with path `/agentic-dev/api/v1/*`
- S3 bucket + CloudFront for frontend (`app-uat-agentic-dev.spyne.ai`)
- Secrets Manager secret → ECS task definition (`APP_SECRETS`)
- Environment variables: `IMAGE_REPO_NAME`, `BUCKET`, `DISTRIBUTION_ID`, etc.

The user only:

1. Writes/edits code with your help
2. Commits and pushes to GitHub
3. Pipeline runs automatically (after platform registration)

---

## Reference samples

Working examples on GitHub:

- Static: `spyne-ai-agentic-dev/agentic-dev-sample-frontend`
- Dynamic: `spyne-ai-agentic-dev/agentic-dev-sample-backend`

When in doubt, match those projects.
