# Next Steps: Give Alpha Agent Hunter Access

These steps give the Alpha agent (running in the hermes-alpha web terminal) the ability to modify and deploy the Hunter agent.

---

## Step 1: Create the Hunter GitHub repo

1. Go to **https://github.com/new**
2. Owner: your org (e.g. `kaminocorp`) or your personal account
3. Repo name: **`hermes-hunter`** (or whatever you prefer)
4. Make it **Private**
5. Check **"Add a README file"** (so it's not empty)
6. Click **Create repository**

Note the full name (e.g. `kaminocorp/hermes-hunter`) — you'll need it below.

## Step 2: Create a GitHub fine-grained PAT

1. Go to **https://github.com/settings/tokens?type=beta**
2. Click **"Generate new token"**
3. Token name: `hermes-alpha-hunter-access`
4. Expiration: 90 days (or custom)
5. **Repository access** → select **"Only select repositories"** → pick **`hermes-hunter`**
6. **Permissions** → Repository permissions:
   - **Contents**: **Read and write** (push/pull code)
   - **Metadata**: **Read-only** (auto-selected)
   - That's all — leave everything else as "No access"
7. Click **Generate token**
8. **Copy the token** (starts with `github_pat_...`)

## Step 3: Create the Hunter Fly app

```bash
fly apps create hermes-hunter --org personal
```

Replace `personal` with your Fly org if you use one.

## Step 4: Create a Fly.io deploy token

```bash
fly tokens create deploy -a hermes-hunter
```

Copy the token (starts with `FlyV1 ...`).

## Step 5: Set all secrets on hermes-alpha

Run this single command, substituting your actual values:

```bash
fly secrets set \
  GITHUB_TOKEN="github_pat_YOUR_TOKEN_HERE" \
  FLY_API_TOKEN="FlyV1 YOUR_TOKEN_HERE" \
  HUNTER_REPO="kaminocorp/hermes-hunter" \
  HUNTER_FLY_APP="hermes-hunter" \
  -a hermes-alpha
```

## Step 6: Redeploy hermes-alpha

```bash
make deploy
```

This picks up the Dockerfile + entrypoint changes and the new secrets.

---

After redeployment, the Alpha agent will have `git` and `flyctl` authenticated inside its container and can push code to the Hunter repo and deploy it to the Hunter Fly app.
