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

export NETBOX_API=http://10.10.88.130:8096   # your NetBox
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

## Notes

- Actually *running tasks* against the devices needs reachability + credentials (SSH/API)
  for that gear — out of scope here; the value is that the **inventory** is always in sync
  with reality via Argus.
- This is the "outbound" half of the loop: Argus discovers reality → NetBox (SoT) → Ansible
  consumes it. Keep Ansible/Terraform as readers or scoped writers (ADR-0004).
