# Ansible ← NetBox dynamic inventory

Once Argus keeps NetBox current, Ansible can target your network straight from that source
of truth — no hand-maintained inventory. This uses the `netbox.netbox` collection's
[`nb_inventory`](https://netbox-ansible-collection.readthedocs.io/) plugin.

**It is read-only.** `nb_inventory` only *reads* NetBox to build an inventory, so it never
conflicts with Argus's reconcile (Argus owns the *discovered* objects — see
[ADR-0004](../docs/architecture/adr/0004-netbox-ansible-inventory.md)).

## Setup

```bash
cd ansible
ansible-galaxy collection install -r requirements.yml
pip install pynetbox pytz      # required by the plugin on the control node

export NETBOX_API=http://10.0.0.10:8096   # your NetBox
export NETBOX_TOKEN=<a NetBox API token>
```

## Use it

```bash
# See the inventory NetBox produces, grouped by site / role / manufacturer / ...
ansible-inventory --graph
ansible-inventory --host <device-name>      # host vars for one device

# Demo playbook (prints only, no device connection needed):
ansible-playbook playbooks/facts.yml

# Target a group built from NetBox:
ansible-playbook playbooks/facts.yml --limit device_roles_switch
```

`group_by` (in `netbox_inventory.yml`) creates groups like `sites_<slug>`,
`device_roles_<slug>`, `manufacturers_<slug>`, `status_active`, etc. `ansible_host` is set
to each device's NetBox primary IP (mask stripped).

## Deploy Argus itself (role)

The [`argus_deploy`](roles/argus_deploy/README.md) role stands up the whole stack on a Docker
host — repo checkout, `.env` rendering (secrets generated once and **reused** on re-runs), and
`docker compose up` — replacing the manual steps.

```bash
ansible-galaxy collection install -r requirements.yml
cp inventory/hosts.example.yml inventory/hosts.yml   # edit host + Vault the UniFi creds
ansible-playbook -i inventory/hosts.yml deploy-argus.yml
```

## Configure git commit signing (role)

The [`git_signing`](roles/git_signing/README.md) role sets up SSH commit signing for one
or more users on a host — git identity, a dedicated `~/.ssh/github-commit-signing`
ed25519 key, `commit.gpgsign`/`tag.gpgsign`, and a fleet-wide `allowed_signers` file
built from the keys registered on the GitHub account — so agents and humans on any host
produce commits that satisfy GitHub's required-signed-commits branch protection.

```bash
ansible-playbook playbooks/git-signing.yml --limit mesh -e 'git_signing_users=["aria","hermes"]'
```

Registering each new public key on the GitHub account (as an SSH **signing** key) is the
one manual step; the role prints the exact `gh api` command for any key it doesn't find
registered.

## Notes

- Actually *running tasks* against the devices needs reachability + credentials (SSH/API)
  for that gear — out of scope here; the value is that the **inventory** is always in sync
  with reality via Argus.
- This is the "outbound" half of the loop: Argus discovers reality → NetBox (SoT) → Ansible
  consumes it. Keep Ansible/Terraform as readers or scoped writers (ADR-0004).
