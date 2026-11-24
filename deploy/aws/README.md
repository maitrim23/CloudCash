# Deploy CostGoblin on AWS (one EC2 instance, HTTPS, no domain needed)

> **Status: written but NOT tested.** It needs your AWS account and a published image, neither of which
> I have. The shell script is syntax-checked and the hostname logic is checked; everything else is
> untested. AWS console labels change, so treat button names as approximate.

**What you get:** `https://<your-ip-with-dashes>.sslip.io`, a real HTTPS certificate (Let's Encrypt via Caddy),
the app and its price database in one container, automatic pick-up of new images.

**Cost** (Mumbai `ap-south-1`, from our own calculator against the 2026-11-23 price list):

| Item | Per month |
|---|---|
| `t3.micro` On-Demand, 24/7 | $8.18 |
| 20 GB gp3 volume | $1.82 |
| Public IPv4 address (about $0.005/h; **from memory, please verify**) | about $3.65 |
| Data out: first 100 GB free, then $0.1093/GB | $0 for a demo |
| **Total** | **about $13.65**, minus whatever your free plan covers |

## Step 0: find out which free tier you have (you said "not sure")

AWS console -> your account name (top right) -> **Billing and Cost Management** -> **Free Tier**.

- You see **"credits remaining"** and a **plan end date** (6 months after sign-up) -> **new credit-based plan**. Credits cover this deployment until they run out or the plan ends; then you must upgrade to a paid plan or the account closes.
- You see **usage limits** such as "EC2: 750 hours" with a 12-month expiry -> **older free tier**. `t3.micro` hours are free, but the **public IPv4 and the EBS volume may not be**.
- You see neither -> the free period has ended; you pay the full ~$13.65.

## Step 1: set a budget alert FIRST

Billing and Cost Management -> **Budgets** -> **Create budget** -> use the **"Zero spend budget"** template (alerts you the moment anything is billed) or a **Monthly cost budget of $5**. Enter your email. Do this before creating anything.

## Step 2: prerequisites

1. The **build-image** workflow has finished green (repo -> Actions -> build-image -> Run workflow).
2. Your GitHub profile -> **Packages** -> `costgoblin` -> **Package settings** -> **Change visibility -> Public**.
3. In the AWS console choose region **Asia Pacific (Mumbai) ap-south-1** (top-right region menu), the one our price database was built for.

## Step 3: launch the server

EC2 -> **Elastic IPs** -> **Allocate Elastic IP address** -> Allocate. (A fixed address; without it the IP, and so the web address, changes when you stop the instance.)

EC2 -> **Instances** -> **Launch instances**:

| Field | Value |
|---|---|
| Name | `costgoblin` |
| AMI | **Amazon Linux 2023**, architecture **64-bit (x86)** (**not** Arm: our image is x86) |
| Instance type | **t3.micro** (it shows "Free tier eligible") |
| Key pair | **Proceed without a key pair** (you will not log in) |
| Network settings -> Auto-assign public IP | **Enable** |
| Security group | create new; **allow HTTP (80) and HTTPS (443) from anywhere**; **remove the SSH rule** |
| Storage | **20 GiB gp3** |
| Advanced details -> Metadata version | **V2 only (token required)** |
| Advanced details -> **User data** | paste the whole of [`user-data.sh`](user-data.sh) |

Click **Launch instance**.

## Step 4: attach the fixed IP

EC2 -> **Elastic IPs** -> select yours -> **Actions -> Associate Elastic IP address** -> choose the `costgoblin` instance -> Associate.

## Step 5: open it

Wait **about 5 minutes** (Docker install, image pull, certificate). The address is your Elastic IP with dots turned into dashes plus `.sslip.io`. For example, `203.0.113.10` becomes **https://203-0-113-10.sslip.io**.

You do not need to restart anything: a timer re-checks every 15 minutes, so if you attached the Elastic IP after the first boot it picks up the new address within 15 minutes.

**If it does not come up:** EC2 -> select the instance -> **Actions -> Monitor and troubleshoot -> Get system log** shows the setup log. Common causes: the GHCR package is not public (image pull fails), or the Elastic IP is not attached yet.

## Updating the app

Run the **build-image** workflow again. Within 15 minutes the server sees the new image and recreates the containers. Saved scenarios live in a Docker volume and survive this, but **not** if you terminate the instance.

## Cost control and teardown

- **Stop vs terminate:** stopping the instance stops the $8.18 compute charge but **the volume, and the Elastic IP, keep billing**. To end all charges: **Terminate** the instance **and** **Release** the Elastic IP (Elastic IPs -> Actions -> Release). Do both.
- Check **Billing -> Bills** after a day. The first month is the one to watch.
- A tiny `t3.micro` has 1 GiB of RAM: plenty for this app (the price database is read from disk by SQLite), but do not run anything else on it.

## Why not the other options

| Option | Why not (for now) |
|---|---|
| App Runner | [Closed to new customers](https://docs.aws.amazon.com/ja_jp/apprunner/latest/dg/apprunner-availability-change.html) since 2026-04-30 |
| ECS Express Mode (Fargate + load balancer) | AWS's App Runner replacement; no free-tier compute, and a load balancer adds a fixed monthly cost (not priced here) |
| Lightsail container service | $10/month fixed and simple, but I could not verify its free-plan credit coverage |
| Lambda | Near $0, but saved scenarios would need a different store (Lambda's disk is not durable): a code change |
