# Operations runbook

Deployment, rollback, and production checks for CS Ticket Automation on GKE.

**Related:** [configuration.md](./configuration.md) · [HANDOFF.md](./HANDOFF.md) · [k8s/](../k8s/)

---

## Environments

| Environment | Branch trigger | Deploy | Host | Replicas |
|-------------|----------------|--------|------|----------|
| **dev** | `dev` (auto) | GitLab CI → Kaniko → kubectl | `cs-ticket-automation.itbs-dev.scmp.tech` | 1 |
| **prod** | `master` (**manual** job) | Same pipeline | `cs-ticket-automation.scmp.work` | 2 |

Namespace: `itbs-general`  
Project label: `cs-ticket-automation`

Dev ingress is IP-whitelisted (see `k8s/dev/deploy/ing.yaml`). Prod uses TLS via cert-manager (`letsencrypt-prod`).

---

## CI/CD pipeline

Defined in [`.gitlab-ci.yml`](../.gitlab-ci.yml):

```text
build (Kaniko) → image_scanning (Prisma, allow_failure)
              → repo_scanning (Prisma, allow_failure)
              → deploy (kubectl apply + rollout status)
```

| Stage | Template | Notes |
|-------|----------|-------|
| Build | `.kaniko-build` | Image: `$CI_REGISTRY_IMAGE/$CI_COMMIT_BRANCH:$CI_COMMIT_SHA` |
| Scan | Prisma Cloud | `allow_failure: true` — review findings before prod |
| Deploy | `k8s/deploy.sh` | `envsubst` on `k8s/{dev|prod}/deploy/*.yaml` → `.generated/` → `kubectl apply` |

**Deploy prod:** merge to `master`, then manually trigger the `deploy-prod` job in GitLab.

---

## Deploy script behaviour

[`k8s/deploy.sh`](../k8s/deploy.sh):

1. Validates `k8s/{K8S_DIR}/deploy/` exists
2. Runs `envsubst` on each YAML (substitutes `CONTAINER_IMAGE`, `K8S_ENV_SLUG`, etc.)
3. `kubectl apply -f .generated/`
4. `kubectl rollout status` on deployment manifests

Required CI variables (from templates): `K8S_API`, `K8S_CA`, `K8S_TKN`, `K8S_DIR`, `K8S_NS`, `K8S_PROJECT`, `CONTAINER_IMAGE`.

---

## Runtime configuration (no redeploy needed)

Live classifier config lives on **Google Drive** and is synced to pod-local `/app/runs/live/`:

| File | Updated by |
|------|------------|
| `Taxonomy.csv` | Learn Confirm, manual Drive edit |
| `CS_ticket_new_categorizations.xlsx` | Learn Confirm |
| `classifier_rules.json` | Rules Confirm, Learn Confirm |
| `config_version.json` | Any Confirm |

Env vars in prod deployment (`k8s/prod/deploy/deployment.yaml`):

- `RUNTIME_CONFIG_DRIVE_ENABLED=true`
- `DRIVE_UPLOAD_ENABLED=true`
- `GOOGLE_DRIVE_LIVE_FOLDER_ID` / `GOOGLE_DRIVE_RUNS_FOLDER_ID`
- `GOOGLE_APPLICATION_CREDENTIALS=/var/secrets/google/credentials.json`

**Rule or allow-list changes do not require a new image** when applied through portal Confirm (writes Drive → next sync).

---

## Pre-deploy checklist

- [ ] `pytest` green on the commit
- [ ] Prisma scan reviewed (if failing on critical CVEs)
- [ ] No unintended changes to `k8s/prod/` env vars or folder IDs
- [ ] Stakeholders notified if prod deploy includes **code** changes to classify logic (not just config)

---

## Post-deploy verification

```bash
# Health (prod)
curl -sS https://cs-ticket-automation.scmp.work/health
# Expected: ok

# Dev (from allowed network)
curl -sS https://cs-ticket-automation.itbs-dev.scmp.tech/health
```

**Functional smoke (browser or script):**

1. Upload small NDJSON (`tests/fixtures/golden_export.ndjson`)
2. Results page shows tier breakdown
3. Download XLSX succeeds
4. If LLM configured: Rules compile returns draft or clarify (not 500)

See [configuration.md § Verification](./configuration.md#verification-checklist).

---

## Rollback

### Application image rollback

```bash
# List rollout history
kubectl -n itbs-general rollout history deployment/prod-app-cs-ticket-automation

# Roll back to previous revision
kubectl -n itbs-general rollout undo deployment/prod-app-cs-ticket-automation

# Or pin a specific revision
kubectl -n itbs-general rollout undo deployment/prod-app-cs-ticket-automation --to-revision=N
```

Alternatively redeploy an earlier commit SHA via GitLab (re-run pipeline on known-good `master` commit).

### Live config rollback (rules / allow-list)

**Preferred:** portal `POST /learn/revert` when `config_version` still matches the bad Confirm.

**Manual:** restore files from `runs/live/backup/{version}/` on Drive or pod cache; bump or restore `config_version.json` consistently.

**Version guard:** if another Confirm landed after the bad one, global revert is blocked — escalate and consider targeted rule disable (`POST /rules/disable`) or manual Drive restore.

---

## Secrets and access

| Secret | Location | Purpose |
|--------|----------|---------|
| `editorial-service-account` | K8s secret → `/var/secrets/google/credentials.json` | Google Drive SA |
| Vault annotations | Pod metadata | Optional secret injection via Banzai Vault |
| GitLab CI tokens | `ITBS_*_K8S_TKN` variables | Deploy auth |

**Local dev:** place SA JSON at `secrets/google/credentials.json`; see `.env.example`.

**Drive folders:** share with `ai-daily-job-sa@editor-sub-editing-assistant.iam.gserviceaccount.com` as **Editor**.

---

## Monitoring and common issues

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| `/health` 502 | Pod crash, rollout in progress | `kubectl get pods -n itbs-general -l project=cs-ticket-automation` |
| Upload 413 | Body > 50m ingress limit | Split export or raise `proxy-body-size` |
| Classify differs between pods | Drive sync lag / stale cache | Confirm `RUNTIME_CONFIG_DRIVE_ENABLED`; check `config_version.json` |
| Confirm disabled | `PORTAL_ALLOW_CONFIRM` unset in prod | Expected — only enable for designated lead sessions |
| Run lost after refresh | In-memory run store | Re-upload export; expected limitation |
| LLM compile 500 | Missing API key / provider env | Check Vault or pod env for `RULE_COMPILE_*` |

**Logs:**

```bash
kubectl -n itbs-general logs -l project=cs-ticket-automation,env=prod --tail=200 -f
```

---

## Scaling notes

- Prod runs **2 replicas** with in-memory run storage — users may hit different pods and lose run context on navigation. Acceptable for Phase 1; sticky sessions or external store would be a future change.
- `emptyDir` at `/app/runs` is pod-local; **Drive is source of truth** for live config.

---

## Contacts (fill in for your org)

| Role | Contact | Responsibility |
|------|---------|----------------|
| Product / CS lead | _TBD_ | Confirm authority, taxonomy decisions |
| Engineering owner | _TBD_ | Deploys, classifier changes |
| ITBS platform | _TBD_ | K8s, GitLab, ingress |
| Google Drive admin | _TBD_ | Folder access, SA keys |

---

## Related documents

- [api-reference.md](./api-reference.md) — HTTP routes
- [design.md §8 Deployment](./design.md#8-deployment-architecture)
- [HANDOFF.md §12 Checklist](./HANDOFF.md#12-handoff-checklist)
